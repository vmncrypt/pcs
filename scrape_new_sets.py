#!/usr/bin/env python3
"""
Scrape new Pokemon card sets from Bulbapedia and PriceCharting.
Imports directly to Supabase for automated tracking.

Usage:
    python scrape_new_sets.py --scrape-bulbapedia  # Get latest sets from Bulbapedia
    python scrape_new_sets.py --scrape-cards       # Get cards from PriceCharting
    python scrape_new_sets.py --all                # Run both steps
"""

import requests
import json
import re
import os
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from supabase import create_client, Client
from typing import List, Dict, Optional

# --- Configuration ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Supabase client (initialized only when needed)
supabase: Optional[Client] = None

def get_supabase_client() -> Client:
    """Get or create Supabase client."""
    global supabase
    if supabase is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables must be set")
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Bulbapedia config
BULBAPEDIA_BASE_URL = "https://bulbapedia.bulbagarden.net"
BULBAPEDIA_EN_URL = f"{BULBAPEDIA_BASE_URL}/wiki/List_of_Pok%C3%A9mon_Trading_Card_Game_expansions"

# PriceCharting config
PRICECHARTING_BASE_URL = "https://www.pricecharting.com"
PRICECHARTING_CATEGORY_URL = f"{PRICECHARTING_BASE_URL}/category/pokemon-cards"


def scrape_bulbapedia_sets() -> List[Dict]:
    """
    Scrapes Pokemon TCG expansion data from Bulbapedia.
    Returns list of sets with metadata.
    """
    logging.info(f"Scraping Bulbapedia expansions from {BULBAPEDIA_EN_URL}")

    try:
        # Simple headers - don't look like a bot
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

        # Small delay to be respectful
        time.sleep(1)

        response = requests.get(BULBAPEDIA_EN_URL, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        expansions = []
        tables = soup.find_all("table")

        for table in tables:
            # Look for tables with expansion data
            header_row = table.find("tr")
            if not header_row:
                continue

            headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

            # Check if this is an expansion table
            if "Name of Expansion" not in headers or "Release date" not in headers:
                continue

            # Get header indices
            name_idx = headers.index("Name of Expansion")
            date_idx = headers.index("Release date")
            cards_idx = headers.index("No. of cards") if "No. of cards" in headers else None
            abbr_idx = headers.index("Set abb.") if "Set abb." in headers else None

            # Process each row
            data_rows = table.find_all("tr")[1:]
            for row in data_rows:
                cells = row.find_all("td")
                if len(cells) < len(headers):
                    continue

                name = cells[name_idx].get_text(strip=True)
                if not name:
                    continue

                expansion = {
                    "name": name,
                    "release_date": cells[date_idx].get_text(strip=True) if date_idx < len(cells) else None,
                    "card_count": re.sub(r'[^\d]', '', cells[cards_idx].get_text(strip=True)) if cards_idx and cards_idx < len(cells) else None,
                    "abbreviation": cells[abbr_idx].get_text(strip=True) if abbr_idx and abbr_idx < len(cells) else None,
                }

                # Get Bulbapedia link
                link_tag = cells[name_idx].find("a")
                if link_tag and link_tag.has_attr("href"):
                    href = link_tag['href']
                    if href and not href.startswith('#'):
                        expansion['bulbapedia_url'] = BULBAPEDIA_BASE_URL + href

                expansions.append(expansion)

        logging.info(f"Successfully scraped {len(expansions)} expansions from Bulbapedia")
        return expansions

    except Exception as e:
        logging.error(f"Error scraping Bulbapedia: {e}")
        return []


def scrape_pricecharting_series() -> List[Dict]:
    """
    Scrapes PriceCharting Pokemon category page to get series URLs.
    Returns list of series with their PriceCharting URLs.
    """
    logging.info(f"Scraping PriceCharting category: {PRICECHARTING_CATEGORY_URL}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    try:
        response = requests.get(PRICECHARTING_CATEGORY_URL, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        series_list = []

        # Find the table with game listings
        table = soup.find("table", {"id": "games_table"}) or soup.find("table", class_="hover_table")
        if not table:
            logging.warning("Could not find games table on PriceCharting category page")
            return []

        rows = table.find_all("tr")[1:]  # Skip header
        for row in rows:
            link = row.find("a")
            if not link or not link.has_attr("href"):
                continue

            series_url = PRICECHARTING_BASE_URL + link['href']
            series_name = link.get_text(strip=True)

            series_list.append({
                "name": series_name,
                "pricecharting_url": series_url
            })

        logging.info(f"Found {len(series_list)} series on PriceCharting")
        return series_list

    except Exception as e:
        logging.error(f"Error scraping PriceCharting category: {e}")
        return []


def scrape_pricecharting_cards(series_url: str) -> List[Dict]:
    """
    Scrapes individual cards from a PriceCharting series page.
    Returns list of cards with pricing data.
    """
    logging.info(f"Scraping cards from: {series_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }

    try:
        response = requests.get(series_url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        cards = []

        # Find the product table
        table = soup.find("table", {"id": "games_table"})
        if not table:
            logging.warning(f"No product table found on {series_url}")
            return []

        # Get headers
        header_row = table.find("tr")
        headers = [th.get_text(strip=True) for th in header_row.find_all("th")]

        # Process each card
        rows = table.find_all("tr")[1:]
        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue

            # Get card name and link
            first_cell = cells[0]
            link = first_cell.find("a")
            if not link:
                continue

            card_name = link.get_text(strip=True)
            card_url = PRICECHARTING_BASE_URL + link['href'] if link.has_attr('href') else None

            # Get image
            img = first_cell.find("img")
            card_image = img['src'] if img and img.has_attr('src') else None

            # Get prices (varies by table structure)
            prices = {}
            for i, cell in enumerate(cells[1:], 1):
                if i < len(headers):
                    price_text = cell.get_text(strip=True).replace('$', '').replace(',', '')
                    try:
                        prices[headers[i]] = float(price_text) if price_text else None
                    except ValueError:
                        prices[headers[i]] = None

            card = {
                "name": card_name,
                "pricecharting_url": card_url,
                "image_url": card_image,
                "prices": prices
            }

            cards.append(card)

        logging.info(f"Scraped {len(cards)} cards from series")
        return cards

    except Exception as e:
        logging.error(f"Error scraping cards from {series_url}: {e}")
        return []


def import_sets_to_supabase(sets: List[Dict]) -> int:
    """
    Imports sets from Bulbapedia to Supabase groups table.
    Returns number of new sets imported.
    """
    logging.info(f"Importing {len(sets)} sets to Supabase...")

    # Get existing groups
    db = get_supabase_client()
    result = db.table("groups").select("name").execute()
    existing_names = {row['name'] for row in result.data}

    new_count = 0
    for set_data in sets:
        set_name = set_data['name']

        # Skip if already exists
        if set_name in existing_names:
            logging.debug(f"Set '{set_name}' already exists, skipping")
            continue

        # Insert new set
        try:
            db.table("groups").insert({
                "name": set_name,
            }).execute()
            new_count += 1
            logging.info(f"Imported new set: {set_name}")
        except Exception as e:
            logging.error(f"Error importing set '{set_name}': {e}")

    logging.info(f"Imported {new_count} new sets to Supabase")
    return new_count


def scrape_all_cards_from_pricecharting(delay: float = 1.5) -> List[Dict]:
    """
    Scrapes all series and their cards from PriceCharting.
    Returns complete card data in BankTCG format.
    """
    all_cards = []

    # Get all series
    series_list = scrape_pricecharting_series()

    for i, series in enumerate(series_list, 1):
        logging.info(f"Processing series {i}/{len(series_list)}: {series['name']}")

        # Scrape cards from this series
        cards = scrape_pricecharting_cards(series['pricecharting_url'])

        # Format cards in BankTCG structure
        for card in cards:
            # Extract card number from name if present
            number_match = re.search(r'#?(\d+)', card['name'])
            card_number = number_match.group(1) if number_match else None

            # Get price (ungraded)
            market_price = card['prices'].get('Ungraded', 0) or 0

            formatted_card = {
                "group": series['name'],
                "name": card['name'],
                "number": card_number,
                "market_price": market_price,
                "image": card['image_url'],
                "pricecharting_url": card['pricecharting_url'],
            }

            all_cards.append(formatted_card)

        # Rate limiting
        if i < len(series_list):
            time.sleep(delay)

    logging.info(f"Scraped {len(all_cards)} total cards from {len(series_list)} series")
    return all_cards


def import_cards_to_supabase(cards: List[Dict]) -> tuple[int, int]:
    """
    Imports cards and groups to Supabase.
    Returns (new_groups_count, new_cards_count).
    """
    logging.info(f"Importing {len(cards)} cards to Supabase...")

    db = get_supabase_client()

    # Get existing groups
    groups_result = db.table("groups").select("id, name").execute()
    group_map = {row['name']: row['id'] for row in groups_result.data}

    # Get existing products
    products_result = db.table("products").select("variant_key").execute()
    existing_variant_keys = {row['variant_key'] for row in products_result.data}

    new_groups = 0
    new_cards = 0

    # Group cards by series
    cards_by_group = {}
    for card in cards:
        group_name = card['group']
        if group_name not in cards_by_group:
            cards_by_group[group_name] = []
        cards_by_group[group_name].append(card)

    # Process each group
    for group_name, group_cards in cards_by_group.items():
        # Create group if it doesn't exist
        if group_name not in group_map:
            try:
                result = db.table("groups").insert({"name": group_name}).execute()
                group_id = result.data[0]['id']
                group_map[group_name] = group_id
                new_groups += 1
                logging.info(f"Created new group: {group_name}")
            except Exception as e:
                logging.error(f"Error creating group '{group_name}': {e}")
                continue
        else:
            group_id = group_map[group_name]

        # Import cards for this group
        for card in group_cards:
            # Generate variant_key (simplified)
            variant_key = f"{group_name}-{card['number']}".lower().replace(' ', '-')[:100]

            # Skip if already exists
            if variant_key in existing_variant_keys:
                continue

            # Estimate rarity based on price
            market_price = card.get('market_price', 0)
            if market_price >= 50:
                rarity = "Ultra Rare"
            elif market_price >= 10:
                rarity = "Rare"
            elif market_price >= 5:
                rarity = "Uncommon"
            else:
                rarity = "Common"

            try:
                db.table("products").insert({
                    "group_id": group_id,
                    "variant_key": variant_key,
                    "name": card['name'],
                    "number": card.get('number'),
                    "market_price": market_price,
                    "rarity": rarity,
                    "pricecharting_url": card.get('pricecharting_url'),
                }).execute()
                new_cards += 1
            except Exception as e:
                logging.error(f"Error importing card '{card['name']}': {e}")

    logging.info(f"Imported {new_groups} new groups and {new_cards} new cards")
    return new_groups, new_cards


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Scrape new Pokemon sets and cards")
    parser.add_argument("--scrape-bulbapedia", action="store_true", help="Scrape sets from Bulbapedia and import to Supabase")
    parser.add_argument("--scrape-cards", action="store_true", help="Scrape all cards from PriceCharting and import to Supabase")
    parser.add_argument("--all", action="store_true", help="Run all scraping steps")
    parser.add_argument("--output", help="Save scraped data to JSON file (optional)")
    parser.add_argument("--no-import", action="store_true", help="Skip Supabase import (only save to JSON)")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between requests in seconds (default: 1.5)")

    args = parser.parse_args()

    if not any([args.scrape_bulbapedia, args.scrape_cards, args.all]):
        parser.print_help()
        return

    # Step 1: Scrape Bulbapedia (get set metadata)
    if args.scrape_bulbapedia or args.all:
        logging.info("=== Scraping Bulbapedia ===")
        bulbapedia_sets = scrape_bulbapedia_sets()

        if args.output:
            output_file = args.output.replace('.json', '_bulbapedia.json')
            with open(output_file, 'w') as f:
                json.dump(bulbapedia_sets, f, indent=2)
            logging.info(f"Saved Bulbapedia data to {output_file}")

        # Import to Supabase (unless --no-import)
        if not args.no_import:
            new_count = import_sets_to_supabase(bulbapedia_sets)
            logging.info(f"✓ Imported {new_count} new sets from Bulbapedia\n")
        else:
            logging.info(f"Skipped Supabase import (--no-import)\n")

    # Step 2: Scrape PriceCharting (get card listings)
    if args.scrape_cards or args.all:
        logging.info("=== Scraping PriceCharting ===")
        all_cards = scrape_all_cards_from_pricecharting(delay=args.delay)

        if args.output:
            output_file = args.output or 'pokemon-cards-scraped.json'
            with open(output_file, 'w') as f:
                json.dump(all_cards, f, indent=2)
            logging.info(f"Saved card data to {output_file}")

        # Import to Supabase (unless --no-import)
        if not args.no_import:
            new_groups, new_cards = import_cards_to_supabase(all_cards)
            logging.info(f"✓ Imported {new_groups} new groups and {new_cards} new cards\n")
        else:
            logging.info(f"Skipped Supabase import (--no-import)\n")

    logging.info("=== Done! ===")
    logging.info("Run 'python sync_eligible_products.py' to mark cards >= $15 for scraping")


if __name__ == "__main__":
    main()

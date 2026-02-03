#!/usr/bin/env python3
"""
Backfill cards for newly discovered Pokemon sets.

This script finds sets in the groups table that have a set_url but no products,
then scrapes card data from PriceCharting and adds them to the products table.

Usage:
    python backfill_new_sets.py
    python backfill_new_sets.py --dry-run  # Preview without adding
    python backfill_new_sets.py --set-id <group_id>  # Process specific set
"""

import os
import argparse
import time
import re
import random
import concurrent.futures
from datetime import datetime
import logging
from dotenv import load_dotenv
from supabase import create_client, Client
import requests
from bs4 import BeautifulSoup

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Global session for connection reuse
session = requests.Session()


def fetch_page(url, retries=3):
    """Fetch HTML content from the given URL with retries."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Rate limiting
    time.sleep(2)

    for i in range(retries):
        try:
            response = session.get(url, headers=headers, timeout=20)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.warning(f"Attempt {i+1} failed for {url}: {e}")
            time.sleep(2 * (i + 1))

    logger.error(f"Failed to fetch {url} after {retries} attempts")
    return None


def parse_price(price_str):
    """Clean and convert price string to float. Returns None if invalid."""
    if not price_str:
        return None
    clean_str = re.sub(r'[^\d.]', '', price_str)
    if not clean_str:
        return None
    try:
        return float(clean_str)
    except ValueError:
        return None


def scrape_set_cards_list(set_url):
    """Scrape the list of cards from a set page, handling pagination."""
    all_cards = []
    cursor = None
    page = 1

    while True:
        if page == 1:
            logger.info(f"Fetching page {page} for {set_url}")
            html = fetch_page(set_url)
        else:
            if not cursor:
                break
            logger.info(f"Fetching page {page} (cursor: {cursor})")
            try:
                time.sleep(2)
                response = session.post(set_url, data={"cursor": cursor}, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }, timeout=20)
                if response.status_code != 200:
                    logger.warning(f"Failed to fetch page {page}: Status {response.status_code}")
                    break
                html = response.text
            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

        if not html:
            break

        soup = BeautifulSoup(html, "lxml")

        # Try different table selectors
        table = soup.find("table", id="games_table")
        if not table:
            table = soup.find("table", class_="hover_table")

        if not table:
            if page == 1:
                logger.warning(f"Could not find card table for {set_url}")
            break

        # Parse rows
        rows = table.find_all("tr")
        current_page_cards = []

        for row in rows:
            # Extract Product ID
            product_id = row.get("data-product")
            if not product_id:
                row_id = row.get("id", "")
                if row_id.startswith("product-"):
                    product_id = row_id.replace("product-", "")

            if not product_id:
                continue

            # Extract Title and URL
            title_cell = row.find("td", class_="title")
            if not title_cell:
                continue

            link = title_cell.find("a")
            if not link:
                continue

            name = link.text.strip()
            href = link.get("href")
            if not href:
                continue

            full_url = "https://www.pricecharting.com" + href

            # Extract Price (Ungraded)
            price_cell = row.select_one("td.used_price .js-price")
            price_str = price_cell.text.strip() if price_cell else None
            price = parse_price(price_str)

            current_page_cards.append({
                "product_id": int(product_id),
                "name": name,
                "url": full_url,
                "price": price
            })

        logger.info(f"Page {page}: Found {len(current_page_cards)} cards.")
        all_cards.extend(current_page_cards)

        # Check for cursor for next page
        cursor_input = soup.find("input", {"name": "cursor"})
        if cursor_input:
            cursor = cursor_input.get("value")
            page += 1
        else:
            break

    return all_cards


def scrape_card_details(card_url):
    """Visit card page and extract detailed metadata."""
    html = fetch_page(card_url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")
    data = {}

    # 1. Product ID
    product_id = None
    details_table = soup.select_one("#itemdetails table")
    if details_table:
        for tr in details_table.find_all("tr"):
            if "PriceCharting ID" in tr.get_text():
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    text_val = tds[1].get_text().strip()
                    if text_val.isdigit():
                        product_id = int(text_val)
                        break

    if not product_id:
        for tr in soup.find_all("tr"):
            if "PriceCharting ID" in tr.get_text():
                text = tr.get_text()
                match = re.search(r'PriceCharting ID:?\s*(\d+)', text)
                if match:
                    product_id = int(match.group(1))
                    break

    data["product_id"] = product_id

    # 2. Image URL
    img = soup.select_one('div.cover img')
    if img:
        data["image_url"] = img.get("src")
    else:
        img = soup.select_one('img[itemprop="image"]')
        data["image_url"] = img.get("src") if img else None

    # 3. Market Price
    price_cell = soup.find("td", id="used_price")
    market_price = None
    if price_cell:
        span = price_cell.find("span", class_="js-price")
        if span:
            market_price = parse_price(span.get_text())

    data["market_price"] = market_price

    return data


def parse_card_name_number(full_name):
    """Split name into name and number (after #)."""
    if "#" in full_name:
        parts = full_name.rsplit("#", 1)
        name = parts[0].strip()
        number = parts[1].strip()
        return name, number
    return full_name, None


def process_card(group_id, card, i, total):
    """Process a single card - scrape details and prepare for database."""
    card_url = card["url"]

    # Random sleep to avoid burst patterns
    time.sleep(random.uniform(0.5, 1.5))

    logger.info(f"[{i}/{total}] Scraping: {card['name']}")
    details = scrape_card_details(card_url)

    if not details or not details["product_id"]:
        logger.warning(f"Could not scrape details for {card['name']} ({card_url})")
        return None

    market_price = details["market_price"]

    # Skip if no price
    if market_price is None:
        logger.warning(f"No price for {card['name']}, skipping")
        return None

    clean_name, number = parse_card_name_number(card["name"])
    product_id = details["product_id"]

    return {
        "variant_key": f"{product_id}:Normal",
        "name": clean_name,
        "number": number,
        "group_id": group_id,
        "market_price": market_price,
        "image": details["image_url"],
        "pricecharting_url": card_url,
        "product_id": product_id,
    }


def get_empty_sets():
    """Find sets that have a set_url but no products."""
    logger.info("Finding sets with no products...")

    # Get all groups with set_url
    groups_response = (
        supabase.table("groups")
        .select("id, name, set_url")
        .not_.is_("set_url", "null")
        .execute()
    )

    if not groups_response.data:
        return []

    # Count products per group
    empty_sets = []
    for group in groups_response.data:
        count_response = (
            supabase.table("products")
            .select("id", count="exact")
            .eq("group_id", group["id"])
            .execute()
        )

        product_count = count_response.count if count_response.count else 0

        if product_count == 0:
            empty_sets.append(group)
            logger.info(f"  Empty set found: {group['name']}")

    return empty_sets


def process_set(group_id, group_name, set_url, dry_run=False):
    """Process a single set - scrape all cards and add to database."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing: {group_name}")
    logger.info(f"URL: {set_url}")
    logger.info(f"Group ID: {group_id}")
    logger.info(f"{'='*60}")

    # 1. Get list of cards from set page
    cards_list = scrape_set_cards_list(set_url)
    logger.info(f"Found {len(cards_list)} cards in set listing.")

    if not cards_list:
        logger.warning("No cards found - page structure may have changed")
        return 0

    # 2. Filter to cards with valid prices
    cards_with_price = [c for c in cards_list if c["price"] is not None]
    logger.info(f"Cards with prices: {len(cards_with_price)}")

    if dry_run:
        logger.info("=== DRY RUN - Would add these cards: ===")
        for card in cards_with_price[:10]:
            logger.info(f"  + {card['name']} (${card['price']:.2f})")
        if len(cards_with_price) > 10:
            logger.info(f"  ... and {len(cards_with_price) - 10} more")
        return len(cards_with_price)

    # 3. Scrape detailed info for each card (multithreaded)
    products_to_add = []
    max_workers = 3

    def process_wrapper(args):
        idx, card = args
        return process_card(group_id, card, idx, len(cards_with_price))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(process_wrapper, enumerate(cards_with_price, 1)))

    products_to_add = [r for r in results if r is not None]
    logger.info(f"Successfully scraped {len(products_to_add)} cards with full details.")

    # 4. Insert into products table
    if products_to_add:
        try:
            logger.info(f"Inserting {len(products_to_add)} products into database...")

            # Batch insert in chunks of 50
            batch_size = 50
            for i in range(0, len(products_to_add), batch_size):
                batch = products_to_add[i:i + batch_size]

                # Prepare payloads (only include fields that exist in products table)
                payloads = []
                for p in batch:
                    payload = {
                        "variant_key": p["variant_key"],
                        "name": p["name"],
                        "number": p["number"],
                        "group_id": p["group_id"],
                        "market_price": p["market_price"],
                        "image": p["image"],
                        "pricecharting_url": p["pricecharting_url"],
                    }
                    payloads.append(payload)

                supabase.table("products").upsert(
                    payloads,
                    on_conflict="variant_key"
                ).execute()

                logger.info(f"  Inserted batch {i // batch_size + 1} ({len(batch)} cards)")

            logger.info(f"Successfully added {len(products_to_add)} cards to {group_name}")

        except Exception as e:
            logger.error(f"Error inserting products: {e}")
            return 0

    return len(products_to_add)


def main():
    parser = argparse.ArgumentParser(description="Backfill cards for new Pokemon sets")
    parser.add_argument("--dry-run", action="store_true", help="Preview without adding")
    parser.add_argument("--set-id", type=str, help="Specific Group ID to process")
    parser.add_argument("--max-sets", type=int, default=None, help="Maximum number of sets to process")
    args = parser.parse_args()

    logger.info("Starting New Set Card Backfill...")

    if args.set_id:
        # Process specific set
        response = (
            supabase.table("groups")
            .select("id, name, set_url")
            .eq("id", args.set_id)
            .execute()
        )

        if not response.data:
            logger.error(f"Set with ID {args.set_id} not found")
            return

        sets_to_process = response.data
    else:
        # Find all empty sets
        sets_to_process = get_empty_sets()

    logger.info(f"\nFound {len(sets_to_process)} sets to backfill.")

    if args.max_sets:
        sets_to_process = sets_to_process[:args.max_sets]
        logger.info(f"Limited to {args.max_sets} sets.")

    if not sets_to_process:
        logger.info("No empty sets found - all sets have products!")
        return

    total_cards_added = 0

    for i, group in enumerate(sets_to_process, 1):
        logger.info(f"\n[{i}/{len(sets_to_process)}] Processing set...")

        cards_added = process_set(
            group["id"],
            group["name"],
            group["set_url"],
            dry_run=args.dry_run
        )

        total_cards_added += cards_added

        # Add delay between sets
        if i < len(sets_to_process):
            time.sleep(5)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Sets processed: {len(sets_to_process)}")
    logger.info(f"Total cards added: {total_cards_added}")
    if args.dry_run:
        logger.info("(DRY RUN - no actual changes made)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

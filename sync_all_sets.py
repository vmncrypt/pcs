#!/usr/bin/env python3
"""
Sync all Pokemon sets from PriceCharting to Supabase.

This script scrapes the PriceCharting Pokemon category page,
discovers all sets, and adds any new ones to the groups table.

Usage:
    python sync_all_sets.py
    python sync_all_sets.py --dry-run  # Preview without adding
"""

import os
import argparse
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

PRICECHARTING_URL = "https://www.pricecharting.com/category/pokemon-cards"


def fetch_page(url):
    """Fetch HTML content from the given URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Error fetching URL {url}: {e}")
        return None


def extract_all_sets(html_content):
    """Extract all Pokemon sets from HTML."""
    soup = BeautifulSoup(html_content, "lxml")
    set_links = soup.find_all("a", href=True)

    sets = []
    seen_names = set()

    for link in set_links:
        href = link['href']
        text = link.text.strip()

        # Match Pokemon set links (format: /console/pokemon-*)
        if href.startswith("/console/pokemon-"):
            # Skip if empty or already seen
            if not text or text in seen_names:
                continue

            # Skip non-set pages (like "Pokemon Cards" main category)
            if text == "Pokemon Cards":
                continue

            full_url = "https://www.pricecharting.com" + href

            sets.append({
                "name": text,
                "set_url": full_url
            })
            seen_names.add(text)

    return sets


def get_existing_groups():
    """Fetch all existing set names from the groups table."""
    try:
        all_groups = []
        offset = 0
        limit = 1000

        while True:
            response = (
                supabase.table("groups")
                .select("name, set_url")
                .range(offset, offset + limit - 1)
                .execute()
            )
            if not response.data:
                break
            all_groups.extend(response.data)
            if len(response.data) < limit:
                break
            offset += limit

        # Return map of name -> set_url
        return {item["name"]: item.get("set_url") for item in all_groups}
    except Exception as e:
        logger.error(f"Error fetching existing groups: {e}")
        return {}


def sync_sets(scraped_sets, dry_run=False):
    """Sync scraped sets to the groups table."""
    existing_groups = get_existing_groups()
    existing_names = set(existing_groups.keys())

    logger.info(f"Found {len(existing_names)} existing sets in database")

    sets_to_add = []
    sets_to_update = []

    for s in scraped_sets:
        name = s["name"]
        url = s["set_url"]

        if name not in existing_names:
            sets_to_add.append(s)
        elif existing_groups[name] != url and url:
            # Existing group but URL is missing or different
            sets_to_update.append({
                "name": name,
                "set_url": url
            })

    logger.info(f"New sets to add: {len(sets_to_add)}")
    logger.info(f"Existing sets to update URL: {len(sets_to_update)}")

    if dry_run:
        logger.info("=== DRY RUN - No changes will be made ===")
        if sets_to_add:
            logger.info("Sets that would be added:")
            for s in sets_to_add[:20]:  # Show first 20
                logger.info(f"  + {s['name']}")
            if len(sets_to_add) > 20:
                logger.info(f"  ... and {len(sets_to_add) - 20} more")
        if sets_to_update:
            logger.info("Sets that would be updated:")
            for s in sets_to_update[:10]:
                logger.info(f"  ~ {s['name']}")
        return

    # 1. Insert New Sets (let Supabase auto-generate UUIDs)
    if sets_to_add:
        try:
            logger.info(f"Adding {len(sets_to_add)} new sets...")

            # Insert in batches of 50
            batch_size = 50
            for i in range(0, len(sets_to_add), batch_size):
                batch = sets_to_add[i:i + batch_size]
                payloads = [{"name": s["name"], "set_url": s["set_url"]} for s in batch]
                supabase.table("groups").insert(payloads).execute()
                logger.info(f"  Inserted batch {i // batch_size + 1} ({len(batch)} sets)")

            logger.info("✅ Successfully added new sets.")
        except Exception as e:
            logger.error(f"❌ Error inserting new sets: {e}")
    else:
        logger.info("No new sets to add.")

    # 2. Update Existing Sets (if URL missing/changed)
    if sets_to_update:
        logger.info(f"Updating {len(sets_to_update)} existing sets with URLs...")
        for update in sets_to_update:
            try:
                supabase.table("groups").update({
                    "set_url": update["set_url"]
                }).eq("name", update["name"]).execute()
            except Exception as e:
                logger.error(f"❌ Error updating set {update['name']}: {e}")
        logger.info("✅ Updates complete.")
    else:
        logger.info("No existing sets needed URL updates.")


def main():
    parser = argparse.ArgumentParser(description="Sync all Pokemon sets from PriceCharting")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    args = parser.parse_args()

    logger.info("🚀 Starting Pokemon Set Sync...")
    logger.info(f"Source: {PRICECHARTING_URL}")

    # 1. Scrape
    html = fetch_page(PRICECHARTING_URL)
    if not html:
        logger.error("Failed to fetch PriceCharting page")
        return

    all_sets = extract_all_sets(html)
    logger.info(f"Found {len(all_sets)} sets on PriceCharting")

    if not all_sets:
        logger.warning("No sets found - page structure may have changed")
        return

    # 2. Sync
    sync_sets(all_sets, dry_run=args.dry_run)
    logger.info("✨ Sync Complete.")


if __name__ == "__main__":
    main()

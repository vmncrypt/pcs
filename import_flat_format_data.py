#!/usr/bin/env python3
"""
Import Pokemon data from flat format JSON

This script handles the flat format where each card has:
{
  "card": "Charizard #4",
  "price": 100,
  "grade9": 200,
  "psa10": 500,
  "image": "https://...",
  "series": "Pokemon Base Set",
  "language": "English",
  "id": "base-set-4"
}
"""

import os
import json
import re
from supabase import create_client

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Path to flat format data
DATA_PATH = "/Users/leon/Downloads/pokemon-cards-final-data-with-ids.json"


def parse_card_name_and_number(card_string):
    """Parse card string to extract name and number."""
    if '#' in card_string:
        parts = card_string.rsplit('#', 1)
        name = parts[0].strip()
        number = parts[1].strip()
        return name, number
    else:
        return card_string.strip(), None


def create_variant_key(series_name, card_number):
    """Create a unique variant_key for the card."""
    slug = series_name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'^pokemon-', '', slug)

    if card_number:
        number_slug = card_number.lower().replace(' ', '-')
        return f"{slug}-{number_slug}"
    else:
        return slug


def estimate_rarity(price, grade9, psa10):
    """Estimate rarity based on price."""
    if price is None or price == 0:
        return "Common"

    if price >= 100:
        return "Ultra Rare"
    elif price >= 15:
        return "Rare"
    elif price >= 5:
        return "Uncommon"
    else:
        return "Common"


def import_flat_data():
    """Import data from flat format"""
    print("🔄 Importing Pokemon data from flat format")
    print("=" * 60)

    # Load data
    print(f"\n📂 Loading data from: {DATA_PATH}")
    with open(DATA_PATH, 'r', encoding='utf-8') as f:
        cards_data = json.load(f)

    print(f"✅ Loaded {len(cards_data):,} cards")

    # Group by series
    print("\n📊 Grouping cards by series...")
    series_map = {}
    for card in cards_data:
        series_name = card.get('series', 'Unknown')
        if series_name not in series_map:
            series_map[series_name] = []
        series_map[series_name].append(card)

    print(f"✅ Found {len(series_map)} unique series")

    # Fetch existing groups
    print("\n📥 Fetching existing groups from Supabase...")
    groups_response = supabase.table("groups").select("id, name").execute()
    existing_groups = {g['name']: g['id'] for g in groups_response.data}
    print(f"✅ Found {len(existing_groups)} existing groups")

    # Find groups with no products (empty groups)
    print("\n🔍 Finding empty groups...")
    empty_groups = []
    for group_name, group_id in existing_groups.items():
        products_count = supabase.table("products").select("id", count="exact").eq("group_id", group_id).execute()
        if products_count.count == 0:
            empty_groups.append(group_name)

    print(f"✅ Found {len(empty_groups)} empty groups to populate")

    if not empty_groups:
        print("\n✅ All groups already have products! Nothing to import.")
        return

    # Track statistics
    total_groups_created = 0
    total_products_added = 0
    total_eligible = 0
    total_skipped = 0

    # Process each series (only empty groups)
    for series_name, cards in sorted(series_map.items()):
        # Skip if not an empty group
        if series_name not in empty_groups:
            continue

        print(f"\n📦 Processing: {series_name} ({len(cards)} cards)")

        # Get group (we know it exists because we filtered for empty groups)
        if series_name in existing_groups:
            group_id = existing_groups[series_name]
            print(f"   Using existing empty group")
        else:
            # This shouldn't happen but handle it anyway
            group_response = supabase.table("groups").insert({
                "name": series_name
            }).execute()

            if not group_response.data:
                print(f"   ❌ Failed to create group")
                continue

            group_id = group_response.data[0]['id']
            existing_groups[series_name] = group_id
            total_groups_created += 1
            print(f"   ✅ Created new group")

        # Check existing products in this group
        existing_products_response = supabase.table("products").select("variant_key").eq("group_id", group_id).execute()
        existing_variant_keys = set(p['variant_key'] for p in existing_products_response.data)

        # Build products (deduplicate by variant_key)
        products_dict = {}

        for card in cards:
            card_string = card.get('card', '')
            price = card.get('price', 0)
            grade9 = card.get('grade9', 0)
            psa10 = card.get('psa10', 0)

            name, number = parse_card_name_and_number(card_string)
            variant_key = create_variant_key(series_name, number)

            # Skip if already exists
            if variant_key in existing_variant_keys:
                total_skipped += 1
                continue

            rarity = estimate_rarity(price, grade9, psa10)

            product = {
                'group_id': group_id,
                'variant_key': variant_key,
                'name': name,
                'number': number,
                'market_price': float(price) if price else 0,
                'rarity': rarity
            }

            products_dict[variant_key] = product

        if not products_dict:
            print(f"   ⚠️  No new products to add (all exist)")
            continue

        # Insert products in batches
        products_to_insert = list(products_dict.values())
        batch_size = 100

        products_inserted = 0

        for i in range(0, len(products_to_insert), batch_size):
            batch = products_to_insert[i:i + batch_size]

            try:
                insert_response = supabase.table("products").insert(batch).execute()
                products_inserted += len(batch)
                print(f"   Inserted {products_inserted}/{len(products_to_insert)} products...")
            except Exception as e:
                print(f"   ❌ Error inserting batch: {e}")

        total_products_added += products_inserted

        # Count eligible products
        eligible = sum(1 for p in products_to_insert if p['market_price'] >= 15 and (p['rarity'] or p['number']))
        total_eligible += eligible

        print(f"   ✅ Added {products_inserted} new products ({eligible} eligible)")

    # Summary
    print("\n" + "=" * 60)
    print("✅ Import Complete!")
    print("=" * 60)
    print(f"Series in file: {len(series_map)}")
    print(f"New groups created: {total_groups_created}")
    print(f"New products added: {total_products_added}")
    print(f"Products skipped (already exist): {total_skipped}")
    print(f"Eligible products added: {total_eligible}")
    print("=" * 60)

    if total_eligible > 0:
        print("\n💡 Next steps:")
        print("   1. Run sync_eligible_products.py to add to scraping queue")
        print("   2. Wait for GitHub Actions to scrape graded sales")
        print("   3. Run export_to_app_format.py to update app data")


if __name__ == "__main__":
    import_flat_data()

#!/usr/bin/env python3
"""
Import missing sets from pokemon_enriched_series_data.json

This script:
1. Compares enriched series data with what's already in Supabase
2. Imports missing groups and their products
3. Maintains the same data structure as the original import
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

# Paths
ENRICHED_DATA_PATH = "/Users/leon/Actual/Apps/Prod/BankTCG/assets/games/pokemon_enriched_series_data.json"
BASE_DATA_PATH = "/Users/leon/Actual/Apps/Prod/BankTCG/assets/games/pokemon-cards-base-data.json"


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


def import_missing_sets():
    """Import missing sets from enriched data"""
    print("🔄 Importing missing sets from enriched series data")
    print("=" * 60)

    # Load enriched data
    print(f"\n📂 Loading enriched data: {ENRICHED_DATA_PATH}")
    with open(ENRICHED_DATA_PATH, 'r', encoding='utf-8') as f:
        enriched_data = json.load(f)

    # Load base data to get image URLs
    print(f"📂 Loading base data for images: {BASE_DATA_PATH}")
    with open(BASE_DATA_PATH, 'r', encoding='utf-8') as f:
        base_data = json.load(f)

    # Build image lookup
    print("🖼️  Building image lookup...")
    image_lookup = {}
    for series in base_data:
        series_name = series['name']
        for card in series['cards']:
            card_string = card.get('card', '')
            image_url = card.get('image')
            if image_url:
                name, number = parse_card_name_and_number(card_string)
                variant_key = create_variant_key(series_name, number)
                image_lookup[variant_key] = image_url

    print(f"✅ Found {len(image_lookup):,} images")

    # Fetch existing groups from Supabase
    print("\n📥 Fetching existing groups from Supabase...")
    groups_response = supabase.table("groups").select("name").execute()
    existing_groups = set(g['name'] for g in groups_response.data)
    print(f"✅ Found {len(existing_groups)} existing groups")

    # Find missing sets
    enriched_names = set(s['name'] for s in enriched_data)
    missing_names = enriched_names - existing_groups

    print(f"\n📊 Found {len(missing_names)} missing sets to import")

    if not missing_names:
        print("\n✅ No missing sets found - all sets already imported!")
        return

    # Show missing sets
    print("\nMissing sets:")
    for name in sorted(missing_names)[:10]:
        print(f"  - {name}")
    if len(missing_names) > 10:
        print(f"  ... and {len(missing_names) - 10} more")

    # Import missing sets
    total_groups_added = 0
    total_products_added = 0
    total_eligible = 0

    for series in enriched_data:
        series_name = series['name']

        # Skip if already exists
        if series_name in existing_groups:
            continue

        print(f"\n📦 Importing: {series_name}")

        # Create group
        group_response = supabase.table("groups").insert({
            "name": series_name
        }).execute()

        if not group_response.data:
            print(f"   ❌ Failed to create group")
            continue

        group_id = group_response.data[0]['id']
        total_groups_added += 1

        # Process cards
        cards = series.get('cards', [])
        if not cards:
            print(f"   ⚠️  No cards found")
            continue

        print(f"   Found {len(cards)} cards")

        # Build products (deduplicate by variant_key)
        products_dict = {}

        for card in cards:
            card_string = card.get('card', '')
            price = card.get('price', 0)
            grade9 = card.get('grade9', 0)
            psa10 = card.get('psa10', 0)
            image_url = card.get('image')

            name, number = parse_card_name_and_number(card_string)
            variant_key = create_variant_key(series_name, number)

            # Check image lookup if not in enriched data
            if not image_url and variant_key in image_lookup:
                image_url = image_lookup[variant_key]

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

        print(f"   ✅ Imported {products_inserted} products ({eligible} eligible)")

    # Summary
    print("\n" + "=" * 60)
    print("✅ Import Complete!")
    print("=" * 60)
    print(f"New groups added: {total_groups_added}")
    print(f"New products added: {total_products_added}")
    print(f"Eligible products added: {total_eligible}")
    print("=" * 60)

    print("\n💡 Next steps:")
    print("   1. Run sync_eligible_products.py to update scraping queue")
    print("   2. Run export_to_app_format.py to update app data")


if __name__ == "__main__":
    import_missing_sets()

#!/usr/bin/env python3
"""
Update product prices from BankTCG source data

⚠️  LOCAL USE ONLY - This script requires access to local BankTCG files
    Do not run in GitHub Actions or CI/CD environments

This script:
1. Reads the latest pokemon-cards-final-data-with-ids.json from BankTCG app
2. Updates market_price in Supabase for existing products
3. Detects cards crossing the $15 eligibility threshold
4. Updates prices to reflect latest market data

Run this locally when you update your BankTCG app data and want to sync
those price changes back to Supabase.
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

# Path to Pokemon data
POKEMON_DATA_PATH = "/Users/leon/Actual/Apps/Prod/BankTCG/assets/games/pokemon-cards-final-data-with-ids.json"


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


def update_prices():
    """Main update function"""
    print("🔄 Starting price update from BankTCG source data")
    print("=" * 60)

    # Load Pokemon data
    print(f"\n📂 Loading data from: {POKEMON_DATA_PATH}")
    with open(POKEMON_DATA_PATH, 'r', encoding='utf-8') as f:
        pokemon_data = json.load(f)

    print(f"✅ Loaded {len(pokemon_data)} series")

    # Track statistics
    total_cards_in_source = 0
    products_updated = 0
    products_created = 0
    products_price_changed = 0
    errors = 0

    # Build a map of variant_key -> price from source data
    print("\n📊 Building price map from source data...")
    price_map = {}

    for series in pokemon_data:
        series_name = series['name']

        for card in series['cards']:
            card_string = card.get('card', '')
            price = card.get('price', 0)

            name, number = parse_card_name_and_number(card_string)
            variant_key = create_variant_key(series_name, number)

            # Store the latest price (in case of duplicates, last one wins)
            price_map[variant_key] = float(price) if price else 0
            total_cards_in_source += 1

    print(f"✅ Found {len(price_map):,} unique products in source data")
    print(f"   ({total_cards_in_source:,} total card entries)")

    # Fetch all products from database
    print("\n📥 Fetching all products from database...")
    all_products = []
    limit = 1000
    offset = 0

    while True:
        response = supabase.table("products").select("variant_key, market_price").range(offset, offset + limit - 1).execute()

        if not response.data:
            break

        all_products.extend(response.data)

        if len(response.data) < limit:
            break

        offset += limit
        print(f"   Fetched {len(all_products)} products...")

    print(f"✅ Fetched {len(all_products):,} products from database")

    # Update prices in batches
    print("\n🔄 Updating prices...")
    batch_size = 100
    updates = []

    for product in all_products:
        variant_key = product['variant_key']
        current_price = float(product['market_price']) if product['market_price'] else 0

        if variant_key in price_map:
            new_price = price_map[variant_key]

            if new_price != current_price:
                updates.append({
                    'variant_key': variant_key,
                    'market_price': new_price
                })
                products_price_changed += 1

                # Show significant price changes
                if current_price >= 15 and new_price < 15:
                    print(f"   ⬇️  {variant_key}: ${current_price:.2f} → ${new_price:.2f} (no longer eligible)")
                elif current_price < 15 and new_price >= 15:
                    print(f"   ⬆️  {variant_key}: ${current_price:.2f} → ${new_price:.2f} (now eligible!)")
                elif abs(new_price - current_price) >= 10:
                    print(f"   📈 {variant_key}: ${current_price:.2f} → ${new_price:.2f}")

    print(f"\n   Found {products_price_changed:,} products with price changes")

    # Apply updates in batches
    if updates:
        print(f"\n💾 Applying {len(updates):,} price updates...")

        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]

            try:
                for update in batch:
                    supabase.table("products").update({
                        'market_price': update['market_price']
                    }).eq('variant_key', update['variant_key']).execute()

                products_updated += len(batch)
                print(f"   Updated {products_updated}/{len(updates)} products...")

            except Exception as e:
                print(f"   ❌ Error updating batch: {e}")
                errors += len(batch)

    # Summary
    print("\n" + "=" * 60)
    print("✅ Price Update Complete!")
    print("=" * 60)
    print(f"Products in source data: {len(price_map):,}")
    print(f"Products in database: {len(all_products):,}")
    print(f"Price changes detected: {products_price_changed:,}")
    print(f"Products updated: {products_updated:,}")
    print(f"Errors: {errors}")
    print("=" * 60)

    # Check new eligibility
    print("\n📊 Checking eligibility after price update...")
    eligible = supabase.table("products").select("id", count="exact").gte("market_price", 15).execute()
    print(f"✅ Eligible products (>= $15): {eligible.count:,}")

    print("\n💡 Next step: Run sync_eligible_products.py to update the scraping queue")
    print("   python3 sync_eligible_products.py")


if __name__ == "__main__":
    update_prices()

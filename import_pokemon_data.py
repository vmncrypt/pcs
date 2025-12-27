#!/usr/bin/env python3
"""
Import Pokemon card data from BankTCG JSON file into Supabase

This script:
1. Reads pokemon-cards-final-data-with-ids.json
2. Creates groups (series) in Supabase
3. Creates products (cards) in Supabase
4. Maps card data to the expected schema
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
    """
    Parse card string to extract name and number.

    Examples:
      "Greninja #SWSH144" -> ("Greninja", "SWSH144")
      "Charizard #4" -> ("Charizard", "4")
      "Pikachu Birthday #24" -> ("Pikachu Birthday", "24")
      "Mew ex #151" -> ("Mew ex", "151")
    """
    # Split by last occurrence of #
    if '#' in card_string:
        parts = card_string.rsplit('#', 1)
        name = parts[0].strip()
        number = parts[1].strip()
        return name, number
    else:
        # No number found
        return card_string.strip(), None


def create_variant_key(series_name, card_number):
    """
    Create a unique variant_key for the card.

    Format: {series_slug}-{number}
    Example: pokemon-celebrations-swsh144
    """
    # Create a slug from series name
    slug = series_name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)  # Remove special chars
    slug = re.sub(r'[\s_]+', '-', slug)    # Replace spaces with hyphens
    slug = re.sub(r'^pokemon-', '', slug)  # Remove "pokemon-" prefix if exists

    if card_number:
        number_slug = card_number.lower().replace(' ', '-')
        return f"{slug}-{number_slug}"
    else:
        return slug


def estimate_rarity(price, grade9, psa10):
    """
    Estimate rarity based on market price.
    This is a simple heuristic - adjust as needed.
    """
    if price is None or price == 0:
        return "Common"

    if price >= 100:
        return "Ultra Rare"
    elif price >= 50:
        return "Secret Rare"
    elif price >= 20:
        return "Rare Holo"
    elif price >= 5:
        return "Rare"
    elif price >= 2:
        return "Uncommon"
    else:
        return "Common"


def import_data():
    """Main import function"""
    print("🚀 Starting Pokemon card import to Supabase")
    print("=" * 60)

    # Load Pokemon data
    print(f"\n📂 Loading data from: {POKEMON_DATA_PATH}")
    with open(POKEMON_DATA_PATH, 'r', encoding='utf-8') as f:
        pokemon_data = json.load(f)

    print(f"✅ Loaded {len(pokemon_data)} series")

    # Count total cards
    total_cards = sum(len(series['cards']) for series in pokemon_data)
    print(f"✅ Found {total_cards:,} total cards")

    # Create groups and products
    groups_created = 0
    products_created = 0
    products_skipped = 0

    for series_idx, series in enumerate(pokemon_data, 1):
        series_name = series['name']

        print(f"\n[{series_idx}/{len(pokemon_data)}] Processing: {series_name}")
        print(f"   Cards in series: {len(series['cards'])}")

        # Create or get group
        try:
            # Check if group exists
            existing_group = supabase.table("groups").select("id").eq("name", series_name).execute()

            if existing_group.data and len(existing_group.data) > 0:
                group_id = existing_group.data[0]['id']
                print(f"   ✓ Group already exists (ID: {group_id[:8]}...)")
            else:
                # Create group
                new_group = supabase.table("groups").insert({
                    "name": series_name
                }).execute()
                group_id = new_group.data[0]['id']
                groups_created += 1
                print(f"   ✓ Created group (ID: {group_id[:8]}...)")

        except Exception as e:
            print(f"   ❌ Error creating group: {e}")
            continue

        # Process cards in batches
        batch_size = 100
        cards = series['cards']

        for i in range(0, len(cards), batch_size):
            batch = cards[i:i + batch_size]
            products_dict = {}  # Use dict to auto-deduplicate by variant_key

            for card in batch:
                card_string = card.get('card', '')
                price = card.get('price', 0)
                grade9 = card.get('grade9')
                psa10 = card.get('psa10')
                image = card.get('image')

                # Parse name and number
                name, number = parse_card_name_and_number(card_string)

                # Create variant key
                variant_key = create_variant_key(series_name, number)

                # Estimate rarity
                rarity = estimate_rarity(price, grade9, psa10)

                # Build product object (will overwrite duplicates)
                products_dict[variant_key] = {
                    "name": name,
                    "number": number,
                    "variant_key": variant_key,
                    "group_id": group_id,
                    "market_price": float(price) if price else 0,
                    "rarity": rarity
                }

            products_to_insert = list(products_dict.values())

            # Bulk insert/upsert
            try:
                result = supabase.table("products").upsert(
                    products_to_insert,
                    on_conflict="variant_key"
                ).execute()

                products_created += len(result.data)
                print(f"   ✓ Inserted batch {i//batch_size + 1}/{(len(cards) + batch_size - 1)//batch_size} ({len(batch)} cards)")

            except Exception as e:
                print(f"   ❌ Error inserting batch: {e}")
                products_skipped += len(batch)

    # Summary
    print("\n" + "=" * 60)
    print("✅ Import Complete!")
    print("=" * 60)
    print(f"Groups created: {groups_created}")
    print(f"Products created/updated: {products_created}")
    print(f"Products skipped (errors): {products_skipped}")
    print("=" * 60)

    # Check eligibility
    print("\n📊 Checking eligibility (market_price >= $15)...")
    eligible = supabase.table("products").select("id", count="exact").gte("market_price", 15).execute()
    print(f"✅ Eligible products: {eligible.count:,}")

    print("\n✨ Ready to run: python sync_eligible_products.py")


if __name__ == "__main__":
    import_data()

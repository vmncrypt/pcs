#!/usr/bin/env python3
"""
Import cards from a JSON file to Supabase.

Usage:
    python import_cards_from_json.py my_cards.json

JSON Format:
[
  {
    "name": "Pokemon Scarlet & Violet - New Set",
    "cards": [
      {
        "card": "Pikachu ex #025",
        "price": 45.99,
        "grade9": 120.00,
        "psa10": 350.00,
        "image": "https://example.com/image.jpg"
      }
    ]
  }
]
"""

import os
import sys
import json
import re
from supabase import create_client
from dotenv import load_dotenv

# Load environment
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def parse_card_name_and_number(card_string):
    """Parse 'Pikachu ex #025' -> ('Pikachu ex', '025')"""
    if '#' in card_string:
        parts = card_string.rsplit('#', 1)
        return parts[0].strip(), parts[1].strip()
    return card_string.strip(), None


def create_variant_key(series_name, card_number):
    """Create unique key: pokemon-celebrations-swsh144"""
    slug = series_name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'^pokemon-', '', slug)

    if card_number:
        number_slug = card_number.lower().replace(' ', '-')
        return f"{slug}-{number_slug}"
    return slug


def estimate_rarity(price):
    """Estimate rarity based on price"""
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
    return "Common"


def import_from_json(json_path):
    """Import cards from JSON file"""
    print(f"📂 Loading: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"✅ Found {len(data)} series\n")

    total_imported = 0
    total_skipped = 0

    for series in data:
        series_name = series['name']
        cards = series.get('cards', [])

        print(f"📦 Processing: {series_name}")
        print(f"   Cards: {len(cards)}")

        # Get or create group
        try:
            result = supabase.table("groups").select("id").eq("name", series_name).execute()

            if result.data:
                group_id = result.data[0]['id']
                print(f"   ✓ Found group (ID: {group_id[:8]}...)")
            else:
                new_group = supabase.table("groups").insert({"name": series_name}).execute()
                group_id = new_group.data[0]['id']
                print(f"   ✓ Created group (ID: {group_id[:8]}...)")

        except Exception as e:
            print(f"   ❌ Error with group: {e}")
            continue

        # Import cards
        products_dict = {}

        for card in cards:
            card_string = card.get('card', '')
            price = card.get('price', 0)
            image = card.get('image')

            name, number = parse_card_name_and_number(card_string)
            variant_key = create_variant_key(series_name, number)
            rarity = estimate_rarity(price)

            products_dict[variant_key] = {
                "name": name,
                "number": number,
                "variant_key": variant_key,
                "group_id": group_id,
                "market_price": float(price) if price else 0,
                "rarity": rarity,
                "image": image
            }

        products_to_insert = list(products_dict.values())

        try:
            result = supabase.table("products").upsert(
                products_to_insert,
                on_conflict="variant_key"
            ).execute()

            imported = len(result.data)
            total_imported += imported
            print(f"   ✅ Imported {imported} cards\n")

        except Exception as e:
            print(f"   ❌ Error importing cards: {e}\n")
            total_skipped += len(products_to_insert)

    print("=" * 60)
    print(f"✅ Import complete!")
    print(f"   Imported: {total_imported} cards")
    if total_skipped > 0:
        print(f"   Skipped: {total_skipped} cards")
    print("\nNext steps:")
    print("   python sync_eligible_products.py")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nExample:")
        print("   python import_cards_from_json.py test_cards.json")
        sys.exit(1)

    json_path = sys.argv[1]

    if not os.path.exists(json_path):
        print(f"❌ File not found: {json_path}")
        sys.exit(1)

    import_from_json(json_path)


if __name__ == "__main__":
    main()

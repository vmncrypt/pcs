#!/usr/bin/env python3
"""
Update product images in Supabase from JSON file.

Usage:
    python update_images_from_json.py phantasmal-flames_cards.json
"""

import os
import sys
import json
import re
from dotenv import load_dotenv
from supabase import create_client

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


def update_images_from_json(json_path):
    """Update product images from JSON file"""
    print(f"📂 Loading: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    updated_count = 0
    skipped_count = 0

    for series in data:
        series_name = series['name']
        cards = series.get('cards', [])

        print(f"\n📦 Processing: {series_name}")
        print(f"   Cards: {len(cards)}")

        for card in cards:
            card_string = card.get('card', '')
            image_url = card.get('image', '')

            if not image_url:
                continue

            # Parse card to get variant_key
            name, number = parse_card_name_and_number(card_string)
            variant_key = create_variant_key(series_name, number)

            try:
                # Update the product with the image URL
                result = supabase.table('products').update({
                    'image': image_url
                }).eq('variant_key', variant_key).execute()

                if result.data:
                    updated_count += 1
                else:
                    skipped_count += 1

            except Exception as e:
                print(f"   ❌ Error updating {card_string}: {e}")
                skipped_count += 1

        print(f"   ✅ Updated {updated_count} images")

    print(f"\n{'=' * 60}")
    print(f"✅ Image update complete!")
    print(f"   Updated: {updated_count} cards")
    if skipped_count > 0:
        print(f"   Skipped: {skipped_count} cards")
    print(f"\nNext step:")
    print(f"   python export_to_app_format.py")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nExample:")
        print("   python update_images_from_json.py phantasmal-flames_cards.json")
        sys.exit(1)

    json_path = sys.argv[1]

    if not os.path.exists(json_path):
        print(f"❌ File not found: {json_path}")
        sys.exit(1)

    # Test if image column exists
    try:
        supabase.table('products').select('id, image').limit(1).execute()
    except Exception as e:
        if 'image' in str(e) and 'column' in str(e).lower():
            print("❌ Image column doesn't exist in products table")
            print("\nRun this SQL in Supabase SQL Editor first:")
            print("   ALTER TABLE products ADD COLUMN IF NOT EXISTS image TEXT;")
            sys.exit(1)
        else:
            raise

    update_images_from_json(json_path)


if __name__ == "__main__":
    main()

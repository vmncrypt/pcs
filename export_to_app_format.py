#!/usr/bin/env python3
"""
Export Supabase data to BankTCG app format

This script:
1. Fetches data from Supabase (products, groups, graded_prices)
2. Reads image URLs from original BankTCG source data
3. Converts to your app's JSON format with images
4. Writes to BankTCG assets folder

Run this after scraping completes to update your app's data.
"""

import os
import json
import re
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Output path
OUTPUT_PATH = "/Users/leon/Actual/Apps/Prod/BankTCG/assets/games/pokemon-cards-final-data-with-ids.json"


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
    """Create a unique variant_key for the card (same logic as import)."""
    slug = series_name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'^pokemon-', '', slug)

    if card_number:
        number_slug = card_number.lower().replace(' ', '-')
        return f"{slug}-{number_slug}"
    else:
        return slug


def export_to_app_format():
    """Export data in BankTCG app format"""
    print("🔄 Exporting data from Supabase to app format...")
    print("=" * 60)

    # Images are stored directly in Supabase products.image — no base file needed.
    image_lookup = {}

    # Fetch all groups with explicit ordering for consistency
    print("\n📥 Fetching groups from Supabase...")
    groups_response = supabase.table("groups")\
        .select("id, name")\
        .order('name', desc=False)\
        .execute()
    groups = groups_response.data

    print(f"✅ Found {len(groups)} groups (ordered alphabetically)")

    # Build output data
    output_data = []

    for group in groups:
        print(f"\n📦 Processing: {group['name']}")

        # Fetch products for this group with explicit ordering
        products_response = supabase.table("products")\
            .select("id, variant_key, name, number, market_price, image")\
            .eq("group_id", group['id'])\
            .order('variant_key', desc=False)\
            .execute()
        products = products_response.data

        if not products:
            print(f"   ⚠️  No products found, skipping")
            continue

        print(f"   Found {len(products)} products")

        # Fetch graded prices for all products in this group (batch to avoid URL length limits)
        product_ids = [p['id'] for p in products]
        prices_data = []
        batch_size = 200
        for i in range(0, len(product_ids), batch_size):
            batch_ids = product_ids[i:i + batch_size]
            prices_response = supabase.table("graded_prices").select("product_id, grade, market_price").in_("product_id", batch_ids).execute()
            prices_data.extend(prices_response.data)

        # Build price lookup: {product_id: {grade: price}}
        price_lookup = {}
        for price in prices_data:
            if price['product_id'] not in price_lookup:
                price_lookup[price['product_id']] = {}
            price_lookup[price['product_id']][price['grade']] = price['market_price']

        # Build cards array
        cards = []
        for product in products:
            product_id = product['id']
            variant_key = product['variant_key']
            prices = price_lookup.get(product_id, {})

            card = {
                "supabase_id": product_id,  # ✅ CRITICAL: Stable UUID from Supabase
                "card": f"{product['name']} #{product['number']}" if product['number'] else product['name'],
                "price": float(product['market_price']) if product['market_price'] else 0,
                "grade9": float(prices.get(9, 0)),
                "psa10": float(prices.get(10, 0))
            }

            # Add image URL (prefer Supabase, fallback to original data)
            image_url = product.get('image') or image_lookup.get(variant_key)
            if image_url:
                card["image"] = image_url

            cards.append(card)

        # Add to output
        output_data.append({
            "name": group['name'],
            "cards": cards
        })

        print(f"   ✅ Exported {len(cards)} cards")

    # Write to file
    print(f"\n💾 Writing to: {OUTPUT_PATH}")
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    # Summary and validation
    total_cards = sum(len(group['cards']) for group in output_data)
    cards_with_images = sum(1 for group in output_data for card in group['cards'] if 'image' in card)
    cards_with_ids = sum(1 for group in output_data for card in group['cards'] if 'supabase_id' in card)

    print("\n" + "=" * 60)
    print("✅ Export Complete!")
    print("=" * 60)
    print(f"Groups exported: {len(output_data)}")
    print(f"Total cards: {total_cards}")
    print(f"Cards with Supabase IDs: {cards_with_ids} ({cards_with_ids/total_cards*100:.1f}%)")
    print(f"Cards with images: {cards_with_images} ({cards_with_images/total_cards*100:.1f}%)")
    print(f"Output file: {OUTPUT_PATH}")
    print("=" * 60)

    # Validation check
    if cards_with_ids != total_cards:
        print("\n⚠️  WARNING: Not all cards have Supabase IDs!")
        print(f"Missing IDs: {total_cards - cards_with_ids}")
    else:
        print("\n✅ All cards have stable Supabase UUIDs")


if __name__ == "__main__":
    export_to_app_format()

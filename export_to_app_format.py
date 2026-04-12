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
import argparse
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

BANKTCG_ASSETS = "/Users/leon/Actual/Apps/Prod/BankTCG/assets/games"

# category_id=None means filter WHERE category_id IS NULL (English Pokemon).
# Other games use the same IDs assigned in sync_all_sets.py.
GAME_CONFIGS = {
    "pokemon":   {"category_id": None, "output": f"{BANKTCG_ASSETS}/pokemon-cards-final-data-with-ids.json"},
    "magic":     {"category_id": 1,    "output": f"{BANKTCG_ASSETS}/magic-cards-final-data-with-ids.json"},
    "yugioh":    {"category_id": 2,    "output": f"{BANKTCG_ASSETS}/yugioh-cards-final-data-with-ids.json"},
    "one-piece": {"category_id": 3,    "output": f"{BANKTCG_ASSETS}/one-piece-cards-final-data-with-ids.json"},
}


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


def export_to_app_format(game="pokemon"):
    """Export data in BankTCG app format for the given game."""
    config = GAME_CONFIGS[game]
    category_id = config["category_id"]
    output_path = config["output"]

    print(f"🔄 Exporting {game} data from Supabase to app format...")
    print("=" * 60)

    # Images are stored directly in Supabase products.image — no base file needed.
    image_lookup = {}

    # Fetch groups for this game only, filtered by category_id
    print("\n📥 Fetching groups from Supabase...")
    query = supabase.table("groups").select("id, name").order('name', desc=False)
    if category_id is None:
        query = query.is_("category_id", "null")
    else:
        query = query.eq("category_id", category_id)
    groups_response = query.execute()
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
            prices_response = supabase.table("graded_prices").select("product_id, grade, market_price, psa_pop").in_("product_id", batch_ids).execute()
            prices_data.extend(prices_response.data)

        # Build price lookup: {product_id: {grade: {price, psa_pop}}}
        price_lookup = {}
        for price in prices_data:
            pid = price['product_id']
            if pid not in price_lookup:
                price_lookup[pid] = {}
            price_lookup[pid][price['grade']] = {
                'price': price['market_price'],
                'psa_pop': price.get('psa_pop'),
            }

        # Fetch graded sales in smaller batches to avoid statement timeout
        sales_data = []
        sales_batch_size = 30
        for i in range(0, len(product_ids), sales_batch_size):
            batch_ids = product_ids[i:i + sales_batch_size]
            sales_response = supabase.table("graded_sales")\
                .select("product_id, grade, sale_date, price")\
                .in_("product_id", batch_ids)\
                .order("sale_date", desc=True)\
                .limit(5000)\
                .execute()
            sales_data.extend(sales_response.data)

        # Build sales lookup: {product_id: {grade: [{"date": ..., "price": ...}, ...]}} capped at 100 per grade
        sales_lookup = {}
        for sale in sales_data:
            pid = sale['product_id']
            grade = sale['grade']
            if pid not in sales_lookup:
                sales_lookup[pid] = {}
            if grade not in sales_lookup[pid]:
                sales_lookup[pid][grade] = []
            if len(sales_lookup[pid][grade]) < 100:
                sales_lookup[pid][grade].append({
                    "date": sale['sale_date'],
                    "price": float(sale['price']),
                })

        # Build cards array
        cards = []
        for product in products:
            product_id = product['id']
            variant_key = product['variant_key']
            prices = price_lookup.get(product_id, {})

            def grade_price(g):
                return float(prices[g]['price']) if prices.get(g) and prices[g]['price'] else 0

            def grade_pop(g):
                return prices[g]['psa_pop'] if prices.get(g) and prices[g].get('psa_pop') is not None else None

            card = {
                "supabase_id": product_id,  # ✅ CRITICAL: Stable UUID from Supabase
                "card": f"{product['name']} #{product['number']}" if product['number'] else product['name'],
                "price": float(product['market_price']) if product['market_price'] else 0,
                "grade7": grade_price(7),
                "grade8": grade_price(8),
                "grade9": grade_price(9),
                "psa10": grade_price(10),
            }

            # Only include pop counts when available
            for grade, key in [(7, 'psa7_pop'), (8, 'psa8_pop'), (9, 'psa9_pop'), (10, 'psa10_pop')]:
                pop = grade_pop(grade)
                if pop is not None:
                    card[key] = pop

            # Add image URL (prefer Supabase, fallback to original data)
            image_url = product.get('image') or image_lookup.get(variant_key)
            if image_url:
                card["image"] = image_url

            # Add graded sales history (only when present, keyed by grade number as string)
            product_sales = sales_lookup.get(product_id)
            if product_sales:
                card["grade_sales"] = {str(k): v for k, v in product_sales.items()}

            cards.append(card)

        # Add to output
        output_data.append({
            "name": group['name'],
            "cards": cards
        })

        print(f"   ✅ Exported {len(cards)} cards")

    # Write to file
    print(f"\n💾 Writing to: {output_path}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    # Summary and validation
    total_cards = sum(len(group['cards']) for group in output_data)
    cards_with_images = sum(1 for group in output_data for card in group['cards'] if 'image' in card)
    cards_with_ids = sum(1 for group in output_data for card in group['cards'] if 'supabase_id' in card)

    print("\n" + "=" * 60)
    print("✅ Export Complete!")
    print("=" * 60)
    print(f"Game: {game}")
    print(f"Groups exported: {len(output_data)}")
    print(f"Total cards: {total_cards}")
    print(f"Cards with Supabase IDs: {cards_with_ids} ({cards_with_ids/total_cards*100:.1f}%)")
    print(f"Cards with images: {cards_with_images} ({cards_with_images/total_cards*100:.1f}%)")
    print(f"Output file: {output_path}")
    print("=" * 60)

    # Validation check
    if cards_with_ids != total_cards:
        print("\n⚠️  WARNING: Not all cards have Supabase IDs!")
        print(f"Missing IDs: {total_cards - cards_with_ids}")
    else:
        print("\n✅ All cards have stable Supabase UUIDs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Supabase card data to BankTCG app format")
    parser.add_argument(
        "--game",
        choices=list(GAME_CONFIGS.keys()),
        default="pokemon",
        help="Which game to export (default: pokemon)",
    )
    args = parser.parse_args()
    export_to_app_format(game=args.game)

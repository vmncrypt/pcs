#!/usr/bin/env python3
"""
Join exported Supabase JSON files into app format.

This script reads the local supabase_*.json files and creates
pokemon-cards-final-data-with-ids.json without needing a database connection.

Usage:
    python join_local_data.py
    python join_local_data.py --output my_output.json
"""

import json
import argparse
from collections import defaultdict


def load_json(filename):
    """Load JSON file."""
    print(f"📂 Loading {filename}...")
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"   Loaded {len(data):,} records")
    return data


def join_data(output_path):
    """Join all tables into app format."""
    print("🔄 Joining Supabase data into app format...")
    print("=" * 60)

    # Load all tables
    groups = load_json("supabase_groups.json")
    products = load_json("supabase_products.json")
    graded_prices = load_json("supabase_graded_prices.json")

    # Build lookup maps
    print("\n🔗 Building lookup maps...")

    # Group ID -> Group Name
    group_map = {g['id']: g['name'] for g in groups}
    print(f"   Groups: {len(group_map)}")

    # Product ID -> {grade: price}
    price_map = defaultdict(dict)
    for p in graded_prices:
        product_id = p['product_id']
        grade = p['grade']
        market_price = p['market_price']
        price_map[product_id][grade] = market_price
    print(f"   Graded prices: {len(price_map)} products with prices")

    # Group products by group_id
    print("\n📦 Grouping products by set...")
    products_by_group = defaultdict(list)
    for p in products:
        group_id = p.get('group_id')
        if group_id:
            products_by_group[group_id].append(p)

    # Build output
    print("\n🏗️  Building output structure...")
    output_data = []

    for group_id, group_name in sorted(group_map.items(), key=lambda x: x[1]):
        group_products = products_by_group.get(group_id, [])

        if not group_products:
            continue

        cards = []
        for product in group_products:
            product_id = product['id']
            name = product.get('name', '')
            number = product.get('number', '')
            market_price = product.get('market_price', 0) or 0
            image = product.get('image')

            # Build card string
            if number:
                card_str = f"{name} #{number}"
            else:
                card_str = name

            # Get graded prices
            prices = price_map.get(product_id, {})

            # Helper to get price for a grade (handles int/string keys)
            def get_grade_price(grade_num):
                price = (
                    prices.get(grade_num) or
                    prices.get(str(grade_num)) or
                    prices.get(f'PSA {grade_num}') or
                    0
                )
                # Convert -1 (no data) to 0 for app
                return 0 if price == -1 else float(price) if price else 0.0

            card = {
                "card": card_str,
                "price": float(market_price),
                "psa7": get_grade_price(7),
                "psa8": get_grade_price(8),
                "grade9": get_grade_price(9),
                "psa10": get_grade_price(10)
            }

            # Add image if available
            if image:
                card["image"] = image

            cards.append(card)

        # Sort cards by price descending
        cards.sort(key=lambda x: x['price'], reverse=True)

        output_data.append({
            "name": group_name,
            "cards": cards
        })

    # Write output
    print(f"\n💾 Writing to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    # Summary
    total_cards = sum(len(g['cards']) for g in output_data)
    cards_with_images = sum(1 for g in output_data for c in g['cards'] if 'image' in c)
    cards_with_psa7 = sum(1 for g in output_data for c in g['cards'] if c['psa7'] > 0)
    cards_with_psa8 = sum(1 for g in output_data for c in g['cards'] if c['psa8'] > 0)
    cards_with_grade9 = sum(1 for g in output_data for c in g['cards'] if c['grade9'] > 0)
    cards_with_psa10 = sum(1 for g in output_data for c in g['cards'] if c['psa10'] > 0)

    print("\n" + "=" * 60)
    print("✅ Join Complete!")
    print("=" * 60)
    print(f"Sets: {len(output_data)}")
    print(f"Total cards: {total_cards:,}")
    print(f"Cards with images: {cards_with_images:,} ({cards_with_images/total_cards*100:.1f}%)")
    print(f"Cards with PSA 7 prices: {cards_with_psa7:,} ({cards_with_psa7/total_cards*100:.1f}%)")
    print(f"Cards with PSA 8 prices: {cards_with_psa8:,} ({cards_with_psa8/total_cards*100:.1f}%)")
    print(f"Cards with PSA 9 prices: {cards_with_grade9:,} ({cards_with_grade9/total_cards*100:.1f}%)")
    print(f"Cards with PSA 10 prices: {cards_with_psa10:,} ({cards_with_psa10/total_cards*100:.1f}%)")
    print(f"Output: {output_path}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Join Supabase exports into app format")
    parser.add_argument("--output", "-o", default="pokemon-cards-joined.json",
                        help="Output file path (default: pokemon-cards-joined.json)")
    args = parser.parse_args()

    join_data(args.output)


if __name__ == "__main__":
    main()

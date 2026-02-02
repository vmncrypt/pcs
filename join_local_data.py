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


def build_sales_history(graded_sales):
    """
    Build sales history lookup: {product_id: {grade: [{date, price}, ...]}}
    Sorted by date ascending for charting.
    """
    sales_map = defaultdict(lambda: defaultdict(list))

    for sale in graded_sales:
        product_id = sale.get('product_id')
        grade = sale.get('grade')
        sale_date = sale.get('sale_date')
        price = sale.get('price')

        if product_id and grade and sale_date and price is not None:
            sales_map[product_id][grade].append({
                "date": sale_date,
                "price": float(price)
            })

    # Sort each grade's sales by date
    for product_id in sales_map:
        for grade in sales_map[product_id]:
            sales_map[product_id][grade].sort(key=lambda x: x['date'])

    return sales_map


def get_latest_sale_price(sales_list):
    """
    Get the latest sale price from sales data.
    Sales are already sorted by date ascending, so last item is most recent.
    Returns 0 if no sales.
    """
    if not sales_list:
        return 0.0
    return sales_list[-1]['price']


def join_data(output_path, include_sales=True):
    """Join all tables into app format."""
    print("🔄 Joining Supabase data into app format...")
    print("=" * 60)

    # Load all tables
    groups = load_json("supabase_groups.json")
    products = load_json("supabase_products.json")
    graded_prices = load_json("supabase_graded_prices.json")

    if include_sales:
        graded_sales = load_json("supabase_graded_sales.json")
    else:
        graded_sales = []

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

    # Product ID -> {grade: [{date, price}, ...]}
    if include_sales:
        sales_map = build_sales_history(graded_sales)
        print(f"   Sales history: {len(sales_map)} products with sales")
    else:
        sales_map = {}

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

            # Get graded prices and sales for this product
            prices = price_map.get(product_id, {})
            product_sales = sales_map.get(product_id, {}) if include_sales else {}

            # Helper to get price for a grade (handles int/string keys)
            # Falls back to latest sale price if no computed price exists
            def get_grade_price(grade_key):
                # Try various key formats
                if isinstance(grade_key, int):
                    price = (
                        prices.get(grade_key) or
                        prices.get(str(grade_key)) or
                        prices.get(f'PSA {grade_key}') or
                        0
                    )
                    sale_keys = [grade_key, str(grade_key)]
                else:
                    # String key like "Ungraded"
                    price = prices.get(grade_key) or 0
                    sale_keys = [grade_key]

                # Convert -1 (no data) to 0
                if price == -1:
                    price = 0

                # If no computed price, use latest sale price
                if not price and include_sales:
                    grade_sales = []
                    for key in sale_keys:
                        grade_sales = product_sales.get(key) or []
                        if grade_sales:
                            break
                    price = get_latest_sale_price(grade_sales)

                return float(price) if price else 0.0

            card = {
                "card": card_str,
                "price": float(market_price),
                "ungraded": get_grade_price("Ungraded"),
                "psa7": get_grade_price(7),
                "psa8": get_grade_price(8),
                "grade9": get_grade_price(9),
                "psa10": get_grade_price(10)
            }

            # Add image if available
            if image:
                card["image"] = image

            # Add sales history for charting (grouped by grade)
            if include_sales and product_id in sales_map:
                product_sales = sales_map[product_id]
                if product_sales:
                    card["sales"] = dict(product_sales)

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
    cards_with_ungraded = sum(1 for g in output_data for c in g['cards'] if c['ungraded'] > 0)
    cards_with_psa7 = sum(1 for g in output_data for c in g['cards'] if c['psa7'] > 0)
    cards_with_psa8 = sum(1 for g in output_data for c in g['cards'] if c['psa8'] > 0)
    cards_with_grade9 = sum(1 for g in output_data for c in g['cards'] if c['grade9'] > 0)
    cards_with_psa10 = sum(1 for g in output_data for c in g['cards'] if c['psa10'] > 0)
    cards_with_sales = sum(1 for g in output_data for c in g['cards'] if 'sales' in c)
    total_sale_records = sum(
        len(sales_list)
        for g in output_data
        for c in g['cards']
        if 'sales' in c
        for sales_list in c['sales'].values()
    )

    print("\n" + "=" * 60)
    print("✅ Join Complete!")
    print("=" * 60)
    print(f"Sets: {len(output_data)}")
    print(f"Total cards: {total_cards:,}")
    print(f"Cards with images: {cards_with_images:,} ({cards_with_images/total_cards*100:.1f}%)")
    print(f"Cards with Ungraded prices: {cards_with_ungraded:,} ({cards_with_ungraded/total_cards*100:.1f}%)")
    print(f"Cards with PSA 7 prices: {cards_with_psa7:,} ({cards_with_psa7/total_cards*100:.1f}%)")
    print(f"Cards with PSA 8 prices: {cards_with_psa8:,} ({cards_with_psa8/total_cards*100:.1f}%)")
    print(f"Cards with PSA 9 prices: {cards_with_grade9:,} ({cards_with_grade9/total_cards*100:.1f}%)")
    print(f"Cards with PSA 10 prices: {cards_with_psa10:,} ({cards_with_psa10/total_cards*100:.1f}%)")
    if include_sales:
        print(f"Cards with sales history: {cards_with_sales:,} ({cards_with_sales/total_cards*100:.1f}%)")
        print(f"Total sale records: {total_sale_records:,}")
    print(f"Output: {output_path}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Join Supabase exports into app format")
    parser.add_argument("--output", "-o", default="pokemon-cards-joined.json",
                        help="Output file path (default: pokemon-cards-joined.json)")
    parser.add_argument("--no-sales", action="store_true",
                        help="Exclude sales history (smaller file size)")
    args = parser.parse_args()

    join_data(args.output, include_sales=not args.no_sales)


if __name__ == "__main__":
    main()

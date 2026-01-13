#!/usr/bin/env python3
"""
Convert PriceCharting HTML table to JSON format for import.

Usage:
    1. Go to PriceCharting series page
    2. Right-click table -> Inspect Element
    3. Right-click <tbody> -> Copy -> Copy outerHTML
    4. Paste into a file (e.g., test.html)
    5. Run: python convert_html_to_json.py test.html "Pokemon Phantasmal Flames"

The script will generate a JSON file you can import with import_pokemon_data.py
"""

import sys
import re
from bs4 import BeautifulSoup
import json


def parse_price(price_text):
    """
    Parse price from various formats:
    - SGD720.08 -> 720.08
    - $45.99 -> 45.99
    - 1,234.56 -> 1234.56
    """
    if not price_text:
        return 0.0

    # Remove currency symbols and commas
    clean = re.sub(r'[SGD$,]', '', price_text.strip())

    try:
        return float(clean)
    except ValueError:
        return 0.0


def convert_html_to_json(html_path, series_name, output_path=None):
    """Convert PriceCharting HTML table to JSON"""

    print(f"📂 Reading HTML from: {html_path}")

    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, 'html.parser')

    # Find all card rows
    rows = soup.find_all('tr', {'data-product': True})

    if not rows:
        print("❌ No card rows found. Make sure you copied the <tbody> element.")
        return

    print(f"✅ Found {len(rows)} cards\n")

    cards = []

    for row in rows:
        try:
            # Get card name (includes number)
            title_cell = row.find('td', class_='title')
            if not title_cell:
                continue

            card_link = title_cell.find('a')
            card_name = card_link.get_text(strip=True) if card_link else ""

            if not card_name:
                continue

            # Get image URL
            image_cell = row.find('td', class_='image')
            image_url = ""
            if image_cell:
                img_tag = image_cell.find('img')
                if img_tag and img_tag.has_attr('src'):
                    image_url = img_tag['src']

            # Get prices (PriceCharting columns)
            # used_price = Ungraded
            # cib_price = PSA 7
            # new_price = PSA 9/10

            used_price_cell = row.find('td', class_='used_price')
            cib_price_cell = row.find('td', class_='cib_price')
            new_price_cell = row.find('td', class_='new_price')

            used_price = 0.0
            if used_price_cell:
                price_span = used_price_cell.find('span', class_='js-price')
                if price_span:
                    used_price = parse_price(price_span.get_text())

            cib_price = 0.0
            if cib_price_cell:
                price_span = cib_price_cell.find('span', class_='js-price')
                if price_span:
                    cib_price = parse_price(price_span.get_text())

            new_price = 0.0
            if new_price_cell:
                price_span = new_price_cell.find('span', class_='js-price')
                if price_span:
                    new_price = parse_price(price_span.get_text())

            # Build card object
            card = {
                "card": card_name,
                "price": used_price,
                "grade9": cib_price if cib_price > 0 else None,
                "psa10": new_price if new_price > 0 else None,
                "image": image_url
            }

            cards.append(card)

            print(f"✓ {card_name}")
            print(f"  Price: ${used_price:.2f}, Grade9: ${cib_price:.2f}, PSA10: ${new_price:.2f}")

        except Exception as e:
            print(f"⚠ Error parsing row: {e}")
            continue

    # Build output JSON
    output_data = [
        {
            "name": series_name,
            "cards": cards
        }
    ]

    # Determine output file name
    if not output_path:
        base_name = html_path.replace('.html', '').replace('.htm', '')
        output_path = f"{base_name}_cards.json"

    # Save to file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Converted {len(cards)} cards")
    print(f"📝 Saved to: {output_path}")
    print(f"\nNext step:")
    print(f"   python import_cards_from_json.py {output_path}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        print("\nExample:")
        print('   python convert_html_to_json.py test.html "Pokemon Phantasmal Flames"')
        sys.exit(1)

    html_path = sys.argv[1]
    series_name = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else None

    convert_html_to_json(html_path, series_name, output_path)


if __name__ == "__main__":
    main()

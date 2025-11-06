import os
import sys
import json
import argparse
from datetime import datetime
from supabase import create_client, Client
from main import scrape_pricecharting, parse_sales_for_grade, parse_pop_report, fetch

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_product_by_variant_key(variant_key):
    """
    Fetch a product from the database by its variant_key.
    Returns product data with group info.
    """
    # Fetch the product
    response = (
        supabase.table("products")
        .select("id, name, number, group_id, pricecharting_url, variant_key")
        .eq("variant_key", variant_key)
        .execute()
    )

    if not response.data or len(response.data) == 0:
        return None

    product = response.data[0]

    # Fetch group name if group_id exists
    if product.get("group_id"):
        group_response = (
            supabase.table("groups")
            .select("name")
            .eq("id", product["group_id"])
            .execute()
        )
        if group_response.data and len(group_response.data) > 0:
            product["group_name"] = group_response.data[0]["name"]
        else:
            product["group_name"] = None
    else:
        product["group_name"] = None

    return product


def save_graded_sales(product_id, scraped_data):
    """
    Save graded sales data to normalized graded_sales table.
    Uses upsert to handle duplicates.
    """
    grades = scraped_data.get("grades", {})
    sales_records = []

    for grade_label, sales_list in grades.items():
        if not isinstance(sales_list, list):
            continue

        # Extract grade number (e.g., "PSA 7" -> 7)
        try:
            grade = int(grade_label.split()[-1])
        except (ValueError, IndexError):
            continue

        for sale in sales_list:
            if not isinstance(sale, dict):
                continue

            date_str = sale.get('date')
            price = sale.get('price')
            url = sale.get('url')
            title = sale.get('title', '')

            if not date_str or price is None or not url:
                print(f"   ⚠️  Skipping incomplete sale record: {sale}")
                continue

            # Parse date
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
            except ValueError:
                try:
                    parsed_date = datetime.strptime(date_str, "%b %d, %Y").date().isoformat()
                except ValueError:
                    print(f"   ⚠️  Could not parse date: {date_str}")
                    continue

            sales_records.append({
                'product_id': product_id,
                'grade': grade,
                'sale_date': parsed_date,
                'price': float(price),
                'ebay_url': url,
                'title': title
            })

    if not sales_records:
        print("   ℹ️  No sales records to save")
        return True

    try:
        # Upsert sales records
        supabase.table('graded_sales').upsert(
            sales_records,
            on_conflict='product_id,sale_date,price,ebay_url'
        ).execute()
        print(f"   ✅ Saved {len(sales_records)} sales records")
        return True
    except Exception as e:
        print(f"   ❌ Error saving graded sales: {e}")
        return False


def update_product_data(product_id, pop_count, pricecharting_url):
    """
    Update the products table with pop_count and pricecharting_url.
    """
    try:
        supabase.table("products").update({
            "pop_count": pop_count,
            "pricecharting_url": pricecharting_url
        }).eq("id", product_id).execute()
        print(f"   ✅ Updated product pop_count and URL")
        return True
    except Exception as e:
        print(f"   ❌ Error updating product: {e}")
        return False


def parse_card_name(name):
    """Extract clean card name by removing everything after ' -' or ' ('."""
    if not name:
        return ""
    import re
    clean = re.split(r'\s+-|\s+\(', name)[0].strip()
    return clean


def parse_card_number(number):
    """Extract card number before '/' and remove leading zeros."""
    if not number:
        return ""
    clean = number.split('/')[0].strip()
    clean = clean.lstrip('0') or '0'
    return clean


def scrape_product(product_data, verbose=True):
    """
    Scrape a single product and save to database.
    Returns True if successful, False otherwise.
    """
    product_id = product_data.get("id")
    variant_key = product_data.get("variant_key")
    raw_name = product_data.get("name")
    raw_number = product_data.get("number")
    group_name = product_data.get("group_name")
    pricecharting_url = product_data.get("pricecharting_url")

    if verbose:
        number_display = f"#{raw_number}" if raw_number else "(no number)"
        print(f"\n📦 Product: {raw_name} {number_display}")
        print(f"   Variant Key: {variant_key}")

    try:
        # If we already have a pricecharting_url, use it directly
        if pricecharting_url:
            if verbose:
                print(f"   Using existing URL: {pricecharting_url}")

            # Fetch once and reuse
            soup = fetch(pricecharting_url)

            result = {
                "product_url": pricecharting_url,
                "grades": {},
                "pop_report": {}
            }

            # Scrape grade data
            grade_tabs = {
                "completed-auctions-cib": "PSA 7",
                "completed-auctions-new": "PSA 8",
                "completed-auctions-graded": "PSA 9",
                "completed-auctions-manual-only": "PSA 10"
            }

            for css_class, grade in grade_tabs.items():
                sales = parse_sales_for_grade(pricecharting_url, css_class, soup=soup)
                result["grades"][grade] = sales

            # Scrape POP report
            result["pop_report"] = parse_pop_report(pricecharting_url, soup=soup)

        else:
            # Need to search for the product first
            clean_name = parse_card_name(raw_name)
            clean_number = parse_card_number(raw_number) if raw_number else ""

            # Build search query
            if clean_number:
                search_query = f"{clean_name} {clean_number}".strip()
            else:
                search_query = clean_name.strip()

            if verbose:
                print(f"   Search: {search_query} | Set: {group_name or 'N/A'}")

            result = scrape_pricecharting(search_query, test_mode=False, set_name=group_name, verbose=False)

        # Count sales
        total_sales = sum(len(sales) for sales in result.get("grades", {}).values())
        pop_count = len(result.get('pop_report', {}))

        if verbose:
            grades_summary = []
            for grade_label, sales in result.get("grades", {}).items():
                grade_num = grade_label.split()[-1]
                grades_summary.append(f"PSA {grade_num}: {len(sales)}")

            print(f"   📊 Scraped: {total_sales} total sales [{', '.join(grades_summary)}], POP: {pop_count} grades")

        # Save to database
        if verbose:
            print(f"\n💾 Saving to database...")

        # Save sales
        save_graded_sales(product_id, result)

        # Update product
        update_product_data(product_id, result.get("pop_report", {}), result.get("product_url"))

        if verbose:
            print(f"\n✅ Successfully scraped and saved product!")

        return True

    except Exception as e:
        print(f"\n❌ Error scraping product: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """
    Main function to scrape a single product by variant_key.
    Can be called from command line or imported and used programmatically.
    """
    parser = argparse.ArgumentParser(description="Scrape a single product by variant_key")
    parser.add_argument("variant_key", type=str, help="The variant_key of the product to scrape")
    parser.add_argument("--json", action="store_true", help="Output result as JSON (for programmatic use)")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    args = parser.parse_args()

    verbose = not args.quiet

    if verbose:
        print("🚀 PriceCharting Single Product Scraper")
        print("=" * 60)

    # Fetch product from database
    if verbose:
        print(f"\n🔍 Fetching product with variant_key: {args.variant_key}")

    product = fetch_product_by_variant_key(args.variant_key)

    if not product:
        result = {"success": False, "error": f"Product not found with variant_key: {args.variant_key}"}
        if args.json:
            print(json.dumps(result))
        else:
            print(f"\n❌ {result['error']}")
        sys.exit(1)

    if verbose:
        print(f"   ✅ Found product: {product['name']}")

    # Scrape the product
    success = scrape_product(product, verbose=verbose)

    # Output result
    result = {
        "success": success,
        "variant_key": args.variant_key,
        "product_id": product["id"],
        "product_name": product["name"]
    }

    if args.json:
        print(json.dumps(result))
    elif verbose:
        print("\n" + "=" * 60)
        if success:
            print("✨ SCRAPE COMPLETE")
        else:
            print("❌ SCRAPE FAILED")
        print("=" * 60)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

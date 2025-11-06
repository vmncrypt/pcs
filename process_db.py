import os
import re
from supabase import create_client, Client
from main import scrape_pricecharting

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def parse_card_name(name):
    """
    Extract the clean card name by removing everything after ' -' or ' ('.
    Example: "Pikachu - Holo" -> "Pikachu"
    Example: "Charizard (Shiny)" -> "Charizard"
    """
    if not name:
        return ""

    # Split by ' -' or ' (' and take the first part
    clean = re.split(r'\s+-|\s+\(', name)[0].strip()
    return clean


def parse_card_number(number):
    """
    Extract the card number before the '/' character and remove leading zeros.
    Example: "25/102" -> "25"
    Example: "001/102" -> "1"
    Example: "SV01" -> "SV01"
    """
    if not number:
        return ""

    # Split by '/' and take the first part
    clean = number.split('/')[0].strip()

    # Remove leading zeros (but keep at least one digit)
    clean = clean.lstrip('0') or '0'

    return clean


def fetch_incomplete_products(limit=1000, offset=0):
    """
    Fetch products that need grade data processing (completed=false).
    Manually joins product_grade_progress with products table and groups.
    Uses pagination with offset for batching through large datasets.
    """
    # First, get incomplete product IDs with pagination
    progress_response = (
        supabase.table("product_grade_progress")
        .select("product_id")
        .eq("completed", False)
        .range(offset, offset + limit - 1)
        .execute()
    )

    if not progress_response.data:
        return []

    # Get the product IDs
    product_ids = [item["product_id"] for item in progress_response.data]

    # Fetch the actual product details with group info and pricecharting_url
    products_response = (
        supabase.table("products")
        .select("id, name, number, group_id, pricecharting_url")
        .in_("id", product_ids)
        .execute()
    )

    if not products_response.data:
        return []

    # Get all unique group IDs
    group_ids = [p.get("group_id") for p in products_response.data if p.get("group_id")]

    # Fetch all groups at once if any exist
    group_map = {}
    if group_ids:
        groups_response = (
            supabase.table("groups")
            .select("id, name")
            .in_("id", group_ids)
            .execute()
        )
        group_map = {g["id"]: g["name"] for g in groups_response.data}

    # Enrich products with group names
    enriched_products = []
    for product in products_response.data:
        group_id = product.get("group_id")
        product["group_name"] = group_map.get(group_id) if group_id else None
        enriched_products.append(product)

    return enriched_products


def save_graded_sales(product_id, scraped_data):
    """
    Save graded sales data to normalized graded_sales table.
    scraped_data format: {"grades": {"PSA 7": [...], "PSA 8": [...]}, "pop_report": {...}}
    Uses upsert to handle duplicates - only new sales will be inserted.
    """
    from datetime import datetime

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

            # Extract fields
            date_str = sale.get('date')
            price = sale.get('price')
            url = sale.get('url')
            title = sale.get('title', '')

            if not date_str or price is None or not url:
                print(f"   ⚠️  Skipping incomplete sale record: {sale}")
                continue

            # Parse date: handle multiple formats
            try:
                # Try ISO format first (YYYY-MM-DD)
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
            except ValueError:
                try:
                    # Try text format (Nov 3, 2024)
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
        return True  # No sales to save, but not an error

    try:
        # Upsert sales records (unique constraint prevents duplicates)
        supabase.table('graded_sales').upsert(
            sales_records,
            on_conflict='product_id,sale_date,price,ebay_url'
        ).execute()
        return True
    except Exception as e:
        print(f"   ❌ Error saving graded sales: {e}")
        return False


def update_product_data(product_id, pop_count):
    """
    Update the products table with pop_count only.
    Sales data is now stored in graded_sales table.
    """
    try:
        supabase.table("products").update({
            "pop_count": pop_count
        }).eq("id", product_id).execute()
        return True
    except Exception as e:
        print(f"   ❌ Error updating product pop_count: {e}")
        return False


def mark_product_completed(product_id):
    """
    Mark the product as completed in product_grade_progress table.
    """
    try:
        supabase.table("product_grade_progress").update({
            "completed": True,
            "updated_at": "now()"
        }).eq("product_id", product_id).execute()
        return True
    except Exception as e:
        print(f"   ❌ Error marking product completed: {e}")
        return False


def process_product(product_data, verbose=True):
    """
    Process a single product: scrape PriceCharting data.
    Returns scraped data dict or None if error.
    Does NOT write to database - that's done in batch by process_batch().
    """
    product_id = product_data.get("id")
    raw_name = product_data.get("name")
    raw_number = product_data.get("number")
    group_name = product_data.get("group_name")
    pricecharting_url = product_data.get("pricecharting_url")

    if verbose:
        # Handle null number display
        number_display = f"#{raw_number}" if raw_number else "(no number)"
        print(f"📦 Processing: {raw_name} {number_display}")

    try:
        # If we already have a pricecharting_url, use it directly
        if pricecharting_url:
            if verbose:
                print(f"   Using existing URL: {pricecharting_url}")

            # Import scraping functions directly from main
            from main import parse_sales_for_grade, parse_pop_report, fetch

            # Fetch once and reuse for all parsing (saves 4 HTTP requests per product)
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

            # Build search query (only include number if it exists)
            if clean_number:
                search_query = f"{clean_name} {clean_number}".strip()
            else:
                search_query = clean_name.strip()

            if verbose:
                print(f"   Search: {search_query} | Set: {group_name or 'N/A'}")

            result = scrape_pricecharting(search_query, test_mode=False, set_name=group_name, verbose=False)

        if verbose:
            # Count sales for each grade
            grades_summary = []
            for grade_label, sales in result.get("grades", {}).items():
                grade_num = grade_label.split()[-1]  # Extract "7" from "PSA 7"
                grades_summary.append(f"PSA {grade_num}: {len(sales)}")

            total_sales = sum(len(sales) for sales in result.get("grades", {}).values())
            print(f"   ✅ Scraped: {total_sales} total sales [{', '.join(grades_summary)}], POP: {len(result.get('pop_report', {}))} grades")

        return {
            "product_id": product_id,
            "result": result
        }

    except Exception as e:
        print(f"   ❌ Error scraping: {e}")
        return None


def process_batch(batch_data, verbose=True):
    """
    Process a batch of products: scrape all, then write all to database at once.
    batch_data: list of dicts with "product_id" and "result" keys
    Returns (success_count, failed_count)
    """
    if not batch_data:
        return 0, 0

    from datetime import datetime

    # Prepare all database writes
    all_sales_records = []
    product_updates = []
    progress_updates = []

    for item in batch_data:
        if item is None:
            continue

        product_id = item["product_id"]
        result = item["result"]

        # Collect sales records
        grades = result.get("grades", {})
        for grade_label, sales_list in grades.items():
            if not isinstance(sales_list, list):
                continue

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
                    continue

                # Parse date
                try:
                    parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
                except ValueError:
                    try:
                        parsed_date = datetime.strptime(date_str, "%b %d, %Y").date().isoformat()
                    except ValueError:
                        continue

                all_sales_records.append({
                    'product_id': product_id,
                    'grade': grade,
                    'sale_date': parsed_date,
                    'price': float(price),
                    'ebay_url': url,
                    'title': title
                })

        # Collect product updates (pop_count and pricecharting_url)
        pop_count = result.get("pop_report", {})
        product_url = result.get("product_url")

        product_updates.append({
            "id": product_id,
            "pop_count": pop_count,
            "pricecharting_url": product_url
        })

        # Collect progress updates
        progress_updates.append(product_id)

    # Now write everything in batches
    success_count = 0
    failed_count = 0

    # 1. Batch upsert all sales records
    if all_sales_records:
        try:
            if verbose:
                print(f"\n💾 Writing {len(all_sales_records)} sales records to database...")
            supabase.table('graded_sales').upsert(
                all_sales_records,
                on_conflict='product_id,sale_date,price,ebay_url'
            ).execute()
        except Exception as e:
            print(f"   ❌ Error batch saving sales: {e}")
            failed_count = len(batch_data)
            return 0, failed_count

    # 2. Batch update products (pop_count and pricecharting_url)
    if product_updates:
        try:
            if verbose:
                print(f"💾 Updating {len(product_updates)} product records...")
            for update in product_updates:
                supabase.table("products").update({
                    "pop_count": update["pop_count"],
                    "pricecharting_url": update["pricecharting_url"]
                }).eq("id", update["id"]).execute()
        except Exception as e:
            print(f"   ❌ Error batch updating products: {e}")

    # 3. Batch mark as completed
    if progress_updates:
        try:
            if verbose:
                print(f"💾 Marking {len(progress_updates)} products as completed...")
            for product_id in progress_updates:
                supabase.table("product_grade_progress").update({
                    "completed": True,
                    "updated_at": "now()"
                }).eq("product_id", product_id).execute()
            success_count = len(progress_updates)
        except Exception as e:
            print(f"   ❌ Error batch updating progress: {e}")
            failed_count = len(batch_data)
            return 0, failed_count

    if verbose:
        print(f"✅ Batch write complete: {success_count} products saved\n")

    return success_count, failed_count


def main():
    """
    Main function to process all incomplete products in batches.
    """
    import time
    import argparse

    parser = argparse.ArgumentParser(description="Process PriceCharting grade data for products")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of products to fetch/write per batch")
    parser.add_argument("--max-products", type=int, default=None, help="Maximum number of products to process (for testing)")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay in seconds between scrape requests")
    args = parser.parse_args()

    print("🚀 Starting PriceCharting Grade Data Processor")
    print(f"   Batch size: {args.batch_size} (scrape {args.batch_size}, then write all at once)")
    print(f"   Delay between requests: {args.delay}s")
    if args.max_products:
        print(f"   Max products to process: {args.max_products}")
    print()

    total_processed = 0
    total_success = 0
    total_failed = 0
    offset = 0

    while True:
        # Check if we've hit the max limit
        if args.max_products and total_processed >= args.max_products:
            print(f"\n✅ Reached max products limit ({args.max_products})")
            break

        # Fetch next batch
        print(f"📥 Fetching batch (offset: {offset})...")
        products = fetch_incomplete_products(limit=args.batch_size, offset=offset)

        if not products:
            print("✅ No more incomplete products found!")
            break

        print(f"📊 Scraping {len(products)} products in this batch\n")

        # Scrape all products in batch (collect data, don't write yet)
        batch_results = []
        for i, product_data in enumerate(products, 1):
            # Check max limit
            if args.max_products and total_processed >= args.max_products:
                break

            print(f"[{total_processed + 1}] ", end="")

            scraped_data = process_product(product_data, verbose=True)
            batch_results.append(scraped_data)

            total_processed += 1

            # Add delay between scrape requests to be respectful
            if i < len(products) and (not args.max_products or total_processed < args.max_products):
                time.sleep(args.delay)

            print()

        # Write all scraped data to database at once
        success, failed = process_batch(batch_results, verbose=True)
        total_success += success
        total_failed += failed

        # Move to next batch (offset stays 0 because completed items are filtered out)
        if args.max_products and total_processed >= args.max_products:
            break

    # Final summary
    print("\n" + "="*60)
    print("📊 PROCESSING COMPLETE")
    print("="*60)
    print(f"   Total processed: {total_processed}")
    print(f"   ✅ Successful: {total_success}")
    print(f"   ❌ Failed: {total_failed}")
    print(f"   Success rate: {(total_success/total_processed*100) if total_processed > 0 else 0:.1f}%")
    print("="*60)


if __name__ == "__main__":
    main()

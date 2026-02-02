import os
from collections import defaultdict
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables from .env file
load_dotenv()

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Searchable log prefixes for easy filtering
LOG_PREFIX_COLLISION = "[URL_COLLISION]"
LOG_PREFIX_EXCLUDED = "[EXCLUDED]"


def fetch_all_eligible_products():
    """
    Fetch ALL products that have market_price >= 15.
    Uses cursor-based pagination with id > last_id to ensure all rows are fetched.
    
    Returns list of product dicts with id, name, and pricecharting_url.
    """
    eligible_products = []
    limit = 1000
    last_id = ""  # Empty string sorts before all UUIDs

    print("🔍 Fetching all eligible products from database...")
    print("   Using SQL filter: market_price >= 15")
    print("   Using cursor-based pagination (id > last_id)")

    while True:
        query = (
            supabase.table("products")
            .select("id, name, pricecharting_url, variant_key, market_price, rarity, number")
            .gte("market_price", 15)
            .order("id", desc=False)
            .limit(limit)
        )
        
        # Add cursor filter if we have a last_id
        if last_id:
            query = query.gt("id", last_id)
        
        response = query.execute()

        if not response.data:
            break

        eligible_products.extend(response.data)
        
        # Update cursor to last ID in this batch
        last_id = response.data[-1]["id"]

        print(f"      Fetched {len(eligible_products):,} products so far (cursor: {last_id[:8]}...)...")

        if len(response.data) < limit:
            break

    print(f"\n✅ Found {len(eligible_products):,} eligible products total")
    return eligible_products


def detect_url_collisions(products):
    """
    Detect products that share the same pricecharting_url.
    
    Returns:
        - clean_products: list of products without URL collisions
        - collisions: dict mapping pricecharting_url -> list of product dicts
    """
    print("\n🔍 Detecting pricecharting_url collisions...")
    
    # Group products by pricecharting_url
    url_to_products = defaultdict(list)
    products_without_url = []
    
    for product in products:
        url = product.get("pricecharting_url")
        if url:
            # Strip query parameters (? and everything after) for comparison
            clean_url = url.split("?")[0] if "?" in url else url
            product["_clean_url"] = clean_url  # Store cleaned URL for grouping
            url_to_products[clean_url].append(product)
        else:
            # Products without a URL are fine to process
            products_without_url.append(product)
    
    # Separate clean (unique URL) from collisions (duplicate URLs)
    clean_products = list(products_without_url)  # Products without URLs are clean
    collisions = {}
    
    for url, prods in url_to_products.items():
        if len(prods) == 1:
            # Unique URL - clean
            clean_products.append(prods[0])
        else:
            # Multiple products with same URL - collision!
            collisions[url] = prods
    
    # Log collisions with searchable prefix
    if collisions:
        print(f"\n{'='*60}")
        print(f"{LOG_PREFIX_COLLISION} Found {len(collisions)} URLs with multiple products!")
        print(f"{'='*60}")
        
        total_excluded = 0
        for url, prods in collisions.items():
            total_excluded += len(prods)
            print(f"\n{LOG_PREFIX_COLLISION} URL: {url}")
            print(f"{LOG_PREFIX_COLLISION} Products sharing this URL ({len(prods)}):")
            for p in prods:
                variant = p.get('variant_key', 'N/A')
                print(f"{LOG_PREFIX_EXCLUDED}   - {p['name']} | variant_key: {variant} | id: {p['id']}")
        
        print(f"\n{LOG_PREFIX_COLLISION} Summary: {total_excluded} products excluded due to URL collisions")
        print(f"{'='*60}\n")
    else:
        print("   ✅ No URL collisions found!")
    
    print(f"\n📊 Collision Analysis:")
    print(f"   Total eligible products: {len(products):,}")
    print(f"   Products with unique/no URL (clean): {len(clean_products):,}")
    print(f"   Products excluded (URL collisions): {len(products) - len(clean_products):,}")
    print(f"   Collision groups: {len(collisions)}")
    
    return clean_products, collisions


def sync_progress_table(clean_products):
    """
    Sync the product_grade_progress table with clean products only.
    
    Approach: Wipe all existing rows and insert fresh ones.
    This ensures a clean slate on each sync run.
    """
    print(f"\n📝 Syncing product_grade_progress table...")
    
    clean_ids = [p["id"] for p in clean_products]

    # Step 1: Delete ALL existing rows
    print("   🗑️  Wiping all existing progress records...")
    try:
        # Count how many exist
        count_response = supabase.table("product_grade_progress").select("product_id", count="exact").execute()
        existing_count = count_response.count if count_response.count else 0
        
        if existing_count > 0:
            print(f"      Found {existing_count:,} existing records to delete...")
            # Delete in smaller batches (100 at a time to avoid issues)
            deleted = 0
            while True:
                # Fetch a small batch of IDs
                batch_response = (
                    supabase.table("product_grade_progress")
                    .select("product_id")
                    .limit(100)
                    .execute()
                )
                
                if not batch_response.data:
                    break
                
                batch_ids = [r["product_id"] for r in batch_response.data]
                
                # Delete one at a time if batch delete fails
                try:
                    supabase.table("product_grade_progress").delete().in_("product_id", batch_ids).execute()
                    deleted += len(batch_ids)
                except Exception:
                    # Fallback: delete one by one
                    for pid in batch_ids:
                        try:
                            supabase.table("product_grade_progress").delete().eq("product_id", pid).execute()
                            deleted += 1
                        except Exception:
                            pass
                
                if deleted % 500 == 0 or deleted == existing_count:
                    print(f"      Deleted {deleted:,}/{existing_count:,} records...")
            
            print(f"   ✅ Deleted {deleted:,} existing records")
        else:
            print("      No existing records to delete")
    except Exception as e:
        print(f"   ⚠️  Error during delete: {e}")
        print("      Will use upsert to handle existing records...")

    # Step 2: Upsert all clean products with completed=false (upsert handles duplicates gracefully)
    print(f"\n   ➕ Adding {len(clean_ids):,} products (completed=false)...")
    
    # Batch upsert in groups of 100 (smaller batches for reliability)
    success_count = 0
    for i in range(0, len(clean_ids), 100):
        batch = clean_ids[i:i + 100]
        rows = [{"product_id": pid, "completed": False} for pid in batch]
        try:
            supabase.table("product_grade_progress").upsert(rows, on_conflict="product_id").execute()
            success_count += len(batch)
            if (i + 100) % 500 == 0 or i + 100 >= len(clean_ids):
                print(f"      Synced {min(i + 100, len(clean_ids)):,}/{len(clean_ids):,} products...")
        except Exception as e:
            print(f"      ⚠️  Error upserting batch {i}-{i+100}: {e}")

    print(f"\n✅ Sync complete! Products ready for scraping: {success_count:,}")


def write_collisions_to_file(collisions, filename="url_collisions.txt"):
    """
    Write collision information to a text file for local review.
    """
    with open(filename, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("URL COLLISION REPORT\n")
        f.write(f"Generated at: {__import__('datetime').datetime.now().isoformat()}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Total collision groups: {len(collisions)}\n")
        total_products = sum(len(prods) for prods in collisions.values())
        f.write(f"Total products affected: {total_products}\n\n")
        
        f.write("-" * 80 + "\n\n")
        
        for url, prods in collisions.items():
            f.write(f"URL: {url}\n")
            f.write(f"Products sharing this URL ({len(prods)}):\n")
            for p in prods:
                variant = p.get('variant_key', 'N/A')
                f.write(f"  - {p['name']}\n")
                f.write(f"    ID: {p['id']}\n")
                f.write(f"    variant_key: {variant}\n")
            f.write("\n")
    
    print(f"\n📄 Collision report written to: {filename}")


def main():
    """
    Main function to sync eligible products to progress table.
    Run this before starting the scraper to ensure we're scraping the right products.
    
    Key features:
    1. Cursor-based pagination to fetch ALL eligible products
    2. URL collision detection - products sharing same pricecharting_url are excluded
    3. Only clean products are synced to product_grade_progress with completed=false
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Sync eligible products to product_grade_progress table")
    parser.add_argument("--local", action="store_true", help="Local development mode - writes collisions to url_collisions.txt")
    args = parser.parse_args()
    
    print("🚀 PriceCharting - Sync Eligible Products")
    print("=" * 60)
    if args.local:
        print("   Mode: LOCAL DEVELOPMENT (collisions will be saved to file)")
    print("\nCriteria:")
    print("  • market_price >= 15")
    print("  • No pricecharting_url collision with other products")
    print()

    # Fetch all eligible products with cursor-based pagination
    eligible_products = fetch_all_eligible_products()

    if not eligible_products:
        print("\n⚠️  No eligible products found!")
        return

    # Detect URL collisions and get clean products
    clean_products, collisions = detect_url_collisions(eligible_products)
    
    # In local mode, write collisions to file
    if args.local and collisions:
        write_collisions_to_file(collisions)

    if not clean_products:
        print("\n⚠️  No clean products after collision filtering!")
        return

    # Sync only clean products to progress table
    sync_progress_table(clean_products)

    print("\n" + "=" * 60)
    print("✨ Ready to run: python process_db.py")
    print("=" * 60)
    
    if collisions:
        print(f"\n⚠️  Note: {len(collisions)} URL collision groups were excluded.")
        print(f"   Search logs for '{LOG_PREFIX_COLLISION}' to review them.")
        if args.local:
            print(f"   📄 Full report saved to: url_collisions.txt")


if __name__ == "__main__":
    main()
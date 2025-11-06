import os
from supabase import create_client

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_all_eligible_products():
    """
    Fetch ALL products that have is_eligible = true.

    Returns list of product IDs.
    """
    eligible_ids = []
    limit = 1000
    offset = 0

    print("🔍 Fetching all eligible products from database...")
    print("   Using SQL filter: is_eligible = true")

    while True:
        response = (
            supabase.table("products")
            .select("id")
            .eq("is_eligible", True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        if not response.data:
            break

        for product in response.data:
            eligible_ids.append(product["id"])

        print(f"      Fetched {len(eligible_ids)} products so far...")

        if len(response.data) < limit:
            break

        offset += limit

    print(f"\n✅ Found {len(eligible_ids):,} eligible products total")
    return eligible_ids


def sync_progress_table(eligible_product_ids):
    """
    Sync the product_grade_progress table:
    1. Mark all existing rows as completed=false (for re-scraping)
    2. Add new rows for products not in the table
    """
    print(f"\n📝 Syncing product_grade_progress table...")

    # Get all existing product IDs in progress table
    existing_response = (
        supabase.table("product_grade_progress")
        .select("product_id")
        .execute()
    )

    existing_ids = set(item["product_id"] for item in existing_response.data)
    eligible_ids_set = set(eligible_product_ids)

    # Products to add (new eligible products)
    to_add = eligible_ids_set - existing_ids

    # Products to mark as incomplete (existing eligible products)
    to_update = eligible_ids_set & existing_ids

    # Products to potentially remove (in progress but no longer eligible)
    to_remove = existing_ids - eligible_ids_set

    print(f"\n   📊 Analysis:")
    print(f"      Total eligible products: {len(eligible_product_ids):,}")
    print(f"      Already in progress table: {len(existing_ids):,}")
    print(f"      New products to add: {len(to_add):,}")
    print(f"      Existing to mark incomplete: {len(to_update):,}")
    print(f"      No longer eligible (ignored): {len(to_remove):,}")

    # Mark all existing eligible products as incomplete
    if to_update:
        print(f"\n   🔄 Marking {len(to_update):,} products as incomplete...")

        # Batch update in groups of 500 (smaller to avoid query size limits)
        update_list = list(to_update)
        for i in range(0, len(update_list), 500):
            batch = update_list[i:i + 500]
            try:
                supabase.table("product_grade_progress").update({
                    "completed": False,
                    "updated_at": "now()"
                }).in_("product_id", batch).execute()

                print(f"      Updated {min(i + 500, len(update_list))}/{len(update_list)} products...")
            except Exception as e:
                print(f"      ⚠️  Error updating batch {i}-{i+500}: {e}")

    # Add new products (use upsert to handle any duplicates gracefully)
    if to_add:
        print(f"\n   ➕ Adding {len(to_add):,} new products...")

        # Batch upsert in groups of 500
        add_list = list(to_add)
        for i in range(0, len(add_list), 500):
            batch = add_list[i:i + 500]
            rows = [{"product_id": pid, "completed": False} for pid in batch]
            try:
                supabase.table("product_grade_progress").upsert(rows, on_conflict="product_id").execute()
                print(f"      Added {min(i + 500, len(add_list))}/{len(add_list)} products...")
            except Exception as e:
                print(f"      ⚠️  Error adding batch {i}-{i+500}: {e}")

    print(f"\n✅ Sync complete! Total products ready for scraping: {len(eligible_product_ids):,}")


def main():
    """
    Main function to sync eligible products to progress table.
    Run this before starting the scraper to ensure we're scraping the right products.
    """
    print("🚀 PriceCharting - Sync Eligible Products")
    print("=" * 60)
    print("\nCriteria:")
    print("  • is_eligible = true")
    print()

    # Fetch all eligible products
    eligible_ids = fetch_all_eligible_products()

    if not eligible_ids:
        print("\n⚠️  No eligible products found!")
        return

    # Sync progress table
    sync_progress_table(eligible_ids)

    print("\n" + "=" * 60)
    print("✨ Ready to run: python process_db.py")
    print("=" * 60)


if __name__ == "__main__":
    main()

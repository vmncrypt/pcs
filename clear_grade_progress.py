import os
from supabase import create_client, Client

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_total_count():
    """
    Get total count of rows in product_grade_progress table.
    """
    response = supabase.table("product_grade_progress").select("product_id", count="exact").execute()
    return response.count if response.count else 0


def delete_all_rows_in_batches(fetch_size=1000, delete_chunk_size=100):
    """
    Delete all rows from product_grade_progress table in batches.
    Fetches in larger batches but deletes in smaller chunks to avoid query limits.
    """
    total_deleted = 0
    batch_number = 1

    while True:
        # Fetch a batch of product_ids
        response = supabase.table("product_grade_progress").select("product_id").limit(fetch_size).execute()

        if not response.data or len(response.data) == 0:
            print("   No more rows to delete")
            break

        product_ids = [row["product_id"] for row in response.data]

        print(f"   Batch {batch_number}: Deleting {len(product_ids)} rows (in chunks of {delete_chunk_size})...")

        # Delete in smaller chunks to avoid "Bad Request" errors
        for i in range(0, len(product_ids), delete_chunk_size):
            chunk = product_ids[i:i + delete_chunk_size]
            supabase.table("product_grade_progress").delete().in_("product_id", chunk).execute()

        total_deleted += len(product_ids)
        print(f"   ✅ Deleted {len(product_ids)} rows (total: {total_deleted})")

        batch_number += 1

    return total_deleted


def main():
    """
    Main function to clear all rows from product_grade_progress table.
    """
    print("🚀 Clear Product Grade Progress Table")
    print("=" * 60)
    print("\n⚠️  WARNING: This will delete ALL rows from product_grade_progress!")
    print()

    try:
        # Get total count
        print("📊 Counting total rows...")
        total_count = get_total_count()

        if total_count == 0:
            print("✅ Table is already empty!")
            return

        print(f"📝 Found {total_count:,} rows to delete\n")

        # Ask for confirmation
        confirmation = input(f"Are you sure you want to delete all {total_count:,} rows? (yes/no): ")

        if confirmation.lower() != "yes":
            print("\n❌ Operation cancelled")
            return

        print("\n🗑️  Deleting all rows...\n")

        # Delete all rows in batches (fetch 1000, delete in chunks of 100)
        total_deleted = delete_all_rows_in_batches(fetch_size=1000, delete_chunk_size=100)

        # Final summary
        print("\n" + "=" * 60)
        print("✨ DELETE COMPLETE")
        print("=" * 60)
        print(f"   Total rows deleted: {total_deleted:,}")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()

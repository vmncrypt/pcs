#!/usr/bin/env python3
"""
Export all Supabase tables to JSON files in current directory.
"""

import os
import json
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TABLES = ['groups', 'products', 'product_grade_progress', 'graded_sales', 'graded_prices']


def export_table(table_name):
    """Export a single table to JSON."""
    print(f"📥 Downloading {table_name}...")
    all_data = []
    offset = 0
    limit = 1000

    while True:
        try:
            response = supabase.table(table_name).select('*').range(offset, offset + limit - 1).execute()
            if not response.data:
                break
            all_data.extend(response.data)
            print(f"   Fetched {len(all_data)} rows...")
            if len(response.data) < limit:
                break
            offset += limit
        except Exception as e:
            print(f"   Error: {e}")
            break

    filename = f"supabase_{table_name}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False, default=str)

    print(f"✅ Saved {len(all_data)} rows to {filename}\n")
    return len(all_data)


def main():
    print("🚀 Exporting Supabase database...")
    print("=" * 50)

    total_rows = 0
    for table in TABLES:
        total_rows += export_table(table)

    print("=" * 50)
    print(f"🎉 Done! Exported {total_rows} total rows across {len(TABLES)} tables.")


if __name__ == "__main__":
    main()

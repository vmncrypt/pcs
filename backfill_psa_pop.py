#!/usr/bin/env python3
"""
Backfill PSA population counts for all products that already have a pricecharting_url.
Fetches pop data from PriceCharting and writes it directly to graded_prices.psa_pop.
"""

import os
import time
import argparse
from supabase import create_client, Client
from dotenv import load_dotenv
from main import parse_pop_report_table

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_products_with_urls(limit=1000, offset=0):
    resp = supabase.table("products") \
        .select("id, name, number, pricecharting_url") \
        .not_.is_("pricecharting_url", "null") \
        .range(offset, offset + limit - 1) \
        .execute()
    return resp.data or []


def fetch_already_done_ids():
    """Return set of product_ids that already have psa_pop populated."""
    done = set()
    page_size = 1000
    offset = 0
    while True:
        resp = supabase.table("graded_prices") \
            .select("product_id") \
            .not_.is_("psa_pop", "null") \
            .range(offset, offset + page_size - 1) \
            .execute()
        if not resp.data:
            break
        for r in resp.data:
            done.add(r["product_id"])
        if len(resp.data) < page_size:
            break
        offset += page_size
    return done


def upsert_pop_for_product(product_id, pop_report):
    """Update psa_pop on existing graded_prices rows only (don't insert new rows)."""
    if not pop_report:
        return 0

    count = 0
    for grade, psa_pop in pop_report.items():
        if grade not in (7, 8, 9, 10):
            continue
        supabase.table("graded_prices") \
            .update({"psa_pop": psa_pop}) \
            .eq("product_id", product_id) \
            .eq("grade", grade) \
            .execute()
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser(description="Backfill PSA pop counts from PriceCharting")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
    parser.add_argument("--max", type=int, default=None, help="Max products to process (for testing)")
    args = parser.parse_args()

    print("🚀 PSA Pop Backfill")
    print(f"   Delay: {args.delay}s | Max: {args.max or 'unlimited'}")
    print("   Fetching already-completed products...")
    already_done = fetch_already_done_ids()
    print(f"   Skipping {len(already_done)} products already processed\n")

    total = 0
    updated = 0
    skipped = 0
    offset = 0
    batch_size = 200

    while True:
        if args.max and total >= args.max:
            break

        products = fetch_products_with_urls(limit=batch_size, offset=offset)
        if not products:
            break

        for product in products:
            if args.max and total >= args.max:
                break

            if product["id"] in already_done:
                continue

            total += 1
            name = product["name"]
            number = product.get("number") or ""
            url = product["pricecharting_url"]
            product_id = product["id"]

            print(f"[{total}] {name} #{number}")
            print(f"   URL: {url}")

            try:
                pop = parse_pop_report_table(url)
                if pop:
                    count = upsert_pop_for_product(product_id, pop)
                    print(f"   ✅ Pop: {pop} → saved {count} grade records")
                    updated += 1
                else:
                    print(f"   ⚠️  No pop data found")
                    skipped += 1
            except Exception as e:
                print(f"   ❌ Error: {e}")
                skipped += 1

            time.sleep(args.delay)
            print()

        offset += batch_size

    print("=" * 50)
    print(f"Done. {total} processed | {updated} updated | {skipped} skipped")


if __name__ == "__main__":
    main()

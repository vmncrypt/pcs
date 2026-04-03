#!/usr/bin/env python3
"""
Remove old slug-based product duplicates left over from group merges.

Only deletes a slug-based product if a :Normal counterpart exists in the
same group pointing to the same pricecharting_url. That's the only safe
signal that both rows represent the same card.

Safe to re-run. Use --dry-run to preview first.
"""

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

AFFECTED_GROUPS = [
    "Pokemon Phantasmal Flames",
    "Pokemon Chinese Gem Pack 3",
    "Pokemon Evolving Skies",
    "Pokemon Obsidian Flames",
    "Pokemon Scarlet & Violet 151",
    "Pokemon Ascended Heroes",
    "Pokemon Japanese Inferno X",
    "Pokemon Japanese Mega Dream ex",
    "Pokemon Japanese Nihil Zero",
    "Pokemon Japanese Start Deck 100 Battle Collection",
]


def cleanup_group(group_name: str, dry_run: bool = False) -> int:
    resp = supabase.table("groups").select("id").eq("name", group_name).execute()
    if not resp.data:
        print(f"  {group_name}: group not found, skipping")
        return 0

    group_id = resp.data[0]["id"]

    # Fetch ALL products
    products = []
    offset = 0
    while True:
        batch = (
            supabase.table("products")
            .select("id, variant_key, pricecharting_url")
            .eq("group_id", group_id)
            .range(offset, offset + 999)
            .execute()
        )
        if not batch.data:
            break
        products.extend(batch.data)
        if len(batch.data) < 1000:
            break
        offset += 1000

    # Build: url -> list of products sharing that URL
    url_to_products: dict = {}
    for p in products:
        url = p.get("pricecharting_url")
        if url:
            url_to_products.setdefault(url, []).append(p)

    # Only delete slug-based products where a :Normal product shares the same URL
    to_delete = []
    for url, prods in url_to_products.items():
        if len(prods) < 2:
            continue
        has_new = any(':' in p["variant_key"] for p in prods)
        if has_new:
            for p in prods:
                if ':' not in p["variant_key"]:
                    to_delete.append(p["id"])

    if not to_delete:
        print(f"  {group_name}: no true duplicates found (same URL, different variant_key format)")
        return 0

    print(f"  {group_name}: {'would remove' if dry_run else 'removing'} {len(to_delete)} "
          f"slug-based products that have a :Normal duplicate")

    if not dry_run:
        for i in range(0, len(to_delete), 100):
            batch = to_delete[i:i + 100]
            supabase.table("products").delete().in_("id", batch).execute()

    return len(to_delete)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Remove slug-based products that have a :Normal duplicate")
    parser.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN — no changes will be made ===\n")

    total = 0
    for group_name in AFFECTED_GROUPS:
        total += cleanup_group(group_name, dry_run=args.dry_run)

    print(f"\n{'Would remove' if args.dry_run else 'Removed'} {total} duplicate products total.")
    if not args.dry_run and total > 0:
        print("\nNext: python export_to_app_format.py → bun run build:db:upload in BankTCG")


if __name__ == "__main__":
    main()

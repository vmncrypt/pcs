#!/usr/bin/env python3
"""
Merge duplicate groups that exist under multiple name variants.
Moves all products from old groups into the canonical group, deletes old groups.
Safe to re-run.
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

# (old_names_to_merge, canonical_name)
# All old groups will be merged into canonical, then deleted.
MERGES = [
    # Empty duplicate groups — just delete them
    (["Pokemon Chinese 151 Collect"],       "Pokemon Chinese 151 Collect"),  # keep the 308-card one
    (["Pokemon Japanese Nihil Zero"],       "Pokemon Japanese Nihil Zero"),  # keep the 120-card one

    # Inferno X — merge old into canonical
    (["Japanese Inferno X"],                "Pokemon Japanese Inferno X"),

    # Mega Dream — merge all variants into canonical
    (["Japanese Mega Dream Ex",
      "Japanese Mega Dream ex"],            "Pokemon Japanese Mega Dream ex"),

    # Start Deck Battle Collection — merge old into canonical
    (["Japanese Start Deck 100 Battle Collection"],
                                            "Pokemon Japanese Start Deck 100 Battle Collection"),
]


def get_group(name: str):
    """Returns list of groups matching name (may be duplicates)."""
    resp = supabase.table("groups").select("id, name").eq("name", name).execute()
    return resp.data


def merge(old_names: list, canonical_name: str, dry_run: bool):
    # Get all canonical groups (there may be duplicates of the canonical too)
    canonical_groups = get_group(canonical_name)

    if not canonical_groups:
        print(f"  ⚠️  Canonical '{canonical_name}' not found — skipping")
        return

    # If multiple groups share the canonical name, keep the one with most products
    if len(canonical_groups) > 1:
        counts = []
        for g in canonical_groups:
            c = supabase.table("products").select("id", count="exact").eq("group_id", g["id"]).execute().count
            counts.append((c, g))
        counts.sort(reverse=True)
        canonical_id = counts[0][1]["id"]
        # Delete the empty canonical duplicates
        for _, g in counts[1:]:
            c = supabase.table("products").select("id", count="exact").eq("group_id", g["id"]).execute().count
            print(f"  Deleting empty duplicate canonical '{canonical_name}' ({c} cards, id={g['id']})")
            if not dry_run:
                supabase.table("groups").delete().eq("id", g["id"]).execute()
    else:
        canonical_id = canonical_groups[0]["id"]

    canonical_count = supabase.table("products").select("id", count="exact").eq("group_id", canonical_id).execute().count

    # Merge each old group into canonical
    for old_name in old_names:
        if old_name == canonical_name:
            continue

        old_groups = get_group(old_name)
        if not old_groups:
            print(f"  '{old_name}': not found — already clean")
            continue

        for old_group in old_groups:
            old_id = old_group["id"]
            old_count = supabase.table("products").select("id", count="exact").eq("group_id", old_id).execute().count

            print(f"  '{old_name}' ({old_count} cards) → '{canonical_name}' ({canonical_count} cards)")

            if not dry_run:
                if old_count > 0:
                    # Fetch all products from both groups to detect variant_key conflicts
                    old_prods = supabase.table("products").select("id, variant_key").eq("group_id", old_id).execute().data
                    canonical_prods = supabase.table("products").select("id, variant_key").eq("group_id", canonical_id).execute().data
                    canonical_keys = {p["variant_key"]: p["id"] for p in canonical_prods}

                    to_move = []
                    to_delete_old = []
                    to_delete_canonical = []

                    for p in old_prods:
                        vk = p["variant_key"]
                        if vk not in canonical_keys:
                            to_move.append(p["id"])
                        else:
                            # Conflict — keep whichever has graded prices
                            old_has_grades = bool(supabase.table("graded_prices").select("product_id").eq("product_id", p["id"]).limit(1).execute().data)
                            can_has_grades = bool(supabase.table("graded_prices").select("product_id").eq("product_id", canonical_keys[vk]).limit(1).execute().data)

                            if old_has_grades and not can_has_grades:
                                # Old has grades, canonical doesn't — delete canonical, move old
                                to_delete_canonical.append(canonical_keys[vk])
                                to_move.append(p["id"])
                            else:
                                # Canonical has grades (or neither does) — delete old
                                to_delete_old.append(p["id"])

                    if to_delete_old:
                        for i in range(0, len(to_delete_old), 100):
                            supabase.table("products").delete().in_("id", to_delete_old[i:i+100]).execute()
                        print(f"    Deleted {len(to_delete_old)} conflicting old products (canonical had grades)")

                    if to_delete_canonical:
                        for i in range(0, len(to_delete_canonical), 100):
                            supabase.table("products").delete().in_("id", to_delete_canonical[i:i+100]).execute()
                        print(f"    Deleted {len(to_delete_canonical)} conflicting canonical products (old had grades)")

                    if to_move:
                        for i in range(0, len(to_move), 100):
                            supabase.table("products").update({"group_id": canonical_id}).in_("id", to_move[i:i+100]).execute()
                        print(f"    Moved {len(to_move)} products")

                supabase.table("groups").delete().eq("id", old_id).execute()
                canonical_count = supabase.table("products").select("id", count="exact").eq("group_id", canonical_id).execute().count
                print(f"    ✅ Done. '{canonical_name}' now has {canonical_count} cards")
            else:
                print(f"    would move {old_count} products and delete old group")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print("=== DRY RUN ===\n")

    for old_names, canonical in MERGES:
        print(f"\n→ {canonical}")
        merge(old_names, canonical, dry_run=args.dry_run)

    print("\nDone.")
    if not args.dry_run:
        print("Next: python export_to_app_format.py → bun run build:db:upload")


if __name__ == "__main__":
    main()

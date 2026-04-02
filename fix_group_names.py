#!/usr/bin/env python3
"""
Fix group naming inconsistencies in Supabase:
1. Merges duplicate groups (non-prefixed stubs into canonical prefixed groups)
2. Renames standalone groups to match PriceCharting canonical naming

Safe to re-run — skips already-fixed groups.
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

# (old_name, canonical_name)
# Products from old_name will be moved into canonical_name, then old_name deleted.
MERGES = [
    ("Scarlet & Violet: 151",         "Pokemon Scarlet & Violet 151"),
    ("Scarlet & Violet: Obsidian Flames", "Pokemon Obsidian Flames"),
    ("Sword & Shield: Evolving Skies", "Pokemon Evolving Skies"),
    ("Chinese Gem Pack 3",             "Pokemon Chinese Gem Pack 3"),
    ("Phantasmal Flames",              "Pokemon Phantasmal Flames"),
    ("Ascended Heroes",                "Pokemon Ascended Heroes"),  # guard against reappearing
]

# Groups with no duplicate — just rename in place.
RENAMES = [
    ("Perfect Order",     "Pokemon Perfect Order"),
    ("Chinese CSGC",      "Pokemon Chinese CSGC"),
    ("Chinese CSV8C",     "Pokemon Chinese CSV8C"),
    ("Chinese Gem Pack 4","Pokemon Chinese Gem Pack 4"),
]


def merge_group(old_name, new_name):
    resp = supabase.table("groups").select("id, name").in_("name", [old_name, new_name]).execute()
    groups = {g["name"]: g["id"] for g in resp.data}

    if old_name not in groups:
        print(f"  ✅ '{old_name}' not found — already clean.")
        return

    if new_name not in groups:
        print(f"  ⚠️  Canonical group '{new_name}' not found — skipping merge.")
        return

    old_id = groups[old_name]
    new_id = groups[new_name]

    # Fetch variant_keys already in canonical group to avoid conflicts
    existing_resp = supabase.table("products").select("variant_key").eq("group_id", new_id).execute()
    existing_keys = {p["variant_key"] for p in existing_resp.data}

    # Fetch products from old group
    old_resp = supabase.table("products").select("id, variant_key").eq("group_id", old_id).execute()
    old_products = old_resp.data

    to_move = [p for p in old_products if p["variant_key"] not in existing_keys]
    conflicts = len(old_products) - len(to_move)

    print(f"  '{old_name}' ({len(old_products)}) → '{new_name}': "
          f"moving {len(to_move)}, skipping {conflicts} conflicts")

    if to_move:
        ids_to_move = [p["id"] for p in to_move]
        # Move in batches of 100
        for i in range(0, len(ids_to_move), 100):
            batch = ids_to_move[i:i + 100]
            supabase.table("products").update({"group_id": new_id}).in_("id", batch).execute()

    # Delete old group (remaining products with conflicts are just deleted with it)
    # First delete any remaining products in old group (the conflicts)
    if conflicts > 0:
        supabase.table("products").delete().eq("group_id", old_id).execute()

    supabase.table("groups").delete().eq("id", old_id).execute()

    final = supabase.table("products").select("id", count="exact").eq("group_id", new_id).execute().count
    print(f"  ✅ Done. '{new_name}' now has {final} products.")


def rename_group(old_name, new_name):
    resp = supabase.table("groups").select("id, name").eq("name", old_name).execute()

    if not resp.data:
        print(f"  ✅ '{old_name}' not found — already renamed or doesn't exist.")
        return

    group_id = resp.data[0]["id"]
    supabase.table("groups").update({"name": new_name}).eq("id", group_id).execute()

    count = supabase.table("products").select("id", count="exact").eq("group_id", group_id).execute().count
    print(f"  ✅ Renamed '{old_name}' → '{new_name}' ({count} products)")


def main():
    print("=== Merging duplicate groups ===")
    for old_name, new_name in MERGES:
        print(f"\n{old_name} → {new_name}")
        merge_group(old_name, new_name)

    print("\n=== Renaming groups to canonical names ===")
    for old_name, new_name in RENAMES:
        print(f"\n{old_name} → {new_name}")
        rename_group(old_name, new_name)

    print("\n✅ All done.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
One-off script: merge "Ascended Heroes" into "Pokemon Ascended Heroes".

Moves all products from the old group to the canonical group, then deletes
the old group. Safe to run multiple times — will exit early if already fixed.
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

OLD_NAME = "Ascended Heroes"
NEW_NAME = "Pokemon Ascended Heroes"


def main():
    # Fetch both groups
    resp = supabase.table("groups").select("id, name").in_("name", [OLD_NAME, NEW_NAME]).execute()
    groups = {g["name"]: g["id"] for g in resp.data}

    if OLD_NAME not in groups:
        print(f"✅ '{OLD_NAME}' not found — already fixed, nothing to do.")
        return

    if NEW_NAME not in groups:
        print(f"❌ '{NEW_NAME}' not found — cannot merge. Check group names in Supabase.")
        return

    old_id = groups[OLD_NAME]
    new_id = groups[NEW_NAME]

    print(f"Old group: '{OLD_NAME}' (id: {old_id})")
    print(f"New group: '{NEW_NAME}' (id: {new_id})")

    # Count products in old group
    count_resp = supabase.table("products").select("id", count="exact").eq("group_id", old_id).execute()
    old_count = count_resp.count
    print(f"\nProducts in '{OLD_NAME}': {old_count}")

    if old_count == 0:
        print("No products to move.")
    else:
        print(f"Moving {old_count} products to '{NEW_NAME}'...")
        supabase.table("products").update({"group_id": new_id}).eq("group_id", old_id).execute()
        print(f"✅ Moved {old_count} products.")

    # Delete old group
    print(f"\nDeleting '{OLD_NAME}' group...")
    supabase.table("groups").delete().eq("id", old_id).execute()
    print(f"✅ Deleted '{OLD_NAME}'.")

    # Verify
    final = supabase.table("products").select("id", count="exact").eq("group_id", new_id).execute()
    print(f"\n✅ '{NEW_NAME}' now has {final.count} products.")


if __name__ == "__main__":
    main()

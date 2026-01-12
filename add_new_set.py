#!/usr/bin/env python3
"""
Simple script to add a new Pokemon set to Supabase.
Use this when a new set releases and you want to start tracking it.

Usage:
    python add_new_set.py "Pokemon Scarlet & Violet - Surging Sparks"
    python add_new_set.py --list  # Show all existing sets
"""

import os
import sys
from supabase import create_client

# Configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY environment variables must be set")
    sys.exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def list_sets():
    """List all existing sets in Supabase."""
    result = supabase.table("groups").select("id, name").order("name").execute()

    print(f"\n📦 Existing sets ({len(result.data)} total):\n")
    for group in result.data:
        print(f"  [{group['id']}] {group['name']}")
    print()


def add_set(set_name: str):
    """Add a new set to Supabase."""
    # Check if it already exists
    result = supabase.table("groups").select("name").eq("name", set_name).execute()

    if result.data:
        print(f"❌ Set '{set_name}' already exists!")
        return False

    # Insert new set
    try:
        result = supabase.table("groups").insert({"name": set_name}).execute()
        print(f"✅ Added new set: {set_name}")
        print(f"   Group ID: {result.data[0]['id']}")
        return True
    except Exception as e:
        print(f"❌ Error adding set: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # List mode
    if sys.argv[1] in ['--list', '-l', 'list']:
        list_sets()
        return

    # Add mode
    set_name = ' '.join(sys.argv[1:])

    print(f"\n➕ Adding new set: {set_name}")

    if add_set(set_name):
        print(f"\n✅ Success! Next steps:")
        print(f"   1. Import cards for this set using import_pokemon_data.py")
        print(f"   2. Or run sync_eligible_products.py to update tracking")
        print()


if __name__ == "__main__":
    main()

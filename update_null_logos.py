#!/usr/bin/env python3
"""
Update null logos in pokemon_enriched_series_data.json with correct URLs.

This script finds sets with null logos and updates them with the correct
Bulbapedia logo URLs based on manual mappings.

Usage:
    python update_null_logos.py
    python update_null_logos.py --dry-run
"""

import json
import argparse
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to the enriched series data
ENRICHED_PATH = "/Users/leon/Actual/Apps/Prod/BankTCG/assets/games/pokemon_enriched_series_data.json"

# Manual logo mappings for sets with null logos
# Format: "set_name": {"logo": "url", "logo_url": "url", "symbol_url": "url"}
LOGO_MAPPINGS = {
    "Scarlet & Violet: 151": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/1/12/SV2a_Pok%C3%A9mon_Card_151_Logo.png/220px-SV2a_Pok%C3%A9mon_Card_151_Logo.png",
        "logo_url": "https://archives.bulbagarden.net/media/upload/thumb/1/12/SV2a_Pok%C3%A9mon_Card_151_Logo.png/220px-SV2a_Pok%C3%A9mon_Card_151_Logo.png",
        "symbol_url": "https://archives.bulbagarden.net/media/upload/thumb/2/23/SetSymbolPok%C3%A9mon_Card_151.png/80px-SetSymbolPok%C3%A9mon_Card_151.png",
        "release_date": "September 22, 2023",
        "set_abbreviation": "MEW"
    },
    "Scarlet & Violet: Obsidian Flames": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/b/bd/SV3_Logo_EN.png/150px-SV3_Logo_EN.png",
        "logo_url": "https://archives.bulbagarden.net/media/upload/thumb/b/bd/SV3_Logo_EN.png/150px-SV3_Logo_EN.png",
        "symbol_url": "https://archives.bulbagarden.net/media/upload/thumb/1/16/SetSymbolRuler_of_the_Black_Flame.png/80px-SetSymbolRuler_of_the_Black_Flame.png",
        "release_date": "August 11, 2023",
        "set_abbreviation": "OBF"
    },
    "Japanese Start Deck 100 Battle Collection": {
        # This is a starter deck product, using the Start Deck 100 logo from the base set
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/e/e7/Start_Deck_100_Logo.png/220px-Start_Deck_100_Logo.png",
        "logo_url": "https://archives.bulbagarden.net/media/upload/thumb/e/e7/Start_Deck_100_Logo.png/220px-Start_Deck_100_Logo.png",
        "symbol_url": None,
        "release_date": "December 17, 2021",
        "set_abbreviation": None
    }
}


def load_json(filepath):
    """Load JSON file."""
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data, filepath):
    """Save JSON file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved to {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Update null logos in enriched series data")
    parser.add_argument('--dry-run', action='store_true', help="Preview without making changes")
    parser.add_argument('--enriched', default=ENRICHED_PATH,
                        help=f"Path to enriched series data (default: {ENRICHED_PATH})")
    args = parser.parse_args()

    logger.info("Updating null logos in enriched series data...")

    # Load data
    enriched_data = load_json(args.enriched)
    if enriched_data is None:
        logger.error("Could not load enriched series data")
        return

    # Find and update sets with null logos
    updated_count = 0
    null_logo_sets = []

    for item in enriched_data:
        name = item.get('name', '')
        logo = item.get('logo')

        if logo is None:
            null_logo_sets.append(name)

            if name in LOGO_MAPPINGS:
                mapping = LOGO_MAPPINGS[name]
                logger.info(f"Found mapping for: {name}")

                if args.dry_run:
                    logger.info(f"  [DRY RUN] Would update with logo: {mapping['logo']}")
                else:
                    # Update all fields from the mapping
                    for key, value in mapping.items():
                        if value is not None or key not in item:
                            item[key] = value
                    updated_count += 1
                    logger.info(f"  Updated logo: {mapping['logo']}")
            else:
                logger.warning(f"No mapping found for: {name}")

    # Report
    logger.info(f"\nSets with null logos: {len(null_logo_sets)}")
    for name in null_logo_sets:
        status = "(has mapping)" if name in LOGO_MAPPINGS else "(no mapping)"
        logger.info(f"  - {name} {status}")

    if args.dry_run:
        logger.info(f"\n[DRY RUN] Would update {updated_count} sets")
    else:
        if updated_count > 0:
            save_json(enriched_data, args.enriched)
            logger.info(f"\nUpdated {updated_count} sets with logos")
        else:
            logger.info("\nNo updates needed")


if __name__ == "__main__":
    main()

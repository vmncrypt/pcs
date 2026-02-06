#!/usr/bin/env python3
"""
Update missing logos in pokemon_enriched_series_data.json.

This script:
1. Parses extracted logos from Bulbapedia HTML
2. Uses fuzzy matching to find logos for sets with missing logos
3. Applies manual mappings for known sets
4. Updates the enriched data file

Usage:
    python update_missing_logos.py
    python update_missing_logos.py --dry-run
    python update_missing_logos.py --logos-file jp_logos.json
"""

import json
import argparse
import os
import re
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
ENRICHED_PATH = "/Users/leon/Actual/Apps/Prod/BankTCG/assets/games/pokemon_enriched_series_data.json"
DEFAULT_LOGOS_FILE = "jp_logos.json"

# Manual logo mappings for sets that need exact specification
# These take priority over fuzzy matching
MANUAL_MAPPINGS = {
    # Scarlet & Violet sets with colon naming
    "Scarlet & Violet: 151": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/1/12/SV2a_Pok%C3%A9mon_Card_151_Logo.png/220px-SV2a_Pok%C3%A9mon_Card_151_Logo.png",
        "symbol_url": "https://archives.bulbagarden.net/media/upload/thumb/2/23/SetSymbolPok%C3%A9mon_Card_151.png/80px-SetSymbolPok%C3%A9mon_Card_151.png",
        "release_date": "September 22, 2023",
        "set_abbreviation": "MEW"
    },
    "Scarlet & Violet: Obsidian Flames": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/b/bd/SV3_Logo_EN.png/150px-SV3_Logo_EN.png",
        "symbol_url": "https://archives.bulbagarden.net/media/upload/thumb/1/16/SetSymbolRuler_of_the_Black_Flame.png/80px-SetSymbolRuler_of_the_Black_Flame.png",
        "release_date": "August 11, 2023",
        "set_abbreviation": "OBF"
    },
    # Japanese sets that need manual mapping
    "Pokemon Japanese Mask of Change": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/d/d7/SV6a_Mask_of_Change_Logo.png/165px-SV6a_Mask_of_Change_Logo.png"
    },
    "Pokemon Japanese Miracle Twins": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/7/7c/SM11_Logo.png/150px-SM11_Logo.png"
    },
    "Pokemon Japanese Matchless Fighter": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/5/53/S5a_Matchless_Fighters_Logo.png/150px-S5a_Matchless_Fighters_Logo.png"
    },
    "Pokemon Japanese Dream Shine Collection": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/9/9f/CP5_Logo.png/150px-CP5_Logo.png"
    },
    "Pokemon Japanese Terastal Festival": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/9/9e/SV8a_Terastal_Fest_ex_Logo.png/150px-SV8a_Terastal_Fest_ex_Logo.png"
    },
    "Pokemon Korean Terastal Festival ex": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/9/9e/SV8a_Terastal_Fest_ex_Logo.png/150px-SV8a_Terastal_Fest_ex_Logo.png"
    },
    "Pokemon Japanese Heat Wave Arena": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/d/dc/SV6_Mask_of_Change_Logo_JP.png/165px-SV6_Mask_of_Change_Logo_JP.png"  # Part of Mask of Change era
    },
    "Pokemon Japanese Web": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/4/44/Pok%C3%A9mon_Card_web_Logo.png/150px-Pok%C3%A9mon_Card_web_Logo.png"
    },
    "Pokemon Japanese Challenge from the Darkness": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/3/38/SetSymbolGym_Booster.png/80px-SetSymbolGym_Booster.png"  # Gym Challenge equivalent
    },
    "Pokemon Fire Red & Leaf Green": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/5/5f/EX_FireRed_%26_LeafGreen_Logo.png/150px-EX_FireRed_%26_LeafGreen_Logo.png"
    },
    "Pokemon EX Latias & Latios": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/7/7e/EX_Dragon_Logo.png/150px-EX_Dragon_Logo.png"  # Part of EX Dragon era
    },
    # Japanese SVG Special Set
    "Pokemon Japanese SVG Special Set": {
        "logo": "https://archives.bulbagarden.net/media/upload/thumb/7/72/SV1_Logo_EN.png/150px-SV1_Logo_EN.png"
    },
}


def normalize_name(name):
    """Normalize set name for matching."""
    if not name:
        return ""
    n = name.lower().strip()
    # Remove common prefixes
    for prefix in ['pokemon ', 'japanese ', 'chinese ', 'korean ', 'scarlet & violet: ', 'sword & shield: ']:
        if n.startswith(prefix):
            n = n[len(prefix):]
    # Normalize punctuation
    n = re.sub(r'[:\-&]+', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def create_name_variants(name):
    """Create multiple variants of a set name for matching."""
    variants = set()
    variants.add(name)
    normalized = normalize_name(name)
    variants.add(normalized)

    # Add without prefixes
    for prefix in ['Pokemon ', 'Japanese ', 'Chinese ', 'Korean ', 'Pokemon Japanese ', 'Pokemon Chinese ', 'Pokemon Korean ']:
        if name.startswith(prefix):
            stripped = name[len(prefix):]
            variants.add(stripped)
            variants.add(normalize_name(stripped))

    # Handle "Scarlet & Violet:" prefix
    if 'Scarlet & Violet:' in name:
        stripped = name.replace('Scarlet & Violet:', '').strip()
        variants.add(stripped)
        variants.add(normalize_name(stripped))

    # Handle "Sword & Shield:" prefix
    if 'Sword & Shield:' in name:
        stripped = name.replace('Sword & Shield:', '').strip()
        variants.add(stripped)
        variants.add(normalize_name(stripped))

    return list(variants)


def load_extracted_logos(logos_file):
    """Load extracted logos from JSON file."""
    if not os.path.exists(logos_file):
        logger.warning(f"Logos file not found: {logos_file}")
        return {}

    with open(logos_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_logo_lookup(extracted_logos):
    """Build normalized lookup from extracted logos."""
    lookup = {}
    for name, url in extracted_logos.items():
        # Add original name
        lookup[name.lower().strip()] = url
        # Add normalized version
        lookup[normalize_name(name)] = url
    return lookup


def find_logo_match(set_name, logo_lookup):
    """Find a logo match for a set name using various strategies."""
    variants = create_name_variants(set_name)

    for variant in variants:
        key = variant.lower().strip()
        if key in logo_lookup:
            return logo_lookup[key]

        # Also try normalized version
        norm_key = normalize_name(variant)
        if norm_key in logo_lookup:
            return logo_lookup[norm_key]

    return None


def main():
    parser = argparse.ArgumentParser(description="Update missing logos in enriched series data")
    parser.add_argument('--dry-run', action='store_true', help="Preview without making changes")
    parser.add_argument('--enriched', default=ENRICHED_PATH,
                        help=f"Path to enriched series data (default: {ENRICHED_PATH})")
    parser.add_argument('--logos-file', default=DEFAULT_LOGOS_FILE,
                        help=f"Path to extracted logos JSON (default: {DEFAULT_LOGOS_FILE})")
    args = parser.parse_args()

    logger.info("Updating missing logos in enriched series data...")

    # Load enriched data
    if not os.path.exists(args.enriched):
        logger.error(f"Enriched data not found: {args.enriched}")
        return

    with open(args.enriched, 'r', encoding='utf-8') as f:
        enriched_data = json.load(f)

    logger.info(f"Loaded {len(enriched_data)} sets from enriched data")

    # Load extracted logos
    extracted_logos = load_extracted_logos(args.logos_file)
    logger.info(f"Loaded {len(extracted_logos)} extracted logos")

    # Build lookup
    logo_lookup = build_logo_lookup(extracted_logos)

    # Track updates
    updated_from_manual = []
    updated_from_extracted = []
    still_missing = []

    # Process each set
    for item in enriched_data:
        name = item.get('name', '')
        logo = item.get('logo')

        # Check if logo is missing
        if logo is None or logo == '' or logo == 'null':
            # First check manual mappings
            if name in MANUAL_MAPPINGS:
                mapping = MANUAL_MAPPINGS[name]
                if args.dry_run:
                    logger.info(f"[DRY RUN] Would update {name} (manual)")
                    logger.info(f"  -> {mapping.get('logo', '')[:80]}...")
                else:
                    for key, value in mapping.items():
                        item[key] = value
                    if 'logo' in mapping:
                        item['logo_url'] = mapping['logo']
                updated_from_manual.append(name)
            else:
                # Try fuzzy matching from extracted logos
                matched_logo = find_logo_match(name, logo_lookup)
                if matched_logo:
                    if args.dry_run:
                        logger.info(f"[DRY RUN] Would update {name} (extracted)")
                        logger.info(f"  -> {matched_logo[:80]}...")
                    else:
                        item['logo'] = matched_logo
                        item['logo_url'] = matched_logo
                    updated_from_extracted.append(name)
                else:
                    still_missing.append(name)

    # Report results
    logger.info(f"\n{'='*60}")
    logger.info(f"Results:")
    logger.info(f"  Updated from manual mappings: {len(updated_from_manual)}")
    logger.info(f"  Updated from extracted logos: {len(updated_from_extracted)}")
    logger.info(f"  Still missing: {len(still_missing)}")

    if updated_from_manual:
        logger.info(f"\nUpdated from manual mappings:")
        for name in updated_from_manual:
            logger.info(f"  + {name}")

    if updated_from_extracted:
        logger.info(f"\nUpdated from extracted logos:")
        for name in updated_from_extracted:
            logger.info(f"  + {name}")

    if still_missing:
        logger.info(f"\nStill missing ({len(still_missing)}):")
        for name in still_missing:
            logger.info(f"  - {name}")

    # Save updated data
    if not args.dry_run and (updated_from_manual or updated_from_extracted):
        with open(args.enriched, 'w', encoding='utf-8') as f:
            json.dump(enriched_data, f, indent=2, ensure_ascii=False)
        logger.info(f"\nSaved updated data to {args.enriched}")
        logger.info(f"Total updated: {len(updated_from_manual) + len(updated_from_extracted)} sets")
    elif args.dry_run:
        logger.info(f"\n[DRY RUN] Would update {len(updated_from_manual) + len(updated_from_extracted)} sets")


if __name__ == "__main__":
    main()

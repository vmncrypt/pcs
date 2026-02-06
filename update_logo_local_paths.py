#!/usr/bin/env python3
"""
Update logo_local paths in enriched data after downloading logo images.

This script scans the local logos directory and updates the enriched data
with logo_local paths for any sets that have a logo URL but no local path.

Usage:
    python update_logo_local_paths.py
    python update_logo_local_paths.py --dry-run
    python update_logo_local_paths.py --logos-dir /path/to/logos
"""

import json
import argparse
import os
import re
import logging
from pathlib import Path
from urllib.parse import urlparse, unquote

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Paths
ENRICHED_PATH = "/Users/leon/Actual/Apps/Prod/BankTCG/assets/games/pokemon_enriched_series_data.json"
LOGOS_DIR = "/Users/leon/Actual/Apps/Prod/BankTCG/assets/images/series-logos/pokemon"


def normalize_filename(name):
    """Create a normalized filename from a set name."""
    # Remove special characters and normalize
    safe = re.sub(r'[^\w\s-]', '', name.lower())
    safe = re.sub(r'[\s]+', '_', safe)
    return safe.strip('_')


def get_filename_from_url(url):
    """Extract filename from a Bulbapedia URL."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    # Get the original filename (before any resize suffix)
    # e.g., /media/upload/thumb/a/aa/SV3_Logo_JP.png/165px-SV3_Logo_JP.png
    parts = path.split('/')
    for part in reversed(parts):
        if 'Logo' in part and part.endswith('.png'):
            # Remove size prefix like "165px-"
            if re.match(r'^\d+px-', part):
                part = re.sub(r'^\d+px-', '', part)
            return part
    return None


def find_matching_file(name, url, logos_dir):
    """Find a matching logo file in the logos directory."""
    logos_path = Path(logos_dir)

    if not logos_path.exists():
        return None

    # Try different matching strategies
    candidates = []

    # 1. Try exact filename from URL
    url_filename = get_filename_from_url(url)
    if url_filename:
        candidates.append(url_filename)

    # 2. Try normalized name variations
    normalized = normalize_filename(name)
    candidates.extend([
        f"{normalized}.png",
        f"{normalized}_logo.png",
        f"pokemon_{normalized}.png",
    ])

    # 3. Try without "Pokemon" prefix
    if name.startswith('Pokemon '):
        short_name = normalize_filename(name[8:])
        candidates.extend([
            f"{short_name}.png",
            f"{short_name}_logo.png",
        ])

    # 4. Try without "Japanese"/"Korean"/"Chinese" prefix
    for lang in ['Japanese ', 'Korean ', 'Chinese ']:
        if lang in name:
            short_name = normalize_filename(name.replace('Pokemon ', '').replace(lang, ''))
            candidates.extend([
                f"{short_name}.png",
                f"japanese_{short_name}.png",
            ])

    # Check for matches
    for candidate in candidates:
        filepath = logos_path / candidate
        if filepath.exists():
            return candidate

    # Also try case-insensitive search
    existing_files = {f.name.lower(): f.name for f in logos_path.glob('*.png')}
    for candidate in candidates:
        if candidate.lower() in existing_files:
            return existing_files[candidate.lower()]

    return None


def main():
    parser = argparse.ArgumentParser(description="Update logo_local paths in enriched data")
    parser.add_argument('--dry-run', action='store_true', help="Preview without making changes")
    parser.add_argument('--enriched', default=ENRICHED_PATH,
                        help=f"Path to enriched series data")
    parser.add_argument('--logos-dir', default=LOGOS_DIR,
                        help=f"Path to logos directory")
    args = parser.parse_args()

    logger.info("Updating logo_local paths...")

    # Load enriched data
    with open(args.enriched, 'r', encoding='utf-8') as f:
        enriched_data = json.load(f)

    # Find sets needing local paths
    updated = []
    not_found = []

    for item in enriched_data:
        name = item.get('name', '')
        logo = item.get('logo')
        logo_local = item.get('logo_local')

        # Only process if has URL but no local path
        if logo and not logo_local:
            local_file = find_matching_file(name, logo, args.logos_dir)

            if local_file:
                if args.dry_run:
                    logger.info(f"[DRY RUN] Would set logo_local for {name}: {local_file}")
                else:
                    item['logo_local'] = local_file
                    item['logo_local_path'] = f"assets/images/series-logos/pokemon/{local_file}"
                updated.append((name, local_file))
            else:
                not_found.append(name)

    # Report
    logger.info(f"\n{'='*60}")
    logger.info(f"Results:")
    logger.info(f"  Updated: {len(updated)}")
    logger.info(f"  Not found: {len(not_found)}")

    if updated:
        logger.info(f"\nUpdated:")
        for name, local_file in updated:
            logger.info(f"  + {name} -> {local_file}")

    if not_found:
        logger.info(f"\nNot found (need to download):")
        for name in not_found:
            logger.info(f"  - {name}")

    # Save
    if not args.dry_run and updated:
        with open(args.enriched, 'w', encoding='utf-8') as f:
            json.dump(enriched_data, f, indent=2, ensure_ascii=False)
        logger.info(f"\nSaved to {args.enriched}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Download Pokemon series logos from Bulbapedia archives.

This script reads the enriched series data, downloads logos for sets
that have logo URLs, and saves them locally.

Usage:
    python download_pokemon_logos.py
    python download_pokemon_logos.py --input enriched_data.json --output logos/
"""

import os
import json
import argparse
import time
import re
import requests
from urllib.parse import urlparse

# Default paths
DEFAULT_INPUT = "pokemon_enriched_series_data.json"
DEFAULT_OUTPUT_DIR = "pokemon_logos"


def sanitize_filename(name):
    """Convert set name to safe filename."""
    # Remove special characters, replace spaces with underscores
    safe = re.sub(r'[^a-zA-Z0-9\-_]', '_', name)
    safe = re.sub(r'_+', '_', safe)  # Collapse multiple underscores
    return safe.lower().strip('_')


def download_file(url, filepath, session):
    """Download a file from URL to filepath."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://bulbapedia.bulbagarden.net/',
    }

    response = session.get(url, headers=headers, timeout=30, allow_redirects=True)
    response.raise_for_status()

    with open(filepath, 'wb') as f:
        f.write(response.content)

    return len(response.content)


def main():
    parser = argparse.ArgumentParser(description="Download Pokemon series logos")
    parser.add_argument('--input', '-i', default=DEFAULT_INPUT,
                        help=f"Input enriched series JSON file (default: {DEFAULT_INPUT})")
    parser.add_argument('--output', '-o', default=DEFAULT_OUTPUT_DIR,
                        help=f"Output directory for logos (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument('--delay', type=float, default=0.5,
                        help="Delay between downloads in seconds (default: 0.5)")
    args = parser.parse_args()

    print("🚀 Starting Pokemon logo download...")
    print(f"   Input: {args.input}")
    print(f"   Output: {args.output}")
    print()

    # Load enriched data
    if not os.path.exists(args.input):
        print(f"❌ Input file not found: {args.input}")
        return 1

    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"📄 Loaded {len(data)} series from JSON file")

    # Create output directory
    os.makedirs(args.output, exist_ok=True)

    # Stats
    downloaded = 0
    skipped = 0
    failed = 0
    already_exists = 0

    # Reuse session for connection pooling
    session = requests.Session()

    for i, series in enumerate(data, 1):
        name = series.get('name', f'unknown_{i}')
        logo_url = series.get('logo')
        prefix = f"[{i}/{len(data)}]"

        if not logo_url:
            print(f"{prefix} ⏭️  No logo URL: {name}")
            skipped += 1
            continue

        # Generate filename
        safe_name = sanitize_filename(name)
        parsed_url = urlparse(logo_url)
        ext = os.path.splitext(parsed_url.path)[1] or '.png'
        filename = f"{safe_name}{ext}"
        filepath = os.path.join(args.output, filename)

        # Skip if already exists
        if os.path.exists(filepath):
            print(f"{prefix} ✓ Already exists: {name}")
            series['logo_local'] = filename
            already_exists += 1
            continue

        # Download
        try:
            print(f"{prefix} ⬇️  Downloading: {name}")
            size = download_file(logo_url, filepath, session)
            series['logo_local'] = filename
            print(f"     ✅ Saved: {filename} ({size:,} bytes)")
            downloaded += 1
            time.sleep(args.delay)

        except Exception as e:
            print(f"     ❌ Failed: {e}")
            failed += 1

    # Save updated JSON with local paths
    output_json = os.path.join(args.output, "enriched_with_local_paths.json")
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n📝 Saved updated JSON: {output_json}")

    # Summary
    print()
    print("═" * 50)
    print("✨ DOWNLOAD COMPLETE")
    print("═" * 50)
    print(f"✅ Downloaded: {downloaded}")
    print(f"📁 Already existed: {already_exists}")
    print(f"⏭️  Skipped (no URL): {skipped}")
    print(f"❌ Failed: {failed}")
    print(f"📁 Logos saved to: {args.output}/")
    print("═" * 50)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())

#!/usr/bin/env python3
"""
Parse Bulbapedia HTML to extract Pokemon TCG set logo URLs.

This script parses saved Bulbapedia HTML files (Japanese or English expansions list)
and extracts set names with their corresponding logo URLs from archives.bulbagarden.net.

Usage:
    python parse_bulbapedia_logos.py jp.html
    python parse_bulbapedia_logos.py jp.html --output logos.json
"""

import re
import json
import argparse
import os
import logging
from urllib.parse import unquote

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_higher_res_url(img_tag):
    """Extract the highest resolution URL from an img tag."""
    # First try to get from srcset (highest resolution)
    srcset_match = re.search(r'srcset="([^"]*)"', img_tag)
    if srcset_match:
        srcset = srcset_match.group(1)
        # Parse srcset and get the 2x or 1.5x version
        for part in srcset.split(','):
            part = part.strip()
            if ' 2x' in part:
                return part.replace(' 2x', '').strip()
            elif ' 1.5x' in part:
                return part.replace(' 1.5x', '').strip()

    # Fall back to src
    src_match = re.search(r'src="([^"]*)"', img_tag)
    if src_match:
        return src_match.group(1)
    return None


def extract_set_names_from_row(row_html):
    """Extract English and Japanese set names from a table row."""
    names = []

    # Look for wiki links to TCG pages
    wiki_links = re.findall(r'<a[^>]*href="/wiki/([^"]+)"[^>]*title="([^"]+)"[^>]*>', row_html)
    for wiki_path, title in wiki_links:
        # Skip non-set links
        if any(x in title.lower() for x in ['file:', 'symbol', 'logo', 'category']):
            continue
        # Decode URL encoding
        title = unquote(title).replace('_', ' ')
        if '(TCG)' in title:
            title = title.replace(' (TCG)', '')
        names.append(title)

    # Also extract plain text from cells that might be set names
    cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
    for cell in cells:
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', cell)
        text = re.sub(r'\s+', ' ', text).strip()
        # Look for English-looking set names
        if text and len(text) > 3 and len(text) < 100:
            # Skip if it's a date or number
            if not re.match(r'^\d+$', text) and not re.match(r'^[A-Z][a-z]+ \d+, \d+$', text):
                if re.search(r'[A-Za-z]', text):
                    names.append(text)

    return list(set(names))  # Remove duplicates


def parse_html_file(filepath):
    """Parse HTML file and extract logo mappings."""
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return {}

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    logos = {}

    # Find all rows in tables
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', content, re.DOTALL | re.IGNORECASE)

    for row in rows:
        # Check if this row has a logo image
        logo_imgs = re.findall(r'<img[^>]*Logo[^>]*>', row, re.IGNORECASE)
        if not logo_imgs:
            continue

        # Get the best logo URL
        for img_tag in logo_imgs:
            if 'archives.bulbagarden.net' in img_tag and 'Logo' in img_tag:
                logo_url = get_higher_res_url(img_tag)
                if logo_url:
                    # Find set names for this row
                    names = extract_set_names_from_row(row)
                    for name in names:
                        if name and name not in logos:
                            # Clean up the name
                            name = name.strip()
                            if len(name) > 2 and 'Logo' not in name and 'Symbol' not in name:
                                logos[name] = logo_url
                    break  # Use first valid logo in row

    return logos


def normalize_name(name):
    """Normalize set name for matching."""
    if not name:
        return ""
    # Lowercase and strip
    n = name.lower().strip()
    # Remove common prefixes
    for prefix in ['pokemon ', 'japanese ', 'chinese ', 'korean ']:
        if n.startswith(prefix):
            n = n[len(prefix):]
    # Normalize punctuation
    n = re.sub(r'[:\-&]+', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def create_name_variants(name):
    """Create multiple variants of a set name for matching."""
    variants = [name]

    # Add without "Pokemon" prefix
    if name.startswith('Pokemon '):
        variants.append(name[8:])

    # Add without "Japanese"/"Chinese"/"Korean" prefix
    for lang in ['Japanese ', 'Chinese ', 'Korean ']:
        if lang in name:
            variants.append(name.replace(lang, ''))
            variants.append(name.replace('Pokemon ' + lang, '').strip())

    # Add with different punctuation
    variants.append(name.replace(': ', ' '))
    variants.append(name.replace(' & ', ' and '))

    return [v.strip() for v in variants if v.strip()]


def main():
    parser = argparse.ArgumentParser(description="Parse Bulbapedia HTML for logo URLs")
    parser.add_argument('html_file', help="Path to saved Bulbapedia HTML file")
    parser.add_argument('--output', '-o', default='bulbapedia_logos.json',
                        help="Output JSON file for logo mappings")
    parser.add_argument('--match-missing', '-m',
                        help="Path to enriched data JSON to find matches for missing logos")
    args = parser.parse_args()

    logger.info(f"Parsing {args.html_file}...")

    logos = parse_html_file(args.html_file)

    logger.info(f"Found {len(logos)} sets with logos in HTML")

    # Save to JSON
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(logos, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved to {args.output}")

    # If matching with missing logos
    if args.match_missing:
        logger.info(f"\nMatching with missing logos from {args.match_missing}...")

        with open(args.match_missing, 'r', encoding='utf-8') as f:
            enriched_data = json.load(f)

        # Build normalized lookup from extracted logos
        normalized_logos = {}
        for name, url in logos.items():
            norm = normalize_name(name)
            normalized_logos[norm] = {'original_name': name, 'url': url}

        # Find sets with missing logos
        matches_found = {}
        still_missing = []

        for item in enriched_data:
            name = item.get('name', '')
            logo = item.get('logo')

            if logo is None or logo == '' or logo == 'null':
                # Try to find a match
                variants = create_name_variants(name)
                matched = False

                for variant in variants:
                    norm = normalize_name(variant)
                    if norm in normalized_logos:
                        match_info = normalized_logos[norm]
                        matches_found[name] = {
                            'matched_to': match_info['original_name'],
                            'logo_url': match_info['url']
                        }
                        matched = True
                        break

                if not matched:
                    still_missing.append(name)

        logger.info(f"\nMatches found: {len(matches_found)}")
        for name, info in sorted(matches_found.items()):
            logger.info(f"  {name}")
            logger.info(f"    -> {info['matched_to']}")

        logger.info(f"\nStill missing: {len(still_missing)}")
        for name in still_missing:
            logger.info(f"  - {name}")

        # Save matches
        matches_file = args.output.replace('.json', '_matches.json')
        with open(matches_file, 'w', encoding='utf-8') as f:
            json.dump({
                'matches': matches_found,
                'still_missing': still_missing
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"\nSaved matches to {matches_file}")


if __name__ == "__main__":
    main()

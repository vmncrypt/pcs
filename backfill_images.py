#!/usr/bin/env python3
"""
Backfill images for products that have a PriceCharting URL but no image.

This is a one-time backfill script to populate images for existing products.
Run manually when needed (e.g., after adding new sets).

Usage:
    python backfill_images.py
    python backfill_images.py --dry-run      # Preview without updating
    python backfill_images.py --limit 100    # Process only 100 products
    python backfill_images.py --batch-size 50 --delay 1.5
"""

import os
import argparse
import time
import random
import concurrent.futures
import logging
from dotenv import load_dotenv
from supabase import create_client, Client
import requests
from bs4 import BeautifulSoup

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Global session for connection reuse
session = requests.Session()


def fetch_page(url, retries=3):
    """Fetch HTML content from the given URL with retries."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for i in range(retries):
        try:
            response = session.get(url, headers=headers, timeout=20)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.warning(f"Attempt {i+1} failed for {url}: {e}")
            time.sleep(2 * (i + 1))

    logger.error(f"Failed to fetch {url} after {retries} attempts")
    return None


def scrape_image_url(pricecharting_url):
    """Scrape the image URL from a PriceCharting product page."""
    html = fetch_page(pricecharting_url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    # Try primary selector: div.cover img
    img = soup.select_one('div.cover img')
    if img and img.get("src"):
        return img.get("src")

    # Fallback: img with itemprop="image"
    img = soup.select_one('img[itemprop="image"]')
    if img and img.get("src"):
        return img.get("src")

    # Fallback: any img in the product info area
    img = soup.select_one('#product img')
    if img and img.get("src"):
        return img.get("src")

    return None


def get_products_without_images(limit=None):
    """Fetch products that have pricecharting_url but no image."""
    logger.info("Fetching products without images...")

    all_products = []
    offset = 0
    batch_size = 1000

    while True:
        query = (
            supabase.table("products")
            .select("id, name, number, pricecharting_url")
            .not_.is_("pricecharting_url", "null")
            .is_("image", "null")
            .range(offset, offset + batch_size - 1)
        )

        response = query.execute()

        if not response.data:
            break

        all_products.extend(response.data)
        logger.info(f"  Fetched {len(all_products)} products so far...")

        if len(response.data) < batch_size:
            break

        offset += batch_size

        if limit and len(all_products) >= limit:
            all_products = all_products[:limit]
            break

    return all_products


def process_product(product, idx, total):
    """Process a single product - scrape image and return update payload."""
    product_id = product["id"]
    name = product["name"]
    number = product.get("number", "")
    url = product["pricecharting_url"]

    # Random delay to avoid burst patterns
    time.sleep(random.uniform(0.5, 1.5))

    display_name = f"{name} #{number}" if number else name
    logger.info(f"[{idx}/{total}] Scraping image for: {display_name}")

    image_url = scrape_image_url(url)

    if image_url:
        logger.info(f"  ✅ Found image: {image_url[:60]}...")
        return {"id": product_id, "image": image_url}
    else:
        logger.warning(f"  ⚠️  No image found")
        return None


def update_products_batch(updates):
    """Update products with images in batch."""
    if not updates:
        return 0

    success_count = 0
    for update in updates:
        try:
            supabase.table("products").update({
                "image": update["image"]
            }).eq("id", update["id"]).execute()
            success_count += 1
        except Exception as e:
            logger.error(f"Error updating product {update['id']}: {e}")

    return success_count


def main():
    parser = argparse.ArgumentParser(description="Backfill images for products")
    parser.add_argument("--dry-run", action="store_true", help="Preview without updating")
    parser.add_argument("--limit", type=int, default=None, help="Maximum products to process")
    parser.add_argument("--batch-size", type=int, default=50, help="Products per batch before writing")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests (seconds)")
    parser.add_argument("--workers", type=int, default=3, help="Number of parallel workers")
    args = parser.parse_args()

    logger.info("🖼️  Starting Image Backfill...")
    logger.info(f"   Batch size: {args.batch_size}")
    logger.info(f"   Delay: {args.delay}s")
    logger.info(f"   Workers: {args.workers}")
    if args.limit:
        logger.info(f"   Limit: {args.limit} products")
    if args.dry_run:
        logger.info("   Mode: DRY RUN (no changes will be made)")

    # Get products needing images
    products = get_products_without_images(limit=args.limit)
    logger.info(f"\nFound {len(products)} products needing images.")

    if not products:
        logger.info("No products need image backfill!")
        return

    # Process in batches
    total_updated = 0
    total_found = 0
    batch_updates = []

    def process_wrapper(args_tuple):
        product, idx, total = args_tuple
        time.sleep(random.uniform(0.5, args.delay))
        return process_product(product, idx, len(products))

    # Use thread pool for parallel processing
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        tasks = [(p, i, len(products)) for i, p in enumerate(products, 1)]
        results = executor.map(process_wrapper, tasks)

        for i, result in enumerate(results, 1):
            if result:
                total_found += 1
                batch_updates.append(result)

            # Write batch when full
            if len(batch_updates) >= args.batch_size:
                if args.dry_run:
                    logger.info(f"\n[DRY RUN] Would update {len(batch_updates)} products")
                else:
                    logger.info(f"\n💾 Writing batch of {len(batch_updates)} images...")
                    updated = update_products_batch(batch_updates)
                    total_updated += updated
                    logger.info(f"   Updated {updated} products")
                batch_updates = []

    # Write remaining batch
    if batch_updates:
        if args.dry_run:
            logger.info(f"\n[DRY RUN] Would update {len(batch_updates)} products")
        else:
            logger.info(f"\n💾 Writing final batch of {len(batch_updates)} images...")
            updated = update_products_batch(batch_updates)
            total_updated += updated

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("🖼️  IMAGE BACKFILL COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Products processed: {len(products)}")
    logger.info(f"Images found: {total_found} ({total_found/len(products)*100:.1f}%)")
    if args.dry_run:
        logger.info(f"Products that would be updated: {total_found}")
        logger.info("(DRY RUN - no actual changes made)")
    else:
        logger.info(f"Products updated: {total_updated}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

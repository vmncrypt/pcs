import os
import argparse
import time
import re
from datetime import datetime
import logging
from dotenv import load_dotenv
from supabase import create_client, Client
import requests
from bs4 import BeautifulSoup
import json

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

CHINESE_SET_CATEGORY_ID = 100

# Global session
session = requests.Session()

def fetch_page(url, retries=3):
    """Fetch HTML content from the given URL with retries."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Simple rate limiting
    time.sleep(2)
    
    for i in range(retries):
        try:
            # Use session
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

def parse_price(price_str):
    """Clean and convert price string to float. Returns None if invalid."""
    if not price_str:
        return None
    # Remove '$', ',' and whitespace
    clean_str = re.sub(r'[^\d.]', '', price_str)
    if not clean_str:
        return None
    try:
        return float(clean_str)
    except ValueError:
        return None

def scrape_set_cards_list(set_url):
    """Scrape the list of cards from a set page, handling pagination."""
    all_cards = []
    cursor = None
    page = 1
    
    while True:
        if page == 1:
            logger.info(f"Fetching page {page} for {set_url}")
            html = fetch_page(set_url)
        else:
            if not cursor:
                break
            logger.info(f"Fetching page {page} (cursor: {cursor})")
            # POST request for next pages
            try:
                time.sleep(2)  # Rate limiting
                response = session.post(set_url, data={"cursor": cursor}, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }, timeout=20)
                if response.status_code != 200:
                    logger.warning(f"Failed to fetch page {page}: Status {response.status_code}")
                    break
                html = response.text
            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

        if not html:
            break
            
        soup = BeautifulSoup(html, "lxml")
        
        # Try different table selectors
        table = soup.find("table", id="games_table")
        if not table:
            table = soup.find("table", class_="hover_table")
            
        if not table:
            if page == 1:
                logger.warning(f"Could not find card table for {set_url}")
            break
            
        # Parse rows
        rows = table.find_all("tr")
        current_page_cards = []
        
        for row in rows:
            # Extract Product ID
            product_id = row.get("data-product")
            if not product_id:
                # Fallback to ID attribute
                row_id = row.get("id", "")
                if row_id.startswith("product-"):
                    product_id = row_id.replace("product-", "")
            
            if not product_id:
                continue
                
            # Extract Title and URL
            title_cell = row.find("td", class_="title")
            if not title_cell:
                continue
                
            link = title_cell.find("a")
            if not link:
                continue
                
            name = link.text.strip()
            href = link.get("href")
            if not href:
                continue
                
            full_url = "https://www.pricecharting.com" + href
            
            # Extract Price (Ungraded)
            price_cell = row.select_one("td.used_price .js-price")
            price_str = price_cell.text.strip() if price_cell else None
            
            price = parse_price(price_str)
            
            current_page_cards.append({
                "product_id": int(product_id),
                "name": name,
                "url": full_url,
                "price": price
            })
            
        logger.info(f"Page {page}: Found {len(current_page_cards)} cards.")
        all_cards.extend(current_page_cards)

        # Check for cursor for next page
        # Look for <input type="hidden" name="cursor" value="...">
        cursor_input = soup.find("input", {"name": "cursor"})
        if cursor_input:
            cursor = cursor_input.get("value")
            page += 1
        else:
            break
            
    return all_cards

def scrape_card_details(card_url):
    """Visit card page and extract detailed metadata."""
    html = fetch_page(card_url)
    if not html:
        return None
        
    soup = BeautifulSoup(html, "lxml")
    
    data = {}
    
    # 1. Product ID
    # Look for "PriceCharting ID:" row
    # Structure: <tr><td class="title">PriceCharting ID:</td><td class="details">12345</td></tr>
    product_id = None
    
    # Try finding in the details table
    details_table = soup.select_one("#itemdetails table")
    if details_table:
        for tr in details_table.find_all("tr"):
            if "PriceCharting ID" in tr.get_text():
                 # Valid row, try to get the second cell
                 tds = tr.find_all("td")
                 if len(tds) >= 2:
                     text_val = tds[1].get_text().strip()
                     if text_val.isdigit():
                         product_id = int(text_val)
                         break
    
    # Fallback: Search all table rows if specific ID table missed
    if not product_id:
        for tr in soup.find_all("tr"):
            if "PriceCharting ID" in tr.get_text():
                text = tr.get_text()
                match = re.search(r'PriceCharting ID:?\s*(\d+)', text)
                if match:
                    product_id = int(match.group(1))
                    break

    data["product_id"] = product_id
    
    # 2. Image URL
    # <div class="cover"> <img src="...">
    img = soup.select_one('div.cover img')
    if img:
        data["image_url"] = img.get("src")
    else:
        # Fallback
        img = soup.select_one('img[itemprop="image"]')
        if img:
             data["image_url"] = img.get("src")
        else:
             data["image_url"] = None
        
    # 3. Market Price
    # <td id="used_price"> <span class="price js-price">$6.91</span>
    price_cell = soup.find("td", id="used_price")
    market_price = None
    if price_cell:
        span = price_cell.find("span", class_="js-price")
        if span:
            market_price = parse_price(span.get_text())
            
    data["market_price"] = market_price
    
    return data

def parse_card_name_number(full_name):
    """Split name into name and number (after #)."""
    # Ex: "Chandelure #1107" -> "Chandelure", "1107"
    # Ex: "Gengar" -> "Gengar", None
    
    if "#" in full_name:
        parts = full_name.rsplit("#", 1)
        name = parts[0].strip()
        number = parts[1].strip()
        return name, number
    return full_name, None

import concurrent.futures
import random

def process_card_wrapper(args):
    """Wrapper for parallel processing."""
    group_id, card, i, total, set_code_default = args
    card_url = card["url"]
    
    # Random sleep to avoid exact burst patterns
    time.sleep(random.uniform(0.5, 1.5))
    
    logger.info(f"[{i}/{total}] Scraping: {card['name']}")
    details = scrape_card_details(card_url)
    
    if not details or not details["product_id"]:
        logger.warning(f"Could not scrape details for {card['name']} ({card_url})")
        return None
        
    market_price = details["market_price"]
    
    # Skip if no price (as per original logic)
    if market_price is None:
        return None
        
    clean_name, number = parse_card_name_number(card["name"])
    product_id = details["product_id"]
    
    return {
        "variant_key": f"{product_id}:Normal",
        "date": datetime.today().strftime('%Y-%m-%d'),
        "price": market_price,
        "product_id": product_id,
        "product_name": clean_name,
        "clean_name": clean_name,
        "group_id": group_id,
        "rarity": None,
        "number": number,
        "image_url": details["image_url"],
        "finish": "Normal",
        "pricecharting_url": card_url,
        "sku": None,
        "set_code": set_code_default,
        "product_line_name": None,
        "release_date": None,
        "low_price": None,
        "high_price": None,
        "image_count": 1
    }

def get_existing_product_ids(group_id):
    """Fetch existing product IDs for a group to check what needs scraping."""
    try:
        # We need to match based on the PriceCharting ID (stored in product_id column)
        # We select product_id from products table
        response = (
            supabase.table("products")
            .select("product_id")
            .eq("group_id", group_id)
            .execute()
        )
        return {item["product_id"] for item in response.data if item["product_id"]}
    except Exception as e:
        logger.error(f"Error fetching existing products: {e}")
        return set()

def process_set(group_id, set_url):
    """Process a single set with optimized hybrid strategy."""
    logger.info(f"Processing Set: {set_url} (Group ID: {group_id})")
    
    # 1. Get List of Cards (Enriched with Price & ID)
    cards_list = scrape_set_cards_list(set_url)
    logger.info(f"Found {len(cards_list)} potential cards in set.")
    
    if not cards_list:
        return

    # 2. Get Existing Products
    existing_ids = get_existing_product_ids(group_id)
    
    to_scrape = []
    batch_data = []
    
    # 3. Separate Updates vs New Scrapes
    for card in cards_list:
        pid = card["product_id"]
        
        # Valid price check (skip if no price, as before)
        if card["price"] is None:
            continue
            
        if pid in existing_ids:
            # OPTIMIZATION: Product exists, just push price update
            # We don't need to visit the card page
            payload = {
                "variant_key": f"{pid}:Normal",
                "date": datetime.today().strftime('%Y-%m-%d'),
                "price": card["price"],
                "product_id": pid,
                # Fields below aren't strictly needed for update but helpful context
                "group_id": group_id,
                "finish": "Normal"
            }
            batch_data.append(payload)
        else:
            # NEW Card: Needs scraping for Image URL & Metadata
            to_scrape.append(card)
            
    logger.info(f"Optimization: {len(batch_data)} updates (fast), {len(to_scrape)} new cards (scrape).")

    # 4. Process New Cards (Multithreaded)
    if to_scrape:
        max_workers = 3
        map_args = [(group_id, card, i, len(to_scrape), None) for i, card in enumerate(to_scrape, 1)]
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(process_card_wrapper, map_args))
            
        # Add scraped results to batch
        scraped_payloads = [r for r in results if r is not None]
        batch_data.extend(scraped_payloads)
    
    # 5. Flush Batch
    # Send in chunks of 50
    chunk_size = 50
    for i in range(0, len(batch_data), chunk_size):
        chunk = batch_data[i:i + chunk_size]
        flush_batch(chunk)

def flush_batch(batch_data):
    """Send batch to Supabase RPC."""
    if not batch_data:
        return

    try:
        logger.info(f"Syncing batch of {len(batch_data)} cards...")
        response = supabase.rpc('batch_update_price_history', {'batch_data': batch_data}).execute()
        
        # Log the actual response data to debug
        if response.data:
            logger.info(f"RPC Response: {json.dumps(response.data, indent=2)}")
        else:
            logger.warning("RPC returned no data.")
            
        logger.info("✅ Batch synced successfully.")
    except Exception as e:
        logger.error(f"❌ Error syncing batch: {e}")

def main():
    parser = argparse.ArgumentParser(description="Backfill Chinese Pokemon Cards")
    parser.add_argument("--set-id", type=int, help="Specific Group ID to process (optional)")
    args = parser.parse_args()
    
    logger.info("🚀 Starting Chinese Card Backfill...")

    # 1. Fetch Chinese Groups
    query = supabase.table("groups").select("id, name, set_url").eq("category_id", CHINESE_SET_CATEGORY_ID)
    
    if args.set_id:
        query = query.eq("id", args.set_id)
    
    # Only sets that have a URL
    query = query.not_.is_("set_url", "null")
    
    response = query.execute()
    groups = response.data
    
    logger.info(f"Found {len(groups)} Chinese sets to process.")
    
    for group in groups:
        process_set(group["id"], group["set_url"])

    logger.info("✨ Backfill Complete.")

if __name__ == "__main__":
    main()
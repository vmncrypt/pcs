import os
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

URL = "https://www.pricecharting.com/category/pokemon-cards"
CHINESE_SET_CATEGORY_ID = 100

def fetch_page(url):
    """Fetch HTML content from the given URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Error fetching URL {url}: {e}")
        return None

def extract_chinese_sets(html_content):
    """Extract Pokemon Chinese sets from HTML."""
    soup = BeautifulSoup(html_content, "lxml")
    set_links = soup.find_all("a", href=True)
    
    sets = []
    seen_names = set()
    
    for link in set_links:
        href = link['href']
        text = link.text.strip()
        
        if href.startswith("/console/pokemon-"):
            if text and text.startswith("Pokemon Chinese") and text not in seen_names:
                full_url = "https://www.pricecharting.com" + href
                sets.append({
                    "name": text,
                    "set_url": full_url
                })
                seen_names.add(text)
    return sets

def get_existing_groups():
    """Fetch existing Chinese set names from the groups table."""
    try:
        response = (
            supabase.table("groups")
            .select("name, set_url")
            .eq("category_id", CHINESE_SET_CATEGORY_ID)
            .execute()
        )
        # return map of name -> set_url
        return {item["name"]: item.get("set_url") for item in response.data}
    except Exception as e:
        logger.error(f"Error fetching existing groups: {e}")
        return {}

def get_next_id():
    """Get the next available ID for the groups table."""
    try:
        # Fetch the group with the highest ID
        response = (
            supabase.table("groups")
            .select("id")
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        if response.data:
            return response.data[0]["id"] + 1
        return 1
    except Exception as e:
        logger.error(f"Error fetching max ID: {e}")
        # Identify if we should fail or default. Choosing to raise/fail to be safe.
        raise

def sync_sets(scraped_sets):
    """Sync scraped sets to the groups table."""
    existing_groups = get_existing_groups()
    existing_names = set(existing_groups.keys())
    
    new_sets = []
    updates = []
    
    # Needs to be determined at insert time to handle concurrency mostly,
    # but for this script we can just fetch once if running solo.
    next_id = 0
    
    # Pre-calculate new sets so we know how many IDs we need
    sets_to_add = []
    for s in scraped_sets:
        name = s["name"]
        url = s["set_url"]
        
        if name not in existing_names:
            sets_to_add.append(s)
        elif existing_groups[name] != url:
            # Existing group, but URL is missing or changed
            updates.append({
                "name": name,
                "set_url": url
            })
            
    # 1. Insert New Sets
    if sets_to_add:
        try:
            next_id = get_next_id()
            logger.info(f"Adding {len(sets_to_add)} new groups starting from ID {next_id}...")
            
            payloads = []
            for i, s in enumerate(sets_to_add):
                payloads.append({
                    "id": next_id + i,
                    "name": s["name"],
                    "category_id": CHINESE_SET_CATEGORY_ID,
                    "set_url": s["set_url"]
                })
                
            supabase.table("groups").insert(payloads).execute()
            logger.info("✅ Successfully added new groups.")
        except Exception as e:
            logger.error(f"❌ Error inserting new groups: {e}")
    else:
        logger.info("No new groups to add.")
        
    # 2. Update Existing Sets (if URL missing)
    if updates:
        logger.info(f"Updating {len(updates)} existing groups with new URLs...")
        for update in updates:
            try:
                # We update by name + category_id since scraping doesn't know ID
                # Ideally we'd validte uniqueness constraint
                supabase.table("groups").update({
                    "set_url": update["set_url"]
                }).eq("name", update["name"]).eq("category_id", CHINESE_SET_CATEGORY_ID).execute()
            except Exception as e:
                logger.error(f"❌ Error updating group {update['name']}: {e}")
        logger.info("✅ Updates complete.")
    else:
        logger.info("No existing groups needed updates.")

def main():
    logger.info("🚀 Starting Chinese Set Sync...")
    
    # 1. Scrape
    html = fetch_page(URL)
    if not html:
        return
        
    chinese_sets = extract_chinese_sets(html)
    logger.info(f"Found {len(chinese_sets)} Chinese sets on PriceCharting.")
    
    # 2. Sync
    sync_sets(chinese_sets)
    logger.info("✨ Sync Complete.")

if __name__ == "__main__":
    main()
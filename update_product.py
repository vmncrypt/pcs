import os
import sys
import argparse
import math
import re
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Check for environment variables before importing anything that might need them
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error: Please set SUPABASE_URL and SUPABASE_KEY environment variables in .env")
    sys.exit(1)

from supabase import create_client, Client
from main import scrape_pricecharting, parse_sales_for_grade, parse_pop_report, fetch

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# SCRAPING LOGIC (from process_db.py)
# ==========================================

def parse_card_name(name):
    """
    Extract the clean card name by removing everything after ' -' or ' ('.
    """
    if not name:
        return ""
    clean = re.split(r'\s+-|\s+\(', name)[0].strip()
    return clean

def parse_card_number(number):
    """
    Extract the card number before the '/' character and remove leading zeros.
    """
    if not number:
        return ""
    clean = number.split('/')[0].strip()
    clean = clean.lstrip('0') or '0'
    return clean

def extract_ebay_item_id(url):
    """
    Extract eBay Item ID from URL.
    """
    if not url:
        return None
    match = re.search(r"/itm/(\d+)(?:\?|$)", url)
    return match.group(1) if match else None

def save_graded_sales(product_id, scraped_data):
    """
    Save graded sales data to normalized graded_sales table.
    """
    grades = scraped_data.get("grades", {})
    sales_records = []

    for grade_label, sales_list in grades.items():
        if not isinstance(sales_list, list):
            continue

        for sale in sales_list:
            if not isinstance(sale, dict):
                continue

            date_str = sale.get('date')
            price = sale.get('price')
            url = sale.get('url')
            title = sale.get('title', '')

            if not date_str or price is None or not url:
                continue
            
            ebay_item_id = extract_ebay_item_id(url)
            if not ebay_item_id:
                continue

            try:
                # Try ISO format first (YYYY-MM-DD)
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
            except ValueError:
                try:
                    # Try text format (Nov 3, 2024)
                    parsed_date = datetime.strptime(date_str, "%b %d, %Y").date().isoformat()
                except ValueError:
                    print(f"   ⚠️  Could not parse date: {date_str}")
                    continue

            sales_records.append({
                'product_id': product_id,
                'grade': grade_label,
                'sale_date': parsed_date,
                'price': float(price),
                'ebay_item_id': ebay_item_id,
                'title': title
            })

    if not sales_records:
        return True

    try:
        # Upsert sales records
        supabase.table('graded_sales').upsert(
            sales_records,
            on_conflict='ebay_item_id'
        ).execute()
        print(f"   ✅ Saved {len(sales_records)} new sales records")
        return True
    except Exception as e:
        print(f"   ❌ Error saving graded sales: {e}")
        return False

def scrape_and_save(product, verbose=True):
    """
    Scrape product and save sales to DB.
    """
    if verbose:
        print(f"📦 Processing: {product['name']} (Variant: {product.get('variant_key')})")

    pricecharting_url = product.get("pricecharting_url")
    
    try:
        if pricecharting_url:
            if verbose:
                print(f"   Using existing URL: {pricecharting_url}")
            
            soup = fetch(pricecharting_url)
            result = {
                "product_url": pricecharting_url,
                "grades": {},
                "pop_report": {}
            }

            # Grade mapping
            grade_tabs = {
                "completed-auctions-grade-twenty": "BGS 10 Black Label",
                "completed-auctions-grade-nineteen": "CGC 10 Pristine",
                "completed-auctions-manual-only": "PSA 10",
                "completed-auctions-loose-and-box": "BGS 10",
                "completed-auctions-grade-seventeen": "CGC 10",
                "completed-auctions-grade-eighteen": "SGC 10",
                "completed-auctions-grade-twenty-one": "TAG 10",
                "completed-auctions-grade-twenty-two": "ACE 10",
                "completed-auctions-box-only": "PSA 9.5",
                "completed-auctions-graded": "PSA 9",
                "completed-auctions-new": "PSA 8",
                "completed-auctions-cib": "PSA 7",
                "completed-auctions-grade-six": "PSA 6",
                "completed-auctions-grade-five": "PSA 5",
                "completed-auctions-grade-four": "PSA 4",
                "completed-auctions-grade-three": "PSA 3",
                "completed-auctions-box-and-manual": "PSA 2",
                "completed-auctions-loose-and-manual": "PSA 1"
            }

            for css_class, grade_label in grade_tabs.items():
                sales = parse_sales_for_grade(pricecharting_url, css_class, soup=soup)
                result["grades"][grade_label] = sales

            result["pop_report"] = parse_pop_report(pricecharting_url, soup=soup)

        else:
            # Search
            raw_name = product.get("name")
            raw_number = product.get("number")
            clean_name = parse_card_name(raw_name)
            clean_number = parse_card_number(raw_number) if raw_number else ""
            
            search_query = f"{clean_name} {clean_number}".strip() if clean_number else clean_name.strip()
            
            if verbose:
                print(f"   Search: {search_query}")
                
            result = scrape_pricecharting(search_query, test_mode=False, set_name=product.get("group_name"), verbose=False)

        # Save sales
        save_graded_sales(product["id"], result)
        
        # Update product info (pop count, url)
        supabase.table("products").update({
            "pop_count": result.get("pop_report", {}),
            "pricecharting_url": result.get("product_url")
        }).eq("id", product["id"]).execute()
        
        return True

    except Exception as e:
        print(f"   ❌ Error scraping: {e}")
        return False


# ==========================================
# PRICING LOGIC (from backfill_graded_prices.ts)
# ==========================================

def calculate_market_price(sales, half_life=21):
    """
    Calculate the market price using liquidity-aware formula.
    """
    if not sales:
        return {"price": -1, "sample_size": 0, "effective_liquidity": 0, "liquidity_factor": 0}

    parsed_sales = []
    max_timestamp = 0
    
    for sale in sales:
        try:
            dt = datetime.fromisoformat(sale['sale_date'])
            ts = dt.timestamp()
            if ts > max_timestamp:
                max_timestamp = ts
            parsed_sales.append({"sale": sale, "ts": ts})
        except Exception:
            continue
            
    if not parsed_sales:
        return {"price": -1, "sample_size": 0, "effective_liquidity": 0, "liquidity_factor": 0}

    sales_with_weights = []
    for item in parsed_sales:
        sale = item["sale"]
        ts = item["ts"]
        days_since = (max_timestamp - ts) / (24 * 60 * 60)
        safe_days_since = max(0, days_since)
        weight = math.pow(2, -safe_days_since / half_life)
        sales_with_weights.append({"sale": sale, "weight": weight})

    sum_weights = sum(item["weight"] for item in sales_with_weights)
    
    if sum_weights == 0:
        return {"price": -1, "sample_size": len(sales), "effective_liquidity": 0, "liquidity_factor": 0}

    weighted_log_sum = sum(item["weight"] * math.log(item["sale"]["price"]) for item in sales_with_weights)
    fair_price = math.exp(weighted_log_sum / sum_weights)
    effective_liquidity = sum_weights
    liquidity_factor = min(1, math.sqrt(effective_liquidity))
    market_value = fair_price * liquidity_factor
    
    return {
        "price": market_value,
        "sample_size": len(sales),
        "effective_liquidity": effective_liquidity,
        "liquidity_factor": liquidity_factor
    }

def update_graded_prices(product_id):
    """
    Fetch sales, calculate prices, and upsert to graded_prices.
    """
    print(f"\n🧮 Calculating graded prices...")
    
    # Fetch all sales
    all_sales = []
    page = 0
    while True:
        try:
            r = supabase.table("graded_sales").select("*").eq("product_id", product_id).range(page*1000, (page+1)*1000-1).execute()
            if not r.data: break
            all_sales.extend(r.data)
            if len(r.data) < 1000: break
            page += 1
        except Exception as e:
            print(f"❌ Error fetching sales: {e}")
            return False

    if not all_sales:
        print("   ⚠️ No sales to calculate.")
        return True

    # Group by grade
    grade_sales_map = defaultdict(list)
    for sale in all_sales:
        if sale.get("grade"):
            grade_sales_map[sale.get("grade")].append(sale)

    # Calculate
    all_prices = []
    for grade, group in grade_sales_map.items():
        res = calculate_market_price(group)
        all_prices.append({
            "product_id": product_id,
            "grade": grade,
            "market_price": res["price"],
            "sample_size": res["sample_size"],
            "last_updated": datetime.now().isoformat()
        })

    # Upsert
    if all_prices:
        try:
            supabase.table("graded_prices").upsert(all_prices, on_conflict="product_id,grade").execute()
            print(f"   ✅ Updated prices for {len(all_prices)} grades")
            
            supabase.table("product_grade_progress").update({
                "completed": True,
                "updated_at": datetime.now().isoformat()
            }).eq("product_id", product_id).execute()
            
        except Exception as e:
            print(f"❌ Error updating prices: {e}")
            return False
            
    return True

# ==========================================
# MAIN EXECUTION
# ==========================================

def fetch_product_by_id(product_id):
    try:
        res = supabase.table("products").select("id, name, number, group_id, pricecharting_url, variant_key").eq("id", product_id).execute()
        if not res.data: return None
        prod = res.data[0]
        if prod.get("group_id"):
            g_res = supabase.table("groups").select("name").eq("id", prod["group_id"]).execute()
            if g_res.data: prod["group_name"] = g_res.data[0]["name"]
        return prod
    except Exception as e:
        print(f"❌ Error fetching product: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Update Single Product")
    parser.add_argument("product_id", type=str, help="Product UUID")
    args = parser.parse_args()

    print(f"� Updating product: {args.product_id}")
    product = fetch_product_by_id(args.product_id)
    if not product:
        print("❌ Product not found")
        sys.exit(1)

    print(f"\n1️⃣  Scraping...")
    if not scrape_and_save(product):
        print("❌ Scraping failed")
        sys.exit(1)

    print(f"\n2️⃣  Pricing...")
    if not update_graded_prices(args.product_id):
        print("❌ Pricing failed")
        sys.exit(1)

    print(f"\n✅ Success!")

if __name__ == "__main__":
    main()
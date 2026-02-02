import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
import argparse
import json
import re

BASE_URL = "https://www.pricecharting.com"


def fetch(url):
    """Fetch HTML and return BS4 soup"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    html = requests.get(url, headers=headers)
    return BeautifulSoup(html.text, "lxml")


def strip_query_params(url):
    """Strip query parameters from URL (everything after '?')."""
    return url.split('?')[0] if url else url


def search_product(query, set_name=None):
    """Returns URL of product page (either direct redirect or best match from search results)."""
    # Clean set name: remove everything after ":"
    if set_name and ':' in set_name:
        set_name = set_name.split(':')[0].strip()

    search_url = f"{BASE_URL}/search-products?type=prices&q={quote(query)}"
    response = requests.get(search_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, allow_redirects=True, timeout=30)

    # Check if we were redirected to a product page (URL contains /game/)
    if '/game/' in response.url:
        return strip_query_params(response.url)

    soup = BeautifulSoup(response.text, "lxml")

    # Try to find games_table first
    games_table = soup.select_one('table#games_table')
    if games_table:
        rows = games_table.select("tr[data-product]")
    else:
        # Fallback to hover_table
        hover_table = soup.select_one('table.hover_table')
        if hover_table:
            rows = hover_table.select("tr[data-product]")
        else:
            rows = []

    if not rows:
        raise ValueError("No matching product found.")

    # If set_name is provided, try to find best match
    if set_name:
        best_match = find_best_set_match(rows, set_name)
        if best_match:
            # href is already a full URL
            href = best_match["href"]
            if href.startswith("http"):
                return strip_query_params(href)
            else:
                return strip_query_params(BASE_URL + href)

    # Otherwise grab first result
    link = rows[0].select_one("td.title a")
    href = link["href"]
    if href.startswith("http"):
        return strip_query_params(href)
    else:
        return strip_query_params(BASE_URL + href)


def find_best_set_match(rows, set_name):
    """Find the best matching product based on set name similarity."""
    import difflib

    best_score = 0
    best_link = None

    # Normalize the set name for comparison
    set_name_normalized = set_name.lower().strip()

    for row in rows:
        link = row.select_one("td.title a")
        console_cell = row.select_one("td.console")

        if not link or not console_cell:
            continue

        # Get the console/set name from the result
        result_set = console_cell.text.strip().lower()

        # Calculate similarity score
        score = difflib.SequenceMatcher(None, set_name_normalized, result_set).ratio()

        if score > best_score:
            best_score = score
            best_link = link

    # Return best match if score is reasonable (>0.3 threshold)
    if best_score > 0.3:
        return best_link

    return None


def parse_sales_for_grade(product_url, grade_class, soup=None):
    """Parse completed listings for a specific PSA grade (correct tab isolation)."""
    if soup is None:
        soup = fetch(product_url)

    # Find all divs with this class, then filter out the tab button
    # The content section has ONLY the grade_class, not the 'tab' class
    sections = soup.find_all("div", class_=grade_class)
    section = None
    for sec in sections:
        # Skip tab buttons (they have 'tab' in their class list)
        if 'tab' not in sec.get('class', []):
            section = sec
            break

    if not section:
        return []

    tbody = section.find("tbody")
    if not tbody:
        return []

    rows = tbody.select("tr[id^='ebay-']")

    sales = []
    for r in rows:
        date = r.select_one("td.date").text.strip()
        title_link = r.select_one("td.title a")
        price = r.select_one("td.numeric .js-price").text.strip()
        href = title_link["href"]

        # Normalize currency format
        num = float(re.sub(r"[^\d.]", "", price))

        sales.append({
            "date": date,
            "price_raw": price,
            "price": num,
            "url": href,
            "title": title_link.text.strip()
        })

    return sales



def parse_pop_report(product_url, soup=None):
    """Return PSA POP count in dictionary format: {grade: count}"""
    if soup is None:
        url = product_url + "#population-report"
        soup = fetch(url)

    pop_table = soup.select_one("table.population tbody tr")

    # Handle case where POP report doesn't exist
    if not pop_table:
        return {}

    cells = pop_table.select("td.numeric")

    if not cells:
        return {}

    return {idx: int(cell.text.strip().replace(",", "")) for idx, cell in enumerate(cells, start=1)}


def scrape_pricecharting(query, test_mode=False, set_name=None, verbose=True):
    """Full scraping function"""
    if verbose:
        print(f"🔍 Searching PriceCharting for: {query}")

    product_url = search_product(query, set_name=set_name)

    if verbose:
        print(f"✅ Product page found: {product_url}")

    # Fetch the page once and reuse for all parsing
    soup = fetch(product_url)

    result = {"product_url": product_url, "grades": {}, "pop_report": {}}

    # Map CSS class to grade string representation
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
        sales = parse_sales_for_grade(product_url, css_class, soup=soup)
        result["grades"][grade_label] = sales

        if test_mode:
            print(f"\n--- {grade_label} ---")
            print(f"Total sales: {len(sales)}")

            if len(sales) > 0:
                sample = sales[0]
                print(f"Sample sale: {sample['date']} | {sample['price_raw']} | {sample['url']}")

    result["pop_report"] = parse_pop_report(product_url, soup=soup)

    if test_mode:
        print("\nPOP Report (grade -> count):")
        print(result["pop_report"])

    return result


# ----------------- CLI ENTRY -----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape PriceCharting sold listings + POP report")
    parser.add_argument("query", type=str, help="Search string for product")
    parser.add_argument("--test", action="store_true", help="Print counts + sample instead of full JSON")

    args = parser.parse_args()

    data = scrape_pricecharting(args.query, args.test)

    if not args.test:
        print(json.dumps(data, indent=4))
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from supabase import create_client, Client
from main import scrape_pricecharting, parse_sales_for_grade, parse_pop_report, fetch

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_product_by_variant_key(variant_key):
    """Fetch a product from the database by its variant_key."""
    response = (
        supabase.table("products")
        .select("id, name, number, group_id, pricecharting_url, variant_key")
        .eq("variant_key", variant_key)
        .execute()
    )

    if not response.data or len(response.data) == 0:
        return None

    product = response.data[0]

    # Fetch group name if group_id exists
    if product.get("group_id"):
        group_response = (
            supabase.table("groups")
            .select("name")
            .eq("id", product["group_id"])
            .execute()
        )
        if group_response.data and len(group_response.data) > 0:
            product["group_name"] = group_response.data[0]["name"]
        else:
            product["group_name"] = None
    else:
        product["group_name"] = None

    return product


def save_graded_sales(product_id, scraped_data):
    """Save graded sales data to normalized graded_sales table."""
    grades = scraped_data.get("grades", {})
    sales_records = []

    for grade_label, sales_list in grades.items():
        if not isinstance(sales_list, list):
            continue

        try:
            grade = int(grade_label.split()[-1])
        except (ValueError, IndexError):
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

            # Parse date
            try:
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
            except ValueError:
                try:
                    parsed_date = datetime.strptime(date_str, "%b %d, %Y").date().isoformat()
                except ValueError:
                    continue

            sales_records.append({
                'product_id': product_id,
                'grade': grade,
                'sale_date': parsed_date,
                'price': float(price),
                'ebay_url': url,
                'title': title
            })

    if not sales_records:
        return True, 0

    try:
        supabase.table('graded_sales').upsert(
            sales_records,
            on_conflict='product_id,sale_date,price,ebay_url'
        ).execute()
        return True, len(sales_records)
    except Exception as e:
        return False, str(e)


def update_product_data(product_id, pop_count, pricecharting_url):
    """Update the products table with pop_count and pricecharting_url."""
    try:
        supabase.table("products").update({
            "pop_count": pop_count,
            "pricecharting_url": pricecharting_url
        }).eq("id", product_id).execute()
        return True
    except Exception as e:
        return False


def parse_card_name(name):
    """Extract clean card name by removing everything after ' -' or ' ('."""
    if not name:
        return ""
    import re
    clean = re.split(r'\s+-|\s+\(', name)[0].strip()
    return clean


def parse_card_number(number):
    """Extract card number before '/' and remove leading zeros."""
    if not number:
        return ""
    clean = number.split('/')[0].strip()
    clean = clean.lstrip('0') or '0'
    return clean


def scrape_product_internal(product_data):
    """Scrape a single product and save to database. Returns result dict."""
    product_id = product_data.get("id")
    variant_key = product_data.get("variant_key")
    raw_name = product_data.get("name")
    raw_number = product_data.get("number")
    group_name = product_data.get("group_name")
    pricecharting_url = product_data.get("pricecharting_url")

    try:
        # If we already have a pricecharting_url, use it directly
        if pricecharting_url:
            soup = fetch(pricecharting_url)

            result = {
                "product_url": pricecharting_url,
                "grades": {},
                "pop_report": {}
            }

            grade_tabs = {
                "completed-auctions-cib": "PSA 7",
                "completed-auctions-new": "PSA 8",
                "completed-auctions-graded": "PSA 9",
                "completed-auctions-manual-only": "PSA 10"
            }

            for css_class, grade in grade_tabs.items():
                sales = parse_sales_for_grade(pricecharting_url, css_class, soup=soup)
                result["grades"][grade] = sales

            result["pop_report"] = parse_pop_report(pricecharting_url, soup=soup)

        else:
            # Need to search for the product first
            clean_name = parse_card_name(raw_name)
            clean_number = parse_card_number(raw_number) if raw_number else ""

            if clean_number:
                search_query = f"{clean_name} {clean_number}".strip()
            else:
                search_query = clean_name.strip()

            result = scrape_pricecharting(search_query, test_mode=False, set_name=group_name, verbose=False)

        # Count sales
        total_sales = sum(len(sales) for sales in result.get("grades", {}).values())
        pop_count = len(result.get('pop_report', {}))

        # Save to database
        sales_success, sales_count = save_graded_sales(product_id, result)
        product_success = update_product_data(product_id, result.get("pop_report", {}), result.get("product_url"))

        return {
            "success": True,
            "variant_key": variant_key,
            "product_id": product_id,
            "product_name": raw_name,
            "stats": {
                "total_sales": total_sales,
                "pop_grades": pop_count,
                "sales_saved": sales_count if isinstance(sales_count, int) else 0
            },
            "pricecharting_url": result.get("product_url")
        }

    except Exception as e:
        return {
            "success": False,
            "variant_key": variant_key,
            "product_id": product_id,
            "error": str(e)
        }


# ==================== API ROUTES ====================

@app.route('/', methods=['GET'])
def home():
    """Health check endpoint."""
    return jsonify({
        "service": "PriceCharting Scraper API",
        "status": "running",
        "endpoints": {
            "scrape": "/api/scrape/<variant_key>",
            "health": "/health"
        }
    })


@app.route('/health', methods=['GET'])
def health():
    """Health check for monitoring."""
    return jsonify({"status": "healthy"}), 200


@app.route('/api/scrape/<variant_key>', methods=['POST', 'GET'])
def scrape_product_api(variant_key):
    """
    Scrape a single product by variant_key.

    GET/POST /api/scrape/<variant_key>

    Returns:
    {
        "success": true,
        "variant_key": "sv3pt5-173",
        "product_id": "12345",
        "product_name": "Charizard ex",
        "stats": {
            "total_sales": 45,
            "pop_grades": 10,
            "sales_saved": 45
        },
        "pricecharting_url": "https://..."
    }
    """
    try:
        # Fetch product from database
        product = fetch_product_by_variant_key(variant_key)

        if not product:
            return jsonify({
                "success": False,
                "error": f"Product not found with variant_key: {variant_key}"
            }), 404

        # Scrape the product
        result = scrape_product_internal(product)

        status_code = 200 if result["success"] else 500
        return jsonify(result), status_code

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/scrape', methods=['POST'])
def scrape_product_body():
    """
    Scrape a single product by variant_key (passed in request body).

    POST /api/scrape
    Body: { "variant_key": "sv3pt5-173" }

    Returns same format as /api/scrape/<variant_key>
    """
    try:
        data = request.get_json()

        if not data or 'variant_key' not in data:
            return jsonify({
                "success": False,
                "error": "Missing variant_key in request body"
            }), 400

        variant_key = data['variant_key']

        # Fetch product from database
        product = fetch_product_by_variant_key(variant_key)

        if not product:
            return jsonify({
                "success": False,
                "error": f"Product not found with variant_key: {variant_key}"
            }), 404

        # Scrape the product
        result = scrape_product_internal(product)

        status_code = 200 if result["success"] else 500
        return jsonify(result), status_code

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

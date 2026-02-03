# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PriceCharting PSA Grade Scraper - An automated system that scrapes PSA graded card sales data from PriceCharting and stores it in Supabase. The system runs via GitHub Actions every 5 days and provides a Flask API for on-demand scraping.

## Commands

### Python Commands

```bash
# Install dependencies
pip install -r requirements.txt

# === NEW SET MANAGEMENT ===
# Add a new Pokemon set when it releases
python add_new_set.py "Pokemon Scarlet & Violet - Surging Sparks"

# List all existing sets
python add_new_set.py --list

# Convert PriceCharting HTML to JSON (copy/paste tbody from browser)
python convert_html_to_json.py new_set.html "Pokemon Scarlet & Violet - Surging Sparks"

# Import cards from converted JSON
python import_cards_from_json.py new_set_cards.json

# Automated scraping (may be blocked by Cloudflare)
python scrape_new_sets.py --all --output scraped_data.json

# === DATA IMPORT/EXPORT ===
# Import Pokemon data from BankTCG source
python import_pokemon_data.py

# Export Supabase data to BankTCG app format (with images)
python export_to_app_format.py

# Import missing sets as placeholders
python import_missing_sets.py

# === AUTOMATIC SET DISCOVERY ===
# Discover all new Pokemon sets from PriceCharting
python sync_all_sets.py
python sync_all_sets.py --dry-run

# Backfill cards for newly discovered sets
python backfill_new_sets.py
python backfill_new_sets.py --dry-run
python backfill_new_sets.py --set-id <group_id>
python backfill_new_sets.py --max-sets 5

# === SCRAPING OPERATIONS ===
# Sync eligible products to progress table
python sync_eligible_products.py

# Update prices from BankTCG source (LOCAL ONLY)
python update_prices_from_source.py

# Process incomplete products (scrape graded sales)
python process_db.py --batch-size 100 --delay 2.0

# Test scraping a single product
python scrape_single_product.py "sv3pt5-199"

# === API ===
# Run Flask API locally
python api.py
```

### Environment Variables

Required for all scripts:
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase service role key (not anon key)

## Adding New Sets

When a new Pokemon TCG set releases:

1. **Add the set:** `python add_new_set.py "Set Name"`
2. **Import cards:** `python import_pokemon_data.py` (if you have updated JSON)
3. **Sync eligible:** `python sync_eligible_products.py`
4. **Done!** GitHub Actions handles graded sales scraping automatically

See [NEW_SETS.md](NEW_SETS.md) for detailed guide.

**Note:** Bulbapedia/PriceCharting may block automated scraping. Manual process is fastest and most reliable.

## Architecture

### Data Flow Pipeline

```
BankTCG Source Data (pokemon-cards-base-data.json)
    ↓
import_pokemon_data.py (initial import)
    ↓
Supabase Database (products, groups)
    ↓
sync_eligible_products.py (filters market_price >= $15)
    ↓
product_grade_progress (tracks completion status)
    ↓
GitHub Actions (every 5 days)
    ├─ Job 1: sync_eligible_products.py (sync products)
    └─ Job 2: process_db.py (scrape PriceCharting)
    ↓
graded_sales table (individual sales)
    ↓
graded_prices table (computed market prices)
    ↓
export_to_app_format.py (export with images)
    ↓
BankTCG App (pokemon-cards-final-data-with-ids.json)
```

### Database Schema

**groups** - Pokemon sets/series
- `name` - Set name (e.g., "Pokemon Base Set", "Pokemon Celebrations")
- Foreign key for products

**products** - Main product table
- `group_id` - References groups.id
- `variant_key` - Unique identifier (e.g., "sv3pt5-199")
- `name`, `number` - Card name and number
- `market_price` - Current market price (used for eligibility filtering)
- `rarity` - Estimated rarity (Common, Uncommon, Rare, Ultra Rare)
- `pricecharting_url` - Cached PriceCharting URL (saves search time on re-scrapes)
- `pop_count` - JSONB field storing PSA population report (grades 1-10)

**product_grade_progress** - Tracks scraping progress
- `product_id` (PK) - References products.id
- `completed` - Boolean flag (false = needs scraping)

**graded_sales** - Normalized sales data
- Unique constraint: `(product_id, sale_date, price, ebay_url)`
- Stores individual PSA 7/8/9/10 sales
- Upsert strategy prevents duplicates

**graded_prices** - Computed market prices
- `product_id, grade` - Composite unique key
- `market_price` - Calculated from recent sales
- `sample_size` - Number of sales used in calculation
- Set to `-1` when no sales data available

### Key Components

**import_pokemon_data.py** - Initial data import
- Reads BankTCG JSON data (pokemon-cards-base-data.json)
- Creates groups and products in Supabase
- Deduplicates by variant_key
- Estimates rarity based on price

**export_to_app_format.py** - Export to app format
- Fetches data from Supabase (products, groups, graded_prices)
- Reads image URLs from original BankTCG source data
- Exports to BankTCG app JSON format with images
- Includes grade9 and psa10 prices from scraping

**import_missing_sets.py** - Import placeholder sets
- Compares enriched series data with Supabase
- Creates empty groups for missing sets
- Ready for future scraping or data import

**sync_all_sets.py** - Automatic set discovery
- Scrapes PriceCharting Pokemon category page
- Discovers all Pokemon sets (not just Chinese)
- Adds new sets to groups table with set_url
- Updates existing sets if URL is missing

**backfill_new_sets.py** - Automatic card backfill
- Finds sets with set_url but no products (empty groups)
- Scrapes card data from PriceCharting set pages
- Adds cards to products table with images
- Supports --dry-run, --set-id, --max-sets options

**sync_eligible_products.py** - Product syncing
- Filters products: `market_price >= $15 AND (rarity OR number exists)`
- Syncs to `product_grade_progress` with `completed=false`

**update_prices_from_source.py** - Price sync (LOCAL ONLY)
- Reads BankTCG source data
- Updates market_price in Supabase
- Detects cards crossing $15 threshold
- ⚠️ Requires local BankTCG files - do not run in GitHub Actions

**main.py** - Core scraper module
- `search_product()` - Searches PriceCharting, handles redirects and fuzzy set matching
- `parse_sales_for_grade()` - Extracts PSA 7/8/9/10 sales from product page
- `parse_pop_report()` - Extracts population counts for all grades
- `scrape_pricecharting()` - Main orchestration function

**process_db.py** - Database integration
- Fetches products from `product_grade_progress` where `completed=false`
- Uses cached `pricecharting_url` if available (skips search)
- Saves sales to `graded_sales` via upsert (duplicates ignored)
- Updates `products.pop_count` with population data
- Marks products as completed
- Computes graded market prices after scraping

**scrape_single_product.py** - Single product scraper
- Scrapes a single product by variant_key
- Useful for testing or one-off scrapes

**api.py** - Flask REST API
- Deployed on Render.com (kept warm via GitHub Actions cron)
- `POST /api/scrape/<variant_key>` - Scrape single product by variant_key
- `GET /health` - Health check endpoint
- CORS enabled for frontend access

### PriceCharting Scraping Logic

**Name Parsing:**
- Input: `"Pikachu VMAX - Rainbow Rare"`
- Output: `"Pikachu VMAX"` (removes everything after ` -` or ` (`)

**Number Parsing:**
- Input: `"044/185"`
- Output: `"44"` (strips leading zeros, removes everything after `/`)

**Set Name Cleaning:**
- Input: `"Sword & Shield: Vivid Voltage"`
- Output: `"Sword & Shield"` (removes everything after `:`)

**Search Query Format:**
- Pattern: `"{name} {number}"` (no `#` symbol)
- Example: `"Pikachu VMAX 44"`

**Product Matching:**
1. Check if search redirects to `/game/` URL (direct match)
2. If search results page:
   - Look for `table#games_table`, fallback to `table.hover_table`
   - Use fuzzy matching on set name (>0.3 similarity threshold)
   - Pick best match

**Grade Mapping (PriceCharting CSS classes):**
- PSA 7: `completed-auctions-cib`
- PSA 8: `completed-auctions-new`
- PSA 9: `completed-auctions-graded`
- PSA 10: `completed-auctions-manual-only`

### Market Price Calculation Logic

Located in `process_db.py:compute_graded_prices()`

**Algorithm:**
1. Filter sales by specific grade
2. Sort by date descending (most recent first)
3. **If sales exist from last 2 weeks:**
   - Use average of all sales from last 14 days
   - Return `{ price: average, sampleSize: count }`
4. **Otherwise:**
   - Use average of last 1-3 sales
   - Return `{ price: average, sampleSize: count }`
5. **If no sales:**
   - Return `{ price: -1, sampleSize: 0 }`

**Important:** Price is set to `-1` (not `null` or `0`) when no sales data exists.

### GitHub Actions Workflows

**scrape_grades.yml** - Main scraping workflow
- Trigger: Every 5 days at 2 AM UTC, push to main, manual dispatch
- 2 sequential jobs:
  1. `sync` - Syncs eligible products (30 min timeout)
  2. `scrape-batch-1` - Scrapes all products with 2s delay, computes prices (~4.3 hours)

**update_prices.yml** - Price update workflow (DISABLED)
- Manual trigger only (requires local BankTCG files)
- Not meant to run in GitHub Actions

**sync_new_sets.yml** - New set discovery workflow
- Trigger: Weekly on Sundays at 1 AM UTC, manual dispatch
- 2 steps:
  1. `sync_all_sets.py` - Discovers new sets from PriceCharting category page
  2. `backfill_new_sets.py` - Scrapes cards for newly discovered sets (empty groups)

**scrape_chinese_sets.yml** - Chinese set scraping workflow
- Trigger: Weekly on Sundays at 4 AM UTC, manual dispatch
- 2 steps:
  1. `sync_chinese_sets.py` - Syncs Chinese Pokemon sets
  2. `backfill_chinese_cards.py` - Backfills cards for Chinese sets

**keep_render_warm.yml** - Render instance warmup
- Trigger: Every 10 minutes
- Pings `RENDER_HEALTH_URL` to prevent cold starts
- Uses 5s connect timeout, 15s max timeout

### Deployment

**GitHub Actions:**
- Requires secrets: `SUPABASE_URL`, `SUPABASE_KEY`
- Free tier: 2,000 minutes/month
- Current usage: ~1,536 minutes/month

**Render.com (Flask API):**
- Uses `render.yaml` blueprint
- Free tier includes cold starts (warmed by GitHub Actions)
- Requires secrets: `SUPABASE_URL`, `SUPABASE_KEY`, `RENDER_HEALTH_URL`
- Build: `pip install -r requirements.txt`
- Start: `gunicorn api:app`

## Development Notes

### Data Import/Export Workflow

1. **Initial Setup:**
   - `import_pokemon_data.py` - Import BankTCG source data to Supabase
   - `import_missing_sets.py` - Add placeholder sets for future scraping

2. **Scraping:**
   - `sync_eligible_products.py` - Mark products for scraping (market_price >= $15)
   - GitHub Actions runs `process_db.py` every 5 days

3. **Export:**
   - `export_to_app_format.py` - Export Supabase data back to BankTCG app format
   - Includes images from original source
   - Adds graded pricing data (grade9, psa10) from scraping

### Deduplication Strategy

The system uses database unique constraints for deduplication:
- `graded_sales` has unique constraint on `(product_id, sale_date, price, ebay_url)`
- `products` has unique constraint on `variant_key`
- Upsert operations automatically skip duplicates
- No application-level duplicate checking needed

### URL Caching

- `products.pricecharting_url` is set after first successful search
- Subsequent scrapes skip search and directly fetch cached URL
- Significantly speeds up re-scrapes (5 day cycle)

### Rate Limiting

- Default delay: 2 seconds between requests
- Configurable via `--delay` parameter in `process_db.py`
- Respectful of PriceCharting servers

### Batch Processing

- `process_db.py` uses pagination with `--batch-size` (default 100)
- Supports offset-based batching for large datasets
- Processes products sequentially to avoid overwhelming database

### Error Handling

- Failed products automatically marked incomplete
- Retried on next run (every 5 days)
- No manual intervention required

### Image Handling

- Images are NOT stored in Supabase
- `export_to_app_format.py` reads images from original BankTCG source data
- Matches cards by variant_key to include correct image URLs
- 100% image coverage for cards that exist in source data

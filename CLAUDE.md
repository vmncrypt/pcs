# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PriceCharting PSA Grade Scraper - An automated system that scrapes PSA graded card sales data from PriceCharting and stores it in Supabase. The system runs via GitHub Actions every 5 days and provides a Flask API for on-demand scraping.

## Commands

### TypeScript/Node.js Commands

```bash
# Run backfill script to calculate graded prices from sales data
npm run backfill
# or
tsx backfill_graded_prices.ts
```

### Python Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Sync eligible products to progress table
python sync_eligible_products.py

# Process incomplete products (scrape graded sales)
python process_db.py --batch-size 100 --delay 2.0

# Run Flask API locally
python api.py

# Test scraping a single product
python main.py "Pikachu VMAX 44" --test
```

### Environment Variables

Required for all scripts:
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase service role key (not anon key)

## Architecture

### Data Flow Pipeline

```
Database Products (filtered)
    ↓
product_grade_progress (tracks completion status)
    ↓
GitHub Actions (every 5 days)
    ├─ Job 1: sync_eligible_products.py (sync products)
    ├─ Job 2: process_db.py (scrape PriceCharting)
    └─ Job 3: backfill_graded_prices.ts (calculate prices)
    ↓
graded_sales table (individual sales)
    ↓
graded_prices table (computed market prices)
```

### Database Schema

**products** - Main product table
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
- `market_price` - Calculated from recent sales (see pricing logic below)
- `sample_size` - Number of sales used in calculation
- Set to `-1` when no sales data available

### Key Components

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

**api.py** - Flask REST API
- Deployed on Render.com (kept warm via GitHub Actions cron)
- `POST /api/scrape/<variant_key>` - Scrape single product by variant_key
- `GET /health` - Health check endpoint
- CORS enabled for frontend access

**backfill_graded_prices.ts** - Price calculator
- Reads `product_grade_progress` table
- Fetches all sales for each product from `graded_sales`
- Calculates market prices using pricing logic (see below)
- Upserts into `graded_prices` table
- Marks progress as incomplete for next scrape cycle

**sync_eligible_products.py** - Product syncing
- Filters products: `market_price >= $15 AND (rarity OR number exists)`
- Syncs to `product_grade_progress` with `completed=false`

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

Located in `backfill_graded_prices.ts:calculateGradedMarketPrice()`

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
- 3 sequential jobs:
  1. `sync` - Syncs eligible products (30 min timeout)
  2. `scrape-batch-1` - Scrapes all products with 2s delay (~4.3 hours)
  3. `backfill-graded-prices` - Calculates market prices (1 hour timeout)

**update_prices.yml** - Price update workflow
- Trigger: Every Monday at 3 AM UTC (before scraping), manual dispatch
- Updates product prices from BankTCG source data
- Re-syncs eligible products based on new prices
- Automatically handles cards that cross the $15 threshold

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

### Deduplication Strategy

The system uses database unique constraints for deduplication:
- `graded_sales` has unique constraint on `(product_id, sale_date, price, ebay_url)`
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

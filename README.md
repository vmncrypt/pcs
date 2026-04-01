# PriceCharting Scraper

Scrapes PSA graded card sales from PriceCharting every 5 days, stores them in Supabase, and exports data for the BankTCG app.

---

## Automated Workflows (GitHub Actions)

| Workflow | Schedule | What it does |
|----------|----------|--------------|
| `scrape_grades.yml` | Every 5 days | Syncs eligible products, scrapes PSA sales → `graded_sales` → `graded_prices` |
| `sync_new_sets.yml` | Every Sunday | Discovers new sets on PriceCharting, backfills their cards |
| `scrape_chinese_sets.yml` | Every Sunday | Same as above for Chinese sets |
| `backfill_images.yml` | Manual | Fills in missing card images from PriceCharting |
| `keep_render_warm.yml` | Every 10 min | Pings Render API to prevent cold starts |

**Manually trigger any workflow:** GitHub → Actions → select workflow → Run workflow.

---

## Full Pipeline: Supabase → App

Run these locally after any scrape cycle completes or after adding new sets:

```bash
# 1. Export from Supabase to local JSON
python export_to_app_format.py

# 2. Build SQLite DB and upload to Firebase (in BankTCG repo)
cd /path/to/BankTCG
bun run build:db:upload
```

Users will automatically download the new database on next app open.

---

## Adding a New Set Manually

Use this when a set is missing or you need to add it before the Sunday automation picks it up.

```bash
# Option A — Let PriceCharting automation handle it (preferred)
# Trigger sync_new_sets.yml manually from GitHub Actions

# Option B — Target a specific set by name
# Trigger sync_new_sets.yml with input: set_name = "Set Name Here"

# Option C — Full manual import via HTML copy/paste
# 1. Add the group
python add_new_set.py "Pokemon New Set Name"

# 2. Copy the <tbody> HTML from PriceCharting in DevTools, save to file
python convert_html_to_json.py new-set.html "Pokemon New Set Name"

# 3. Import cards to Supabase
python import_cards_from_json.py new-set_cards.json

# 4. Then run the pipeline above (export → build:db:upload)
```

---

## Data Flow

```
products (market_price >= $15)
    ↓ sync_eligible_products.py
product_grade_progress (completed=false)
    ↓ process_db.py
graded_sales (PSA 7/8/9/10 individual sales, upserted)
    ↓ compute_graded_prices_batch()
graded_prices (weighted market price per grade)
    ↓ export_to_app_format.py
pokemon-cards-final-data-with-ids.json
    ↓ bun run build:db:upload
pokemon-cards.db → Firebase Storage → App
```

---

## Scripts Reference

| Script | When to run |
|--------|-------------|
| `export_to_app_format.py` | After any scrape or set addition, before build:db:upload |
| `sync_eligible_products.py` | Manually queue products for scraping (normally automated) |
| `process_db.py` | Run scraper locally for testing (`--max-products 5`) |
| `add_new_set.py` | Create an empty group for a new set |
| `backfill_new_sets.py` | Fill cards for empty/incomplete sets |
| `update_product.py` | Re-scrape a single product by variant_key |
| `update_prices_from_source.py` | Sync raw prices from BankTCG JSON → Supabase (local only) |
| `import_cards_from_json.py` | Import cards from a JSON file |
| `convert_html_to_json.py` | Convert PriceCharting HTML table to importable JSON |
| `export_supabase_db.py` | Backup all Supabase tables to local JSON |
| `import_missing_sets.py` | Add groups from pokemon_enriched_series_data.json that are missing in Supabase |
| `parse_bulbapedia_logos.py` | Extract set logos from Bulbapedia HTML |
| `update_missing_logos.py` | Apply extracted logos to pokemon_enriched_series_data.json |

---

## Database Schema (Key Tables)

**`products`** — One row per card variant. `market_price` = raw ungraded price.

**`graded_sales`** — Individual eBay sold listings. Unique on `(product_id, sale_date, price, ebay_url)`.

**`graded_prices`** — Computed market price per `(product_id, grade)` using time-decay weighted average.

**`product_grade_progress`** — Tracks which products have been scraped this cycle (`completed=false` = needs scraping).

**`groups`** — Sets/series. One row per set with optional `set_url` pointing to PriceCharting.

---

## Grade Mapping (PriceCharting CSS classes)

| Grade | CSS class |
|-------|-----------|
| PSA 7 | `completed-auctions-cib` |
| PSA 8 | `completed-auctions-new` |
| PSA 9 | `completed-auctions-graded` |
| PSA 10 | `completed-auctions-manual-only` |

---

## Troubleshooting

**"No matching product found"** — Card name/number doesn't match PriceCharting. Find the URL manually and save it to `products.pricecharting_url`.

**403 errors locally** — PriceCharting blocks home IPs. Scripts that hit PriceCharting must run in GitHub Actions.

**New cards showing $0 PSA prices** — Cards need to be scraped first. Ensure `market_price >= $15` so they're picked up by `sync_eligible_products.py`, then wait for or manually trigger `scrape_grades.yml`.

**Set has wrong card count** — Trigger `sync_new_sets.yml` with `set_name` input to force re-scrape that set.

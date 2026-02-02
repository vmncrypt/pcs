## Quick Start: Export Data for App

```bash
# 1. Download all tables from Supabase
python3 export_supabase_db.py

# 2. Join into app format (includes PSA 7, 8, 9, 10 prices + sales history)
python3 join_local_data.py --output pokemon-cards-final-data-with-ids.json

# 2b. (Optional) Smaller file without sales history (4MB vs 30MB)
python3 join_local_data.py --no-sales --output pokemon-cards-final-data-with-ids.json

# 3. (Optional) Update image resolution
# In the output file, replace /60.jpg with /240.jpg

# 4. Update app db version in stores/gameDataStore.ts
# Increment CURRENT_VERSION by 1
```

### Exported Files from Supabase
- `supabase_groups.json` - All sets/series
- `supabase_products.json` - All cards
- `supabase_graded_prices.json` - Computed PSA prices
- `supabase_graded_sales.json` - Individual sales history (286k+ records)
- `supabase_product_grade_progress.json` - Scraping progress

### Output Format (with sales history)

```json
{
  "card": "Mew #25",
  "price": 43.01,
  "psa7": 31.55,
  "psa8": 33.17,
  "grade9": 44.18,
  "psa10": 141.13,
  "image": "https://...",
  "sales": {
    "7": [{"date": "2025-01-15", "price": 30.00}, ...],
    "8": [{"date": "2025-01-16", "price": 35.00}, ...],
    "9": [{"date": "2025-01-17", "price": 45.00}, ...],
    "10": [{"date": "2025-01-18", "price": 150.00}, ...]
  }
}
```

**Note:** If `graded_prices` doesn't have a computed price, it falls back to the latest sale price.

### Using Sales Data for Charts

```javascript
// Example: Get PSA 10 sales for line chart
const card = data.cards.find(c => c.card === "Mew #25");
const psa10Sales = card.sales?.["10"] || [];

const chartData = {
  labels: psa10Sales.map(s => s.date),
  datasets: [{
    label: 'PSA 10',
    data: psa10Sales.map(s => s.price)
  }]
};

// Combine all grades for multi-line chart
const grades = ["7", "8", "9", "10"];
const datasets = grades.map(grade => ({
  label: `PSA ${grade}`,
  data: (card.sales?.[grade] || []).map(s => ({ x: s.date, y: s.price }))
}));
```

**Tip:** For mobile apps, consider using `--no-sales` for the main data file and loading sales history on-demand per card via API.

---

## Complete Workflow for Adding New Sets

```bash
# 1. Add the set
python3 add_new_set.py "Pokemon New Set Name"

# 2. Copy HTML from PriceCharting in browser (DevTools → <tbody> outerHTML)
nano new-set.html  # Paste and save

# 3. Convert to JSON
python3 convert_html_to_json.py new-set.html "Pokemon New Set Name"

# 4. Import to Supabase (with images!)
python3 import_cards_from_json.py new-set_cards.json

# 5. Sync eligible products
python3 sync_eligible_products.py

# 6. Export to app
python3 export_to_app_format.py

# 7. Update the image resolution
# In final_data_with_ids.json replace /60.jpg with /240.jpg

# 8. Update the app db version
# Increment CURRENT_VERSION in stores/gameDataStore.ts
```

Done! Your app has the new set with all cards and images.

---



# PriceCharting PSA Grade Scraper

Automated system that scrapes PSA graded card sales data from PriceCharting every 5 days and stores it in Supabase.

## Features

- **Automated Scraping**: Runs every 5 days via GitHub Actions (completely free)
- **Smart Deduplication**: Only new sales are added, existing sales are ignored
- **URL Caching**: Saves PriceCharting URLs to skip search on subsequent runs
- **Normalized Data**: Sales stored in `graded_sales` table with proper relational structure
- **PSA Grades**: Scrapes grades 7, 8, 9, and 10
- **Population Reports**: Extracts PSA population counts for all grades (1-10)
- **Fuzzy Matching**: Smart set/edition matching when multiple products exist
- **Progress Tracking**: Marks products as completed, automatic retry on failures

## System Overview

### Data Flow

```
Database Products (6,768)
    ↓
Filter: market_price >= $15 AND (rarity OR number exists)
    ↓
Sync to product_grade_progress (mark incomplete)
    ↓
Scrape PriceCharting (PSA 7/8/9/10 sales + POP)
    ↓
Save to graded_sales table (upsert, no duplicates)
    ↓
Mark as completed
    ↓
Wait 5 days, repeat
```

### Cost Analysis

- **Products**: 6,768
- **Time per run**: ~256 minutes (4.3 hours)
- **Runs per month**: 6 (every 5 days)
- **Monthly usage**: 1,536 minutes
- **Free tier**: 1,750 minutes/month
- **Cost**: $0.00/month ✅

## Setup Instructions

### 1. Prerequisites

- GitHub account
- Supabase account with database set up
- Python 3.9+ (for local testing)

### 2. Database Schema

Ensure your Supabase database has these tables:

**products** (existing table, add these columns if missing):
```sql
ALTER TABLE products ADD COLUMN IF NOT EXISTS pricecharting_url TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS pop_count JSONB DEFAULT '{}'::jsonb;
```

**product_grade_progress** (tracks scraping progress):
```sql
CREATE TABLE IF NOT EXISTS product_grade_progress (
  product_id UUID NOT NULL PRIMARY KEY,
  completed BOOLEAN DEFAULT FALSE,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_progress_completed ON product_grade_progress(completed);
```

**graded_sales** (stores sales data):
```sql
CREATE TABLE public.graded_sales (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL,
  grade INTEGER NOT NULL,
  sale_date DATE NOT NULL,
  price NUMERIC(10, 2) NOT NULL,
  ebay_url TEXT NOT NULL,
  title TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  CONSTRAINT graded_sales_pkey PRIMARY KEY (id),
  CONSTRAINT graded_sales_product_id_sale_date_price_ebay_url_key
    UNIQUE (product_id, sale_date, price, ebay_url),
  CONSTRAINT graded_sales_product_id_fkey
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  CONSTRAINT graded_sales_grade_check
    CHECK (grade >= 1 AND grade <= 10)
);

CREATE INDEX idx_graded_sales_product_id ON graded_sales(product_id);
CREATE INDEX idx_graded_sales_grade ON graded_sales(grade);
CREATE INDEX idx_graded_sales_date ON graded_sales(sale_date);
CREATE INDEX idx_graded_sales_product_grade ON graded_sales(product_id, grade);
```

### 3. Local Testing (Optional)

```bash
# Clone/navigate to repository
cd /path/to/pricecharting

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-anon-key"

# Sync eligible products
python sync_eligible_products.py

# Process a few products (testing)
python process_db.py --max-products 5 --delay 1.0
```

### 4. Deploy to GitHub

#### Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `pricecharting-scraper` (or your choice)
3. Visibility: **Public** (recommended for unlimited free minutes)
4. **Do NOT** initialize with README (we already have files)
5. Click "Create repository"

#### Step 2: Initialize Git and Push

```bash
cd /Users/jonathan/Desktop/pricecharting

# Initialize git (if not already done)
git init
git branch -M main

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: PriceCharting PSA grade scraper"

# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/pricecharting-scraper.git

# Push to GitHub
git push -u origin main
```

#### Step 3: Add GitHub Secrets

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add two secrets:

**Secret 1:**
- Name: `SUPABASE_URL`
- Value: Your Supabase project URL (e.g., `https://your-project.supabase.co`)

**Secret 2:**
- Name: `SUPABASE_KEY`
- Value: Your Supabase anony key (find it in Supabase → Settings → API)

#### Step 4: Enable GitHub Actions

1. Go to **Actions** tab in your repository
2. If prompted, click **"I understand my workflows, go ahead and enable them"**
3. The workflow should start running automatically (triggered by your push to main)

### 5. Monitor the Workflow

#### During Run

1. Go to **Actions** tab
2. Click on the running workflow
3. Click on job name (e.g., "sync" or "scrape-batch-1")
4. View real-time logs

#### Check Progress Locally

```bash
export SUPABASE_URL="your-url"
export SUPABASE_KEY="your-key"
python check_progress.py
```

#### Query Database Directly

```sql
-- Check progress
SELECT
  COUNT(*) FILTER (WHERE completed = true) as completed,
  COUNT(*) FILTER (WHERE completed = false) as remaining,
  COUNT(*) as total
FROM product_grade_progress;

-- Check recent sales
SELECT COUNT(*) as total_sales
FROM graded_sales;

-- Sales by grade
SELECT grade, COUNT(*) as sales_count
FROM graded_sales
GROUP BY grade
ORDER BY grade;
```

## How It Works

### First Run (Initial Scrape)

**For a card like "Pikachu VMAX - Rainbow Rare #044/185":**

1. **Sync Job** (30 min):
   - Identifies card meets criteria (market_price >= $15, has number)
   - Adds to `product_grade_progress` with `completed=false`

2. **Scrape Job** (~4 hours):
   - Parses name: "Pikachu VMAX - Rainbow Rare" → "Pikachu VMAX"
   - Parses number: "044/185" → "44" (removes leading zeros)
   - Cleans set: "Sword & Shield: Vivid Voltage" → "Sword & Shield"
   - Searches: "Pikachu VMAX 44"
   - Gets redirected to product page: `https://www.pricecharting.com/game/pokemon-vivid-voltage/pikachu-vmax-044`
   - **Saves URL** to `products.pricecharting_url`
   - Scrapes PSA 7, 8, 9, 10 sales (e.g., 45 total sales)
   - Scrapes population report
   - **Inserts 45 rows** into `graded_sales` table
   - Updates `pop_count` in products table
   - Marks as `completed=true`

### Second Run (5 Days Later)

1. **Sync Job**:
   - Marks card as `completed=false` (ready to re-scrape)

2. **Scrape Job**:
   - **Uses saved URL** (skips search!)
   - Directly scrapes: `https://www.pricecharting.com/game/pokemon-vivid-voltage/pikachu-vmax-044`
   - Finds 47 sales (2 new sales in past 5 days)
   - Attempts to upsert 47 rows
   - **Only 2 new rows inserted** (45 existing ignored by unique constraint)
   - Updates pop_count
   - Marks as `completed=true`

### Every Subsequent Run

- Same as second run
- Only new sales are added
- Database grows incrementally
- Always have fresh data (max 5 days old)

## Workflow Triggers

The scraper runs automatically on:

1. **Schedule**: Every 5 days at 2 AM UTC
2. **Push to main**: Immediately when you push changes (for testing)
3. **Manual**: Click "Run workflow" in Actions tab

## Files Overview

| File | Purpose |
|------|---------|
| `main.py` | Core scraper: searches PriceCharting, extracts sales & POP |
| `process_db.py` | Database integration: fetches products, saves results |
| `sync_eligible_products.py` | Syncs eligible products to progress table |
| `check_progress.py` | Monitor scraping progress |
| `.github/workflows/scrape_grades.yml` | GitHub Actions workflow |
| `requirements.txt` | Python dependencies |

## Scraping Logic

### Name Parsing
- Input: `"Pikachu VMAX - Rainbow Rare"`
- Output: `"Pikachu VMAX"` (removes everything after " -" or " (")

### Number Parsing
- Input: `"044/185"`
- Output: `"44"` (removes leading zeros and everything after "/")

### Set Name Cleaning
- Input: `"Sword & Shield: Vivid Voltage"`
- Output: `"Sword & Shield"` (removes everything after ":")

### Search Query
- Format: `"{name} {number}"` (no "#" symbol)
- Example: `"Pikachu VMAX 44"`

### Product Matching
1. Check if search redirects to `/game/` URL (direct match)
2. If search results page:
   - Look for `table#games_table` first
   - Fallback to `table.hover_table`
   - Use fuzzy matching on set name (>0.3 similarity threshold)
   - Pick best match

### Grade Mapping
- PSA 7: `completed-auctions-cib`
- PSA 8: `completed-auctions-new`
- PSA 9: `completed-auctions-graded`
- PSA 10: `completed-auctions-manual-only`

## Troubleshooting

### "No eligible products found"
- Check database has products with `market_price >= 15`
- Verify products have `rarity` or `number` fields populated

### "No matching product found"
- Card name/number might not match PriceCharting's format
- Check the product manually on PriceCharting
- Save the URL to `pricecharting_url` column manually

### Workflow not running
- Check **Actions** tab is enabled
- Verify secrets are set correctly (Settings → Secrets)
- Check workflow syntax is valid (Actions tab will show errors)

### Duplicate sales appearing
- Check unique constraint exists on `graded_sales` table
- Constraint: `(product_id, sale_date, price, ebay_url)`

### Rate limited by PriceCharting
- Increase `--delay` to 3-5 seconds in workflow file
- This will process fewer products per run

## Performance Specs

| Metric | Value |
|--------|-------|
| Products scraped | 6,768 |
| Products per hour | ~1,800 |
| Delay between requests | 2 seconds |
| Run frequency | Every 5 days |
| Time per run | ~4.3 hours |
| Monthly minutes | 1,536 |
| Cost | $0.00 |

## Data Freshness

- **Maximum age**: 5 days
- **Typical age**: 2.5 days (average)
- **Re-scraping**: All products re-scraped every 5 days

## Maintenance

### None Required!
- System is fully automated
- New products automatically added when they meet criteria
- Failed products automatically retried next run
- No manual intervention needed

### Optional Adjustments

**Change frequency** (edit `.github/workflows/scrape_grades.yml`):
```yaml
# Every 7 days (more conservative)
- cron: '0 2 */7 * *'

# Every 3 days (more frequent, may exceed free tier)
- cron: '0 2 */3 * *'
```

**Change delay** (slower = more respectful):
```yaml
timeout 19800s python process_db.py --batch-size 100 --delay 3.0 || true
```

**Disable push trigger** (only run on schedule):
Remove these lines from workflow file:
```yaml
push:
  branches:
    - main
```

## Support

For issues or questions:
- Check GitHub Actions logs for error details
- Review Supabase logs for database errors
- Test locally first with `--max-products 5`

## License

MIT License - Use freely for personal or commercial projects
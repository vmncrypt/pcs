# Quick Start Guide

Follow these steps to get your PriceCharting scraper up and running quickly.

## Step 1: Set Up Supabase Database

1. Go to your Supabase project: https://supabase.com/dashboard
2. Click on **SQL Editor** in the left sidebar
3. Click **"New query"**
4. Copy the entire contents of `setup_test_data.sql`
5. Paste it into the SQL editor
6. Click **"Run"** or press `Ctrl+Enter` (Windows) / `Cmd+Enter` (Mac)

This will:
- ✅ Create all necessary tables (groups, products, product_grade_progress, graded_sales, graded_prices)
- ✅ Insert 10 test Pokemon cards
- ✅ Show verification queries to confirm everything worked

## Step 2: Verify Test Data

After running the script, you should see results showing:
- **8 eligible products** (market_price >= $15)
- **2 products below threshold** (won't be scraped)

The test data includes popular cards like:
- Charizard ex (Special Illustration Rare) - $399.99
- Umbreon VMAX (Alternate Art) - $299.99
- Rayquaza VMAX (Alternate Art) - $175.00
- And more!

## Step 3: Get Your Supabase Credentials

1. In Supabase, go to **Settings** → **API**
2. Copy these two values:
   - **Project URL** (e.g., `https://xxxxx.supabase.co`)
   - **Service Role Key** (click "Reveal" - NOT the anon key!)

## Step 4: Test Locally (Optional)

```bash
# Set environment variables
export SUPABASE_URL="your-supabase-url"
export SUPABASE_KEY="your-service-role-key"

# Install dependencies
pip install -r requirements.txt

# Sync eligible products to progress table
python sync_eligible_products.py

# Should show: "✅ Found 8 eligible products total"
```

## Step 5: Test Scraping One Product

```bash
# Scrape one product to test
python process_db.py --batch-size 1 --delay 1.0
```

This will:
1. Fetch 1 product from the database
2. Search PriceCharting for it
3. Scrape PSA 7/8/9/10 sales data
4. Save to `graded_sales` table
5. Save population counts to `products.pop_count`

## Step 6: Check Results in Supabase

Go to **Table Editor** in Supabase and check:

1. **product_grade_progress** - Should have 8 rows, 1 marked as `completed=true`
2. **graded_sales** - Should have sales data for the scraped product
3. **products** - Check the `pop_count` and `pricecharting_url` columns

## Step 7: Run Backfill Script (Calculate Prices)

```bash
# Install Node.js dependencies (if not already)
npm install -g tsx
npm install @supabase/supabase-js dotenv

# Run backfill
npm run backfill
```

This calculates market prices from sales data and stores in `graded_prices` table.

## Step 8: GitHub Actions (Automated Scraping)

Your GitHub Actions should now work! The workflows will:

1. **Sync Job**: Find all eligible products (8 products with test data)
2. **Scrape Job**: Scrape all 8 products (~16 seconds with 2s delay)
3. **Backfill Job**: Calculate prices from sales data

## Step 9: Set Up Render (API)

Follow SETUP.md Part 3 to deploy the Flask API to Render.

Once deployed, you can scrape individual products on-demand:

```bash
curl -X POST https://your-app.onrender.com/api/scrape/sv3pt5-199
```

## Troubleshooting

### No products found
Run this in Supabase SQL Editor:
```sql
SELECT COUNT(*) FROM products
WHERE market_price >= 15 AND (rarity IS NOT NULL OR number IS NOT NULL);
```

If result is 0, re-run the `setup_test_data.sql` script.

### "Product not found on PriceCharting"
Some test products might not be on PriceCharting. This is normal. The scraper will mark them as completed and move on.

### Want to add your own products?
```sql
INSERT INTO products (name, number, variant_key, market_price, rarity)
VALUES ('Card Name', '123', 'set-123', 50.00, 'Rare');
```

Make sure `market_price >= 15` and either `rarity` or `number` is not null.

## Next Steps

- Add real product data from your existing database
- Adjust scraping frequency in `.github/workflows/scrape_grades.yml`
- Set up Render API for on-demand scraping
- Monitor GitHub Actions runs

---

**Total setup time: ~10 minutes**
**Cost: $0.00/month** (free tiers for Supabase, GitHub Actions, Render)

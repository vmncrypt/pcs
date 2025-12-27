# Setup Guide - PriceCharting Scraper

Complete step-by-step guide to set up the PriceCharting PSA grade scraper from scratch.

---

## Prerequisites

Before you begin, make sure you have:

- [ ] A Supabase account (free tier is fine)
- [ ] A GitHub account (free tier is fine)
- [ ] Python 3.9+ installed locally (optional, for testing)
- [ ] Node.js 18+ installed locally (optional, for backfill script)

---

## Part 1: Database Setup (Supabase)

### Step 1: Create a Supabase Project

1. Go to https://supabase.com/dashboard
2. Click "New project"
3. Choose your organization
4. Fill in:
   - **Name**: `pricecharting-scraper` (or any name)
   - **Database Password**: Generate a strong password (save this!)
   - **Region**: Choose closest to you
5. Click "Create new project"
6. Wait 2-3 minutes for project to be ready

### Step 2: Create Database Tables (IN THIS ORDER!)

**IMPORTANT:** You must create the tables in this exact order because of foreign key dependencies.

Go to your Supabase project → **SQL Editor** → Click "New query"

#### Table 1: Create `products` table (or modify existing)

If you already have a `products` table, just add the missing columns:

```sql
-- Add columns to existing products table
ALTER TABLE products ADD COLUMN IF NOT EXISTS pricecharting_url TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS pop_count JSONB DEFAULT '{}'::jsonb;
```

If you DON'T have a products table yet, create it:

```sql
-- Create products table from scratch
CREATE TABLE products (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  number TEXT,
  variant_key TEXT UNIQUE,
  group_id UUID,
  market_price NUMERIC(10, 2),
  rarity TEXT,
  pricecharting_url TEXT,
  pop_count JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  CONSTRAINT products_pkey PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS idx_products_variant_key ON products(variant_key);
CREATE INDEX IF NOT EXISTS idx_products_group_id ON products(group_id);
```

**Note:** You may also need a `groups` table. Create it if it doesn't exist:

```sql
-- Create groups table (if needed)
CREATE TABLE IF NOT EXISTS groups (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  CONSTRAINT groups_pkey PRIMARY KEY (id)
);
```

Click **"Run"** or press `Ctrl+Enter` (Windows) / `Cmd+Enter` (Mac)

---

#### Table 2: Create `product_grade_progress` table

```sql
-- Create product_grade_progress table
CREATE TABLE IF NOT EXISTS product_grade_progress (
  product_id UUID NOT NULL PRIMARY KEY,
  completed BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  CONSTRAINT product_grade_progress_product_id_fkey
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_progress_completed ON product_grade_progress(completed);
```

Click **"Run"**

---

#### Table 3: Create `graded_sales` table

```sql
-- Create graded_sales table
CREATE TABLE IF NOT EXISTS graded_sales (
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

CREATE INDEX IF NOT EXISTS idx_graded_sales_product_id ON graded_sales(product_id);
CREATE INDEX IF NOT EXISTS idx_graded_sales_grade ON graded_sales(grade);
CREATE INDEX IF NOT EXISTS idx_graded_sales_date ON graded_sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_graded_sales_product_grade ON graded_sales(product_id, grade);
```

Click **"Run"**

---

#### Table 4: Create `graded_prices` table

```sql
-- Create graded_prices table
CREATE TABLE IF NOT EXISTS graded_prices (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL,
  grade INTEGER NOT NULL,
  market_price NUMERIC(10, 2) NOT NULL,
  sample_size INTEGER DEFAULT 0,
  last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  CONSTRAINT graded_prices_pkey PRIMARY KEY (id),
  CONSTRAINT graded_prices_product_id_grade_key
    UNIQUE (product_id, grade),
  CONSTRAINT graded_prices_product_id_fkey
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
  CONSTRAINT graded_prices_grade_check
    CHECK (grade >= 1 AND grade <= 10)
);

CREATE INDEX IF NOT EXISTS idx_graded_prices_product_id ON graded_prices(product_id);
CREATE INDEX IF NOT EXISTS idx_graded_prices_grade ON graded_prices(grade);
CREATE INDEX IF NOT EXISTS idx_graded_prices_product_grade ON graded_prices(product_id, grade);
```

Click **"Run"**

---

### Step 3: Get Your Supabase Credentials

1. In your Supabase project, go to **Settings** (gear icon in sidebar)
2. Click **API** in the left menu
3. You'll need two values:

   **Copy these values - you'll need them later:**
   - **Project URL**: (looks like `https://xxxxx.supabase.co`)
   - **Service Role Key** (secret): Click "Reveal" next to `service_role` (NOT anon key!)

---

## Part 2: GitHub Setup

### Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Fill in:
   - **Repository name**: `pricecharting-scraper` (or any name)
   - **Visibility**: **Public** (recommended for unlimited free Actions minutes)
   - **Do NOT** check "Add a README file" (we already have one)
3. Click **"Create repository"**

### Step 2: Push Code to GitHub

Open terminal in your project directory and run:

```bash
# Navigate to your project directory
cd /Users/leon/Actual/Apps/Prod/PriceChartingCron

# Initialize git (if not already done)
git init
git branch -M main

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: PriceCharting scraper"

# Add your GitHub repository as remote (REPLACE with your username/repo)
git remote add origin https://github.com/YOUR_USERNAME/pricecharting-scraper.git

# Push to GitHub
git push -u origin main
```

### Step 3: Add GitHub Secrets

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **"New repository secret"**
4. Add three secrets:

**Secret 1:**
- Name: `SUPABASE_URL`
- Value: Your Supabase Project URL from Part 1, Step 3

**Secret 2:**
- Name: `SUPABASE_KEY`
- Value: Your Supabase Service Role Key from Part 1, Step 3

**Secret 3:**
- Name: `RENDER_HEALTH_URL`
- Value: Leave this blank for now (we'll add it after Render setup)

### Step 4: Enable GitHub Actions

1. Go to the **Actions** tab in your repository
2. If prompted, click **"I understand my workflows, go ahead and enable them"**
3. You should see two workflows:
   - "Scrape PriceCharting Grade Data"
   - "Keep Render Warm"

**Don't run them yet!** We need to set up Render first.

---

## Part 3: Render Setup (Flask API)

### Step 1: Create Render Account

1. Go to https://render.com
2. Sign up (you can use GitHub login)
3. Choose the free tier

### Step 2: Deploy the API

**Option A: Using Blueprint (Recommended)**

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"Blueprint"**
3. Connect your GitHub account if not already connected
4. Select your `pricecharting-scraper` repository
5. Render will detect `render.yaml`
6. Click **"Apply"**
7. Set environment variables:
   - `SUPABASE_URL`: Your Supabase Project URL
   - `SUPABASE_KEY`: Your Supabase Service Role Key
8. Click **"Apply"** again to deploy

**Option B: Manual Setup**

1. Go to https://dashboard.render.com
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure:
   - **Name**: `pricecharting-scraper-api`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn api:app`
   - **Instance Type**: `Free`
5. Add environment variables:
   - `SUPABASE_URL`: Your Supabase Project URL
   - `SUPABASE_KEY`: Your Supabase Service Role Key
   - `PYTHON_VERSION`: `3.9.16`
6. Click **"Create Web Service"**

### Step 3: Get Render Health URL

1. Wait for deployment to complete (3-5 minutes)
2. Once deployed, you'll see your service URL (e.g., `https://pricecharting-scraper-api.onrender.com`)
3. Your health URL is: `https://YOUR-SERVICE-NAME.onrender.com/health`
4. Test it by opening that URL in your browser - you should see: `{"status":"healthy"}`

### Step 4: Add Render Health URL to GitHub

1. Copy your full health URL (e.g., `https://pricecharting-scraper-api.onrender.com/health`)
2. Go to GitHub → Your repository → **Settings** → **Secrets and variables** → **Actions**
3. Find `RENDER_HEALTH_URL` and click **Edit**
4. Paste your health URL
5. Click **Update secret**

---

## Part 4: Testing the Setup

### Test 1: Test the Render API

```bash
# Test health endpoint (replace with your URL)
curl https://YOUR-SERVICE-NAME.onrender.com/health

# Expected response:
# {"status":"healthy"}
```

### Test 2: Test Scraping a Product (Local)

**IMPORTANT:** You need to have at least ONE product in your `products` table first!

If you don't have products yet, add a test product:

```sql
-- Add a test product (run in Supabase SQL Editor)
INSERT INTO products (name, number, variant_key, market_price, rarity, group_id)
VALUES ('Charizard ex', '199', 'sv3pt5-199', 50.00, 'Special Illustration Rare', NULL);
```

Now test locally:

```bash
# Set environment variables
export SUPABASE_URL="your-supabase-url"
export SUPABASE_KEY="your-service-role-key"

# Install dependencies
pip install -r requirements.txt

# Sync one product to progress table
python sync_eligible_products.py

# Scrape one product
python process_db.py --batch-size 1 --delay 1.0
```

### Test 3: Run GitHub Actions Manually

1. Go to GitHub → Your repository → **Actions** tab
2. Click on "Scrape PriceCharting Grade Data" workflow
3. Click **"Run workflow"** → **"Run workflow"**
4. Wait and watch the logs

The workflow will:
1. ✅ Sync eligible products (30 sec - 5 min)
2. ✅ Scrape graded sales data (depends on number of products)
3. ✅ Calculate graded prices (1-5 min)

---

## Part 5: Verify Everything Works

### Check Database Data

Go to Supabase → **Table Editor** and verify:

1. **product_grade_progress** table has rows with `completed = false`
2. **graded_sales** table has sales data after scraping
3. **graded_prices** table has calculated prices after backfill

### Check Logs

- **GitHub Actions**: Go to Actions tab → Click on a workflow run → View logs
- **Render**: Go to Render dashboard → Your service → Logs tab

---

## Troubleshooting

### Error: "column product_id does not exist"

**Solution:** You created the tables in the wrong order. The `products` table must exist BEFORE creating `graded_sales` or `product_grade_progress`.

**Fix:**
1. Drop the tables in reverse order:
```sql
DROP TABLE IF EXISTS graded_prices CASCADE;
DROP TABLE IF EXISTS graded_sales CASCADE;
DROP TABLE IF EXISTS product_grade_progress CASCADE;
```
2. Re-create them following Part 1, Step 2 in the exact order

### Error: "No eligible products found"

**Solution:** You need products in the database first.

**Check:**
```sql
SELECT COUNT(*) FROM products
WHERE market_price >= 15 AND (rarity IS NOT NULL OR number IS NOT NULL);
```

If count is 0, you need to import your products data first.

### GitHub Actions not running

**Check:**
1. Actions tab is enabled (Settings → Actions → General → Allow all actions)
2. Secrets are set correctly (Settings → Secrets and variables → Actions)
3. Check workflow file syntax (Actions tab will show errors)

### Render API cold starts / timing out

**Solution:** The "Keep Render Warm" workflow pings your service every 10 minutes to prevent cold starts.

**Verify:** Check that `RENDER_HEALTH_URL` secret is set correctly in GitHub.

---

## Next Steps

### Optional: Import Your Product Data

If you have existing product data (CSV, JSON, etc.), import it into the `products` table using Supabase Table Editor or SQL.

Required columns:
- `name` - Card name
- `number` - Card number (e.g., "044/185")
- `variant_key` - Unique identifier
- `market_price` - Current market price
- `rarity` - Card rarity (optional but helpful for filtering)
- `group_id` - Foreign key to groups table (optional)

### Optional: Adjust Scraping Frequency

Edit `.github/workflows/scrape_grades.yml`:

```yaml
schedule:
  # Change from every 5 days to every 7 days
  - cron: '0 2 */7 * *'
```

### Optional: Test API from Frontend

```javascript
// Test the API endpoint
const response = await fetch(
  'https://YOUR-SERVICE-NAME.onrender.com/api/scrape/sv3pt5-199',
  { method: 'POST' }
);
const data = await response.json();
console.log(data);
```

---

## Summary

You should now have:

✅ Supabase database with 4 tables (products, product_grade_progress, graded_sales, graded_prices)
✅ GitHub repository with automated scraping workflow (runs every 5 days)
✅ Render API for on-demand scraping
✅ GitHub Actions keeping Render warm (every 10 minutes)

**Total cost: $0.00/month** (using free tiers)

The scraper will now automatically run every 5 days, keeping your graded sales data fresh!

-- ============================================================
-- PriceCharting Scraper - Complete Database Setup
-- ============================================================
-- Run this script in Supabase SQL Editor to set up everything
-- ============================================================

-- Step 1: Create groups table (if it doesn't exist)
-- ============================================================
CREATE TABLE IF NOT EXISTS groups (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  CONSTRAINT groups_pkey PRIMARY KEY (id)
);

-- Step 2: Create products table (if it doesn't exist)
-- ============================================================
CREATE TABLE IF NOT EXISTS products (
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
  CONSTRAINT products_pkey PRIMARY KEY (id),
  CONSTRAINT products_group_id_fkey
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_products_variant_key ON products(variant_key);
CREATE INDEX IF NOT EXISTS idx_products_group_id ON products(group_id);
CREATE INDEX IF NOT EXISTS idx_products_market_price ON products(market_price);

-- Step 3: Create product_grade_progress table
-- ============================================================
CREATE TABLE IF NOT EXISTS product_grade_progress (
  product_id UUID NOT NULL PRIMARY KEY,
  completed BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  CONSTRAINT product_grade_progress_product_id_fkey
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_progress_completed ON product_grade_progress(completed);

-- Step 4: Create graded_sales table
-- ============================================================
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

-- Step 5: Create graded_prices table
-- ============================================================
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

-- ============================================================
-- Step 6: Insert Test Data
-- ============================================================

-- Insert test groups
INSERT INTO groups (name) VALUES
  ('Scarlet & Violet: 151'),
  ('Scarlet & Violet: Obsidian Flames'),
  ('Sword & Shield: Evolving Skies')
ON CONFLICT DO NOTHING;

-- Get group IDs for reference
DO $$
DECLARE
  group_151_id UUID;
  group_obsidian_id UUID;
  group_evolving_id UUID;
BEGIN
  -- Get or create group IDs
  SELECT id INTO group_151_id FROM groups WHERE name = 'Scarlet & Violet: 151' LIMIT 1;
  SELECT id INTO group_obsidian_id FROM groups WHERE name = 'Scarlet & Violet: Obsidian Flames' LIMIT 1;
  SELECT id INTO group_evolving_id FROM groups WHERE name = 'Sword & Shield: Evolving Skies' LIMIT 1;

  -- Insert test products (high-value cards that are likely on PriceCharting)
  INSERT INTO products (name, number, variant_key, group_id, market_price, rarity) VALUES
    -- 151 set
    ('Charizard ex', '199', 'sv3pt5-199', group_151_id, 399.99, 'Special Illustration Rare'),
    ('Mew ex', '151', 'sv3pt5-151', group_151_id, 89.99, 'Double Rare'),
    ('Erika''s Invitation', '196', 'sv3pt5-196', group_151_id, 65.00, 'Special Illustration Rare'),

    -- Obsidian Flames set
    ('Charizard ex', '125', 'sv3-125', group_obsidian_id, 125.00, 'Double Rare'),
    ('Mew ex', '151', 'sv3-151', group_obsidian_id, 45.00, 'Ultra Rare'),

    -- Evolving Skies set
    ('Umbreon VMAX', '215', 'swsh7-215', group_evolving_id, 299.99, 'Alternate Art'),
    ('Rayquaza VMAX', '218', 'swsh7-218', group_evolving_id, 175.00, 'Alternate Art'),
    ('Glaceon VMAX', '209', 'swsh7-209', group_evolving_id, 85.00, 'Alternate Art'),

    -- Products below $15 threshold (should NOT be scraped)
    ('Pikachu', '025', 'sv3pt5-025', group_151_id, 5.00, 'Common'),
    ('Charmander', '004', 'sv3pt5-004', group_151_id, 3.50, 'Common')
  ON CONFLICT (variant_key) DO NOTHING;
END $$;

-- ============================================================
-- Verification Queries
-- ============================================================

-- Check how many products are eligible for scraping
SELECT
  COUNT(*) as eligible_products,
  COUNT(*) FILTER (WHERE market_price >= 15) as above_price_threshold,
  COUNT(*) FILTER (WHERE rarity IS NOT NULL OR number IS NOT NULL) as has_rarity_or_number
FROM products;

-- Show eligible products
SELECT
  variant_key,
  name,
  number,
  market_price,
  rarity
FROM products
WHERE market_price >= 15
  AND (rarity IS NOT NULL OR number IS NOT NULL)
ORDER BY market_price DESC;

-- Show products that won't be scraped (below threshold)
SELECT
  variant_key,
  name,
  number,
  market_price,
  rarity
FROM products
WHERE market_price < 15
ORDER BY market_price DESC;

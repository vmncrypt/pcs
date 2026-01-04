# Integration Guide - Using Graded Sales Data in Your App

This guide shows how to fetch and use the graded sales data in your application.

---

## Option 1: Direct Supabase Client (Recommended)

**Best for:** React, Next.js, Vue, TypeScript/JavaScript apps

### Setup

```bash
npm install @supabase/supabase-js
```

### Basic Usage

```typescript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  'https://tkqsbsvzcjmnrecgospn.supabase.co',
  'YOUR_ANON_KEY' // Use anon key (public), NOT service role key!
)

// Fetch graded sales for a specific product
async function getGradedSales(variantKey: string) {
  const { data: product, error: productError } = await supabase
    .from('products')
    .select('id, name, number')
    .eq('variant_key', variantKey)
    .single()

  if (productError) throw productError

  const { data: sales, error: salesError } = await supabase
    .from('graded_sales')
    .select('*')
    .eq('product_id', product.id)
    .order('sale_date', { ascending: false })

  if (salesError) throw salesError

  return { product, sales }
}

// Usage
const { product, sales } = await getGradedSales('sv3pt5-199')
console.log(`${product.name} has ${sales.length} graded sales`)
```

### Get Latest Market Prices

```typescript
async function getGradedPrices(variantKey: string) {
  const { data: product } = await supabase
    .from('products')
    .select('id')
    .eq('variant_key', variantKey)
    .single()

  const { data: prices, error } = await supabase
    .from('graded_prices')
    .select('grade, market_price, sample_size, last_updated')
    .eq('product_id', product.id)
    .order('grade', { ascending: true })

  return prices
}

// Usage
const prices = await getGradedPrices('sv3pt5-199')
// [
//   { grade: 7, market_price: 125.50, sample_size: 12, ... },
//   { grade: 8, market_price: 175.00, sample_size: 8, ... },
//   { grade: 9, market_price: 250.00, sample_size: 15, ... },
//   { grade: 10, market_price: 450.00, sample_size: 5, ... }
// ]
```

### Real-Time Updates (Optional)

```typescript
// Subscribe to new sales as they're scraped
const subscription = supabase
  .channel('graded_sales_changes')
  .on(
    'postgres_changes',
    {
      event: 'INSERT',
      schema: 'public',
      table: 'graded_sales',
      filter: `product_id=eq.${productId}`
    },
    (payload) => {
      console.log('New sale:', payload.new)
    }
  )
  .subscribe()
```

---

## Option 2: REST API Endpoints

**Best for:** Any language/framework, microservices architecture

### Create API Routes in Your App

**Next.js API Route Example:**

```typescript
// app/api/graded-sales/[variantKey]/route.ts
import { createClient } from '@supabase/supabase-js'
import { NextResponse } from 'next/server'

const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_KEY! // Server-side only!
)

export async function GET(
  request: Request,
  { params }: { params: { variantKey: string } }
) {
  try {
    // Get product
    const { data: product } = await supabase
      .from('products')
      .select('id, name, number, market_price')
      .eq('variant_key', params.variantKey)
      .single()

    if (!product) {
      return NextResponse.json({ error: 'Product not found' }, { status: 404 })
    }

    // Get graded sales
    const { data: sales } = await supabase
      .from('graded_sales')
      .select('*')
      .eq('product_id', product.id)
      .order('sale_date', { ascending: false })

    // Get graded prices
    const { data: prices } = await supabase
      .from('graded_prices')
      .select('*')
      .eq('product_id', product.id)

    return NextResponse.json({
      product,
      sales,
      prices
    })
  } catch (error) {
    return NextResponse.json({ error: 'Internal error' }, { status: 500 })
  }
}
```

**Usage in Frontend:**

```typescript
const response = await fetch('/api/graded-sales/sv3pt5-199')
const { product, sales, prices } = await response.json()
```

---

## Option 3: GraphQL with Supabase

**Best for:** Complex queries, nested data fetching

Supabase supports PostgREST which can be queried like GraphQL:

```typescript
const { data } = await supabase
  .from('products')
  .select(`
    id,
    name,
    number,
    market_price,
    graded_sales (
      grade,
      sale_date,
      price,
      ebay_url
    ),
    graded_prices (
      grade,
      market_price,
      sample_size
    )
  `)
  .eq('variant_key', 'sv3pt5-199')
  .single()

// Returns nested structure with sales and prices
```

---

## Option 4: Periodic Data Sync (For Mobile/Offline Apps)

**Best for:** Mobile apps, offline-first apps

### Strategy

1. Fetch all data periodically (e.g., daily)
2. Store in local database (SQLite, IndexedDB)
3. Sync changes incrementally

```typescript
async function syncGradedData() {
  // Get last sync timestamp
  const lastSync = localStorage.getItem('lastGradedDataSync')

  // Fetch only updated data
  const { data: updatedSales } = await supabase
    .from('graded_sales')
    .select('*')
    .gte('updated_at', lastSync || '1970-01-01')

  const { data: updatedPrices } = await supabase
    .from('graded_prices')
    .select('*')
    .gte('last_updated', lastSync || '1970-01-01')

  // Store in local database
  await localDB.insertOrReplace('graded_sales', updatedSales)
  await localDB.insertOrReplace('graded_prices', updatedPrices)

  // Update sync timestamp
  localStorage.setItem('lastGradedDataSync', new Date().toISOString())
}

// Run on app startup
await syncGradedData()
```

---

## Common Query Patterns

### 1. Get All Sales for a Product

```typescript
const { data } = await supabase
  .from('graded_sales')
  .select('*')
  .eq('product_id', productId)
  .order('sale_date', { ascending: false })
```

### 2. Get Sales by Grade

```typescript
const { data } = await supabase
  .from('graded_sales')
  .select('*')
  .eq('product_id', productId)
  .eq('grade', 10) // PSA 10 only
  .order('sale_date', { ascending: false })
```

### 3. Get Recent Sales (Last 30 Days)

```typescript
const thirtyDaysAgo = new Date()
thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30)

const { data } = await supabase
  .from('graded_sales')
  .select('*')
  .eq('product_id', productId)
  .gte('sale_date', thirtyDaysAgo.toISOString().split('T')[0])
```

### 4. Get Price History by Grade

```typescript
const { data } = await supabase
  .from('graded_sales')
  .select('sale_date, price')
  .eq('product_id', productId)
  .eq('grade', 10)
  .order('sale_date', { ascending: true })

// Use for charting price trends
```

### 5. Get Statistics

```typescript
// Average, min, max prices by grade
const { data } = await supabase
  .from('graded_sales')
  .select('grade, price')
  .eq('product_id', productId)

// Calculate in JavaScript
const stats = data.reduce((acc, sale) => {
  if (!acc[sale.grade]) {
    acc[sale.grade] = { prices: [], count: 0 }
  }
  acc[sale.grade].prices.push(sale.price)
  acc[sale.grade].count++
  return acc
}, {})

Object.keys(stats).forEach(grade => {
  const prices = stats[grade].prices
  stats[grade].avg = prices.reduce((a, b) => a + b) / prices.length
  stats[grade].min = Math.min(...prices)
  stats[grade].max = Math.max(...prices)
})
```

### 6. Search Products by Name

```typescript
const { data } = await supabase
  .from('products')
  .select('variant_key, name, number, market_price')
  .ilike('name', '%Charizard%')
  .gte('market_price', 15)
  .order('market_price', { ascending: false })
```

### 7. Get Population Counts

```typescript
const { data: product } = await supabase
  .from('products')
  .select('pop_count')
  .eq('variant_key', 'sv3pt5-199')
  .single()

// pop_count is JSONB: { "1": 100, "2": 250, "3": 500, ... "10": 50 }
const psa10Count = product.pop_count['10']
```

---

## Row Level Security (RLS) Setup

**Important:** Enable RLS for production to control data access.

```sql
-- Enable RLS on tables
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE graded_sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE graded_prices ENABLE ROW LEVEL SECURITY;

-- Allow public read access (use anon key in frontend)
CREATE POLICY "Public read access" ON products
  FOR SELECT USING (true);

CREATE POLICY "Public read access" ON graded_sales
  FOR SELECT USING (true);

CREATE POLICY "Public read access" ON graded_prices
  FOR SELECT USING (true);
```

---

## Performance Tips

### 1. Use Indexes

Already created in setup, but verify:

```sql
-- Check indexes
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename IN ('products', 'graded_sales', 'graded_prices');
```

### 2. Limit Results

```typescript
// Limit to 100 most recent sales
const { data } = await supabase
  .from('graded_sales')
  .select('*')
  .eq('product_id', productId)
  .order('sale_date', { ascending: false })
  .limit(100)
```

### 3. Use Select Specific Columns

```typescript
// Only fetch what you need
const { data } = await supabase
  .from('graded_sales')
  .select('grade, price, sale_date') // Not *
  .eq('product_id', productId)
```

### 4. Cache in Frontend

```typescript
// React Query example
import { useQuery } from '@tanstack/react-query'

function useGradedSales(variantKey: string) {
  return useQuery({
    queryKey: ['graded-sales', variantKey],
    queryFn: () => getGradedSales(variantKey),
    staleTime: 1000 * 60 * 60, // 1 hour cache
  })
}
```

---

## Example: Complete Product Card Component

```typescript
import { useEffect, useState } from 'react'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)

interface ProductWithGrades {
  variant_key: string
  name: string
  number: string
  market_price: number
  prices: Array<{
    grade: number
    market_price: number
    sample_size: number
  }>
}

export function ProductCard({ variantKey }: { variantKey: string }) {
  const [product, setProduct] = useState<ProductWithGrades | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      const { data } = await supabase
        .from('products')
        .select(`
          variant_key,
          name,
          number,
          market_price,
          graded_prices (
            grade,
            market_price,
            sample_size
          )
        `)
        .eq('variant_key', variantKey)
        .single()

      setProduct(data)
      setLoading(false)
    }

    fetchData()
  }, [variantKey])

  if (loading) return <div>Loading...</div>
  if (!product) return <div>Product not found</div>

  return (
    <div className="product-card">
      <h2>{product.name} #{product.number}</h2>
      <p>Raw Price: ${product.market_price.toFixed(2)}</p>

      <h3>Graded Prices</h3>
      <div className="grades">
        {product.prices.map((price) => (
          <div key={price.grade} className="grade">
            <span>PSA {price.grade}</span>
            <span>${price.market_price.toFixed(2)}</span>
            <span className="sample">({price.sample_size} sales)</span>
          </div>
        ))}
      </div>
    </div>
  )
}
```

---

## Security Best Practices

1. **Use Anon Key in Frontend**
   - Never expose service role key in client code
   - Anon key + RLS policies for security

2. **Use Service Role Key in Backend Only**
   - API routes, serverless functions
   - Full database access

3. **Enable RLS Policies**
   - Control who can read/write data
   - See RLS Setup section above

4. **Environment Variables**
   ```bash
   # Frontend (.env.local)
   NEXT_PUBLIC_SUPABASE_URL=https://tkqsbsvzcjmnrecgospn.supabase.co
   NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key

   # Backend (.env)
   SUPABASE_URL=https://tkqsbsvzcjmnrecgospn.supabase.co
   SUPABASE_SERVICE_KEY=your-service-role-key
   ```

---

## Next Steps

1. **Get your anon key** from Supabase dashboard (Settings → API)
2. **Install Supabase client** in your app
3. **Try the example queries** above
4. **Enable RLS** for production
5. **Build your UI** with the graded data

For more advanced usage, see [Supabase Documentation](https://supabase.com/docs)

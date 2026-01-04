# Periodic Data Sync Strategy - Complete Implementation Guide

This guide provides a complete implementation for syncing graded sales data to your app using a periodic sync strategy.

---

## Overview

**Strategy:** Download data periodically from Supabase and store locally for offline access.

**Benefits:**
- ✅ Works offline after initial sync
- ✅ Fast local queries (no network latency)
- ✅ Reduced Supabase API usage
- ✅ Better user experience (instant data)
- ✅ Control over sync frequency

---

## Architecture

```
Supabase (Source of Truth)
    ↓ (Periodic Sync)
Local Database (SQLite/IndexedDB/WatermelonDB)
    ↓ (Query)
Your App UI
```

---

## Implementation Options

### Option A: Full Sync (Simple, Best for Small Datasets)

Download everything each time.

**Pros:** Simple, always consistent
**Cons:** More bandwidth, slower for large datasets

### Option B: Incremental Sync (Recommended)

Only download changes since last sync.

**Pros:** Fast, efficient, less bandwidth
**Cons:** Slightly more complex

---

## Complete Implementation

### 1. Setup Local Database

#### React Native (SQLite)

```bash
npm install expo-sqlite
```

```typescript
// db/schema.ts
import * as SQLite from 'expo-sqlite'

const db = SQLite.openDatabase('graded_sales.db')

export function initializeDatabase() {
  db.transaction(tx => {
    // Products table
    tx.executeSql(`
      CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        variant_key TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        number TEXT,
        market_price REAL,
        rarity TEXT,
        pop_count TEXT, -- JSON string
        synced_at TEXT
      )
    `)

    // Graded sales table
    tx.executeSql(`
      CREATE TABLE IF NOT EXISTS graded_sales (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL,
        grade INTEGER NOT NULL,
        sale_date TEXT NOT NULL,
        price REAL NOT NULL,
        ebay_url TEXT,
        title TEXT,
        synced_at TEXT,
        FOREIGN KEY (product_id) REFERENCES products(id)
      )
    `)

    // Graded prices table
    tx.executeSql(`
      CREATE TABLE IF NOT EXISTS graded_prices (
        id TEXT PRIMARY KEY,
        product_id TEXT NOT NULL,
        grade INTEGER NOT NULL,
        market_price REAL NOT NULL,
        sample_size INTEGER,
        last_updated TEXT,
        synced_at TEXT,
        UNIQUE(product_id, grade),
        FOREIGN KEY (product_id) REFERENCES products(id)
      )
    `)

    // Sync metadata table
    tx.executeSql(`
      CREATE TABLE IF NOT EXISTS sync_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `)

    // Indexes for performance
    tx.executeSql('CREATE INDEX IF NOT EXISTS idx_products_variant_key ON products(variant_key)')
    tx.executeSql('CREATE INDEX IF NOT EXISTS idx_sales_product_id ON graded_sales(product_id)')
    tx.executeSql('CREATE INDEX IF NOT EXISTS idx_sales_grade ON graded_sales(grade)')
    tx.executeSql('CREATE INDEX IF NOT EXISTS idx_prices_product_id ON graded_prices(product_id)')
  })
}
```

#### Web App (IndexedDB)

```typescript
// db/indexeddb.ts
import { openDB, DBSchema, IDBPDatabase } from 'idb'

interface GradedSalesDB extends DBSchema {
  products: {
    key: string
    value: {
      id: string
      variant_key: string
      name: string
      number: string | null
      market_price: number
      rarity: string | null
      pop_count: Record<string, number>
      synced_at: string
    }
    indexes: { 'by-variant-key': string }
  }
  graded_sales: {
    key: string
    value: {
      id: string
      product_id: string
      grade: number
      sale_date: string
      price: number
      ebay_url: string
      title: string | null
      synced_at: string
    }
    indexes: { 'by-product-id': string; 'by-grade': number }
  }
  graded_prices: {
    key: string
    value: {
      id: string
      product_id: string
      grade: number
      market_price: number
      sample_size: number
      last_updated: string
      synced_at: string
    }
    indexes: { 'by-product-id': string }
  }
  sync_metadata: {
    key: string
    value: {
      key: string
      value: string
      updated_at: string
    }
  }
}

let dbInstance: IDBPDatabase<GradedSalesDB> | null = null

export async function getDB() {
  if (dbInstance) return dbInstance

  dbInstance = await openDB<GradedSalesDB>('graded-sales-db', 1, {
    upgrade(db) {
      // Products store
      const productsStore = db.createObjectStore('products', { keyPath: 'id' })
      productsStore.createIndex('by-variant-key', 'variant_key', { unique: true })

      // Graded sales store
      const salesStore = db.createObjectStore('graded_sales', { keyPath: 'id' })
      salesStore.createIndex('by-product-id', 'product_id')
      salesStore.createIndex('by-grade', 'grade')

      // Graded prices store
      const pricesStore = db.createObjectStore('graded_prices', { keyPath: 'id' })
      pricesStore.createIndex('by-product-id', 'product_id')

      // Sync metadata store
      db.createObjectStore('sync_metadata', { keyPath: 'key' })
    }
  })

  return dbInstance
}
```

---

### 2. Implement Sync Manager

```typescript
// services/syncManager.ts
import { createClient } from '@supabase/supabase-js'
import { getDB } from '../db/indexeddb' // or your SQLite helper

const supabase = createClient(
  process.env.EXPO_PUBLIC_SUPABASE_URL!,
  process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY!
)

export class SyncManager {
  private syncInProgress = false

  /**
   * Get last sync timestamp
   */
  private async getLastSyncTime(table: string): Promise<string | null> {
    const db = await getDB()
    const metadata = await db.get('sync_metadata', `last_sync_${table}`)
    return metadata?.value || null
  }

  /**
   * Update last sync timestamp
   */
  private async setLastSyncTime(table: string, timestamp: string) {
    const db = await getDB()
    await db.put('sync_metadata', {
      key: `last_sync_${table}`,
      value: timestamp,
      updated_at: new Date().toISOString()
    })
  }

  /**
   * Sync products (incremental)
   */
  async syncProducts(): Promise<{ added: number; updated: number }> {
    const lastSync = await this.getLastSyncTime('products')
    const now = new Date().toISOString()

    console.log(`📦 Syncing products (last sync: ${lastSync || 'never'})`)

    // Fetch products updated since last sync
    let query = supabase
      .from('products')
      .select('id, variant_key, name, number, market_price, rarity, pop_count')

    if (lastSync) {
      query = query.gte('updated_at', lastSync)
    }

    const { data: products, error } = await query

    if (error) throw error

    console.log(`📥 Received ${products?.length || 0} products`)

    // Store in local DB
    const db = await getDB()
    const tx = db.transaction('products', 'readwrite')

    let added = 0
    let updated = 0

    for (const product of products || []) {
      const existing = await tx.store.get(product.id)

      await tx.store.put({
        ...product,
        pop_count: product.pop_count || {},
        synced_at: now
      })

      if (existing) {
        updated++
      } else {
        added++
      }
    }

    await tx.done

    // Update last sync time
    await this.setLastSyncTime('products', now)

    console.log(`✅ Products synced: ${added} added, ${updated} updated`)

    return { added, updated }
  }

  /**
   * Sync graded sales (incremental)
   */
  async syncGradedSales(): Promise<{ added: number }> {
    const lastSync = await this.getLastSyncTime('graded_sales')
    const now = new Date().toISOString()

    console.log(`📊 Syncing graded sales (last sync: ${lastSync || 'never'})`)

    // Fetch sales updated since last sync
    let query = supabase
      .from('graded_sales')
      .select('*')

    if (lastSync) {
      query = query.gte('created_at', lastSync)
    }

    const { data: sales, error } = await query

    if (error) throw error

    console.log(`📥 Received ${sales?.length || 0} sales`)

    // Store in local DB
    const db = await getDB()
    const tx = db.transaction('graded_sales', 'readwrite')

    for (const sale of sales || []) {
      await tx.store.put({
        ...sale,
        synced_at: now
      })
    }

    await tx.done

    // Update last sync time
    await this.setLastSyncTime('graded_sales', now)

    console.log(`✅ Graded sales synced: ${sales?.length || 0} added`)

    return { added: sales?.length || 0 }
  }

  /**
   * Sync graded prices (incremental)
   */
  async syncGradedPrices(): Promise<{ added: number; updated: number }> {
    const lastSync = await this.getLastSyncTime('graded_prices')
    const now = new Date().toISOString()

    console.log(`💰 Syncing graded prices (last sync: ${lastSync || 'never'})`)

    // Fetch prices updated since last sync
    let query = supabase
      .from('graded_prices')
      .select('*')

    if (lastSync) {
      query = query.gte('last_updated', lastSync)
    }

    const { data: prices, error } = await query

    if (error) throw error

    console.log(`📥 Received ${prices?.length || 0} prices`)

    // Store in local DB
    const db = await getDB()
    const tx = db.transaction('graded_prices', 'readwrite')

    let added = 0
    let updated = 0

    for (const price of prices || []) {
      const existing = await tx.store.get(price.id)

      await tx.store.put({
        ...price,
        synced_at: now
      })

      if (existing) {
        updated++
      } else {
        added++
      }
    }

    await tx.done

    // Update last sync time
    await this.setLastSyncTime('graded_prices', now)

    console.log(`✅ Graded prices synced: ${added} added, ${updated} updated`)

    return { added, updated }
  }

  /**
   * Full sync - all tables
   */
  async fullSync(): Promise<{
    products: { added: number; updated: number }
    sales: { added: number }
    prices: { added: number; updated: number }
  }> {
    if (this.syncInProgress) {
      throw new Error('Sync already in progress')
    }

    this.syncInProgress = true

    try {
      console.log('🔄 Starting full sync...')

      const products = await this.syncProducts()
      const sales = await this.syncGradedSales()
      const prices = await this.syncGradedPrices()

      console.log('✅ Full sync complete!')

      return { products, sales, prices }
    } finally {
      this.syncInProgress = false
    }
  }

  /**
   * Get sync status
   */
  async getSyncStatus() {
    const productsSync = await this.getLastSyncTime('products')
    const salesSync = await this.getLastSyncTime('graded_sales')
    const pricesSync = await this.getLastSyncTime('graded_prices')

    return {
      products: productsSync,
      sales: salesSync,
      prices: pricesSync,
      isInProgress: this.syncInProgress
    }
  }
}

// Singleton instance
export const syncManager = new SyncManager()
```

---

### 3. Local Query Functions

```typescript
// services/localQueries.ts
import { getDB } from '../db/indexeddb'

/**
 * Get product with graded prices
 */
export async function getProductWithPrices(variantKey: string) {
  const db = await getDB()

  // Get product
  const product = await db.getFromIndex('products', 'by-variant-key', variantKey)

  if (!product) return null

  // Get graded prices
  const prices = await db.getAllFromIndex('graded_prices', 'by-product-id', product.id)

  return {
    ...product,
    prices: prices.sort((a, b) => a.grade - b.grade)
  }
}

/**
 * Get all sales for a product
 */
export async function getGradedSales(variantKey: string, grade?: number) {
  const db = await getDB()

  // Get product
  const product = await db.getFromIndex('products', 'by-variant-key', variantKey)

  if (!product) return []

  // Get all sales
  let sales = await db.getAllFromIndex('graded_sales', 'by-product-id', product.id)

  // Filter by grade if specified
  if (grade !== undefined) {
    sales = sales.filter(sale => sale.grade === grade)
  }

  // Sort by date descending
  return sales.sort((a, b) =>
    new Date(b.sale_date).getTime() - new Date(a.sale_date).getTime()
  )
}

/**
 * Search products by name
 */
export async function searchProducts(query: string, minPrice?: number) {
  const db = await getDB()

  const allProducts = await db.getAll('products')

  const lowerQuery = query.toLowerCase()

  return allProducts
    .filter(p => {
      const matchesName = p.name.toLowerCase().includes(lowerQuery)
      const matchesPrice = minPrice ? p.market_price >= minPrice : true
      return matchesName && matchesPrice
    })
    .sort((a, b) => b.market_price - a.market_price)
}

/**
 * Get price statistics for a product
 */
export async function getPriceStats(variantKey: string, grade: number) {
  const sales = await getGradedSales(variantKey, grade)

  if (sales.length === 0) {
    return null
  }

  const prices = sales.map(s => s.price)

  return {
    count: sales.length,
    avg: prices.reduce((a, b) => a + b) / prices.length,
    min: Math.min(...prices),
    max: Math.max(...prices),
    recent: sales.slice(0, 5) // Last 5 sales
  }
}
```

---

### 4. React Hooks for Sync

```typescript
// hooks/useSync.ts
import { useState, useEffect, useCallback } from 'react'
import { syncManager } from '../services/syncManager'

export function useSync() {
  const [syncing, setSyncing] = useState(false)
  const [lastSync, setLastSync] = useState<string | null>(null)
  const [error, setError] = useState<Error | null>(null)

  const sync = useCallback(async () => {
    setSyncing(true)
    setError(null)

    try {
      await syncManager.fullSync()
      const status = await syncManager.getSyncStatus()
      setLastSync(status.products || null)
    } catch (err) {
      setError(err as Error)
      console.error('Sync failed:', err)
    } finally {
      setSyncing(false)
    }
  }, [])

  // Auto-sync on mount
  useEffect(() => {
    sync()
  }, [sync])

  return { syncing, lastSync, error, sync }
}

// hooks/useProduct.ts
import { useState, useEffect } from 'react'
import { getProductWithPrices } from '../services/localQueries'

export function useProduct(variantKey: string) {
  const [product, setProduct] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const data = await getProductWithPrices(variantKey)
      setProduct(data)
      setLoading(false)
    }

    load()
  }, [variantKey])

  return { product, loading }
}
```

---

### 5. App Integration

```typescript
// App.tsx
import { useEffect } from 'react'
import { syncManager } from './services/syncManager'
import { initializeDatabase } from './db/schema' // or getDB()

export default function App() {
  useEffect(() => {
    async function initialize() {
      // Initialize local database
      await initializeDatabase() // or getDB()

      // Initial sync
      console.log('🚀 Starting initial sync...')
      await syncManager.fullSync()

      // Schedule periodic sync (every 6 hours)
      setInterval(() => {
        console.log('⏰ Scheduled sync triggered')
        syncManager.fullSync()
      }, 6 * 60 * 60 * 1000) // 6 hours
    }

    initialize()
  }, [])

  return <YourAppContent />
}

// Example: Product Screen
function ProductScreen({ variantKey }: { variantKey: string }) {
  const { product, loading } = useProduct(variantKey)
  const { syncing } = useSync()

  if (loading) return <LoadingSpinner />
  if (!product) return <NotFound />

  return (
    <div>
      {syncing && <SyncBanner>Syncing latest data...</SyncBanner>}

      <h1>{product.name} #{product.number}</h1>
      <p>Raw Price: ${product.market_price.toFixed(2)}</p>

      <h2>Graded Prices</h2>
      {product.prices.map(price => (
        <div key={price.grade}>
          <span>PSA {price.grade}</span>
          <span>${price.market_price.toFixed(2)}</span>
          <span>({price.sample_size} sales)</span>
        </div>
      ))}
    </div>
  )
}
```

---

## Sync Strategies

### Strategy 1: On App Launch (Recommended)
```typescript
// Sync when app opens
useEffect(() => {
  syncManager.fullSync()
}, [])
```

### Strategy 2: Background Sync (iOS/Android)
```typescript
import * as BackgroundFetch from 'expo-background-fetch'
import * as TaskManager from 'expo-task-manager'

const BACKGROUND_SYNC_TASK = 'background-sync'

TaskManager.defineTask(BACKGROUND_SYNC_TASK, async () => {
  try {
    await syncManager.fullSync()
    return BackgroundFetch.BackgroundFetchResult.NewData
  } catch (error) {
    return BackgroundFetch.BackgroundFetchResult.Failed
  }
})

// Register background task
BackgroundFetch.registerTaskAsync(BACKGROUND_SYNC_TASK, {
  minimumInterval: 60 * 60 * 6, // 6 hours
  stopOnTerminate: false,
  startOnBoot: true
})
```

### Strategy 3: Pull to Refresh
```typescript
function ProductList() {
  const [refreshing, setRefreshing] = useState(false)

  const onRefresh = async () => {
    setRefreshing(true)
    await syncManager.fullSync()
    setRefreshing(false)
  }

  return (
    <ScrollView
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      {/* Your content */}
    </ScrollView>
  )
}
```

---

## Performance Optimization

### 1. Sync Only Recent Data (Initial Load)

```typescript
async syncRecentData() {
  // Only sync products worth >= $15
  const { data } = await supabase
    .from('products')
    .select('*')
    .gte('market_price', 15)

  // Store locally
  // ...
}
```

### 2. Batch Inserts

```typescript
// Insert in batches of 100
const BATCH_SIZE = 100

for (let i = 0; i < items.length; i += BATCH_SIZE) {
  const batch = items.slice(i, i + BATCH_SIZE)
  await db.transaction(tx => {
    batch.forEach(item => tx.store.put(item))
  })
}
```

### 3. Show Progress

```typescript
function SyncProgress() {
  const [progress, setProgress] = useState(0)

  async function syncWithProgress() {
    setProgress(0)
    await syncManager.syncProducts()
    setProgress(33)
    await syncManager.syncGradedSales()
    setProgress(66)
    await syncManager.syncGradedPrices()
    setProgress(100)
  }

  return <ProgressBar value={progress} />
}
```

---

## Testing

```typescript
// Test sync
import { syncManager } from './services/syncManager'
import { getProductWithPrices } from './services/localQueries'

async function testSync() {
  console.log('Starting sync test...')

  // Sync data
  const result = await syncManager.fullSync()
  console.log('Sync result:', result)

  // Query local data
  const product = await getProductWithPrices('sv3pt5-199')
  console.log('Product:', product)

  console.log('✅ Sync test complete!')
}
```

---

## Next Steps

1. **Initialize database** in your app
2. **Implement SyncManager** with your database (SQLite/IndexedDB)
3. **Call sync on app launch**
4. **Test with a few products** first
5. **Add pull-to-refresh** for manual sync
6. **Enable background sync** (optional)

Your app will now have **fast, offline-first access** to all graded sales data!

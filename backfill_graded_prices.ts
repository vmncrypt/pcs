#!/usr/bin/env tsx
/**
 * Backfill graded_prices table
 *
 * This script:
 * 1. Reads all rows from product_grade_progress table
 * 2. For each product_id, fetches graded_sales data
 * 3. Calculates market prices for PSA 7, 8, 9, and 10
 * 4. Inserts/updates the graded_prices table
 * 5. Sets completed = false in product_grade_progress after processing
 *
 * Note: Price is set to -1 if no sales data is available for a grade
 */

import { createClient } from '@supabase/supabase-js'
import * as dotenv from 'dotenv'

// Load environment variables
dotenv.config({ path: '.env' })

const SUPABASE_URL = process.env.SUPABASE_URL
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_KEY

if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
    console.error('❌ Missing SUPABASE_URL or SUPABASE_KEY in .env')
    process.exit(1)
}

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY)

interface GradedSale {
    id: string
    product_id: string
    grade: number
    sale_date: string
    price: number
    ebay_url: string | null
    title: string | null
    created_at: string
    updated_at: string
}

interface ProductGradeProgress {
    product_id: string
    completed: boolean
    created_at?: string
    updated_at?: string
}

interface GradedPrice {
    product_id: string
    grade: number
    market_price: number
    sample_size: number
    last_updated: string
}

const GRADES_TO_CALCULATE = [7, 8, 9, 10]
const BATCH_SIZE = 100

/**
 * Calculate the market price for a specific PSA grade based on recent sales
 * Returns -1 if no sales data is available
 */
function calculateGradedMarketPrice(sales: GradedSale[], grade: number): { price: number; sampleSize: number } {
    // Filter sales for this specific grade
    const gradeSales = sales.filter(sale => sale.grade === grade)

    if (gradeSales.length === 0) {
        return { price: -1, sampleSize: 0 }
    }

    // Sort by date descending (most recent first)
    const sortedSales = [...gradeSales].sort((a, b) =>
        new Date(b.sale_date).getTime() - new Date(a.sale_date).getTime()
    )

    const now = new Date()
    const twoWeeksAgo = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000)

    // Get sales from the last 2 weeks
    const recentSales = sortedSales.filter(sale =>
        new Date(sale.sale_date) >= twoWeeksAgo
    )

    // If there are sales in the last 2 weeks, use those
    if (recentSales.length > 0) {
        const sum = recentSales.reduce((acc, sale) => acc + sale.price, 0)
        return {
            price: sum / recentSales.length,
            sampleSize: recentSales.length
        }
    }

    // Otherwise, use the last 1-3 sales
    const lastFewSales = sortedSales.slice(0, 3)
    const sum = lastFewSales.reduce((acc, sale) => acc + sale.price, 0)
    return {
        price: sum / lastFewSales.length,
        sampleSize: lastFewSales.length
    }
}

/**
 * Process a single product: calculate and store graded prices
 */
async function processProduct(productId: string): Promise<boolean> {
    try {
        // Fetch all graded sales for this product
        const { data: sales, error: salesError } = await supabase
            .from('graded_sales')
            .select('*')
            .eq('product_id', productId)

        if (salesError) {
            console.error(`  ❌ Error fetching sales for product ${productId}:`, salesError.message)
            return false
        }

        const gradedSales = (sales || []) as GradedSale[]

        // Calculate prices for PSA 7, 8, 9, 10
        const gradedPrices: GradedPrice[] = []

        for (const grade of GRADES_TO_CALCULATE) {
            const { price, sampleSize } = calculateGradedMarketPrice(gradedSales, grade)

            gradedPrices.push({
                product_id: productId,
                grade,
                market_price: price,
                sample_size: sampleSize,
                last_updated: new Date().toISOString()
            })
        }

        // Upsert into graded_prices table
        const { error: upsertError } = await supabase
            .from('graded_prices')
            .upsert(gradedPrices, {
                onConflict: 'product_id,grade'
            })

        if (upsertError) {
            console.error(`  ❌ Error upserting graded prices for product ${productId}:`, upsertError.message)
            return false
        }

        // Mark as completed (set to false as requested)
        const { error: updateError } = await supabase
            .from('product_grade_progress')
            .update({ completed: false })
            .eq('product_id', productId)

        if (updateError) {
            console.error(`  ⚠️  Error updating product_grade_progress for product ${productId}:`, updateError.message)
            // Don't return false here - the main work (price calculation) succeeded
        }

        const pricesWithData = gradedPrices.filter(p => p.market_price !== -1)
        console.log(`  ✅ Product ${productId}: Calculated ${pricesWithData.length}/${GRADES_TO_CALCULATE.length} prices`)

        return true
    } catch (error) {
        console.error(`  ❌ Unexpected error processing product ${productId}:`, error)
        return false
    }
}

/**
 * Main execution function
 */
async function main() {
    console.log('🚀 Starting graded prices backfill...\n')

    // Fetch all products from product_grade_progress
    // Note: Supabase has a default 1000 row limit, so we need to paginate
    let allRecords: any[] = []
    let page = 0
    const PAGE_SIZE = 1000
    let hasMore = true

    console.log('📥 Fetching all products from product_grade_progress...')

    while (hasMore) {
        const from = page * PAGE_SIZE
        const to = from + PAGE_SIZE - 1

        const { data, error: fetchError } = await supabase
            .from('product_grade_progress')
            .select('product_id, completed')
            .order('product_id', { ascending: true })
            .range(from, to)

        if (fetchError) {
            console.error('❌ Error fetching product_grade_progress:', fetchError.message)
            process.exit(1)
        }

        if (!data || data.length === 0) {
            hasMore = false
        } else {
            allRecords = allRecords.concat(data)
            console.log(`  Fetched ${allRecords.length} products so far...`)

            if (data.length < PAGE_SIZE) {
                hasMore = false
            }
            page++
        }
    }

    const progressRecords = allRecords

    if (!progressRecords || progressRecords.length === 0) {
        console.log('⚠️  No records found in product_grade_progress table')
        process.exit(0)
    }

    const totalProducts = progressRecords.length
    console.log(`📊 Found ${totalProducts} products to process\n`)

    let processed = 0
    let succeeded = 0
    let failed = 0

    // Process in batches
    for (let i = 0; i < progressRecords.length; i += BATCH_SIZE) {
        const batch = progressRecords.slice(i, i + BATCH_SIZE)
        const batchNumber = Math.floor(i / BATCH_SIZE) + 1
        const totalBatches = Math.ceil(totalProducts / BATCH_SIZE)

        console.log(`\n📦 Processing batch ${batchNumber}/${totalBatches} (${batch.length} products)`)

        // Process products in batch sequentially (to avoid overwhelming the DB)
        for (const record of batch) {
            const productId = (record as ProductGradeProgress).product_id
            const success = await processProduct(productId)

            processed++
            if (success) {
                succeeded++
            } else {
                failed++
            }

            // Progress indicator
            if (processed % 10 === 0) {
                const progress = ((processed / totalProducts) * 100).toFixed(1)
                console.log(`  📈 Progress: ${processed}/${totalProducts} (${progress}%)`)
            }
        }
    }

    console.log('\n' + '='.repeat(60))
    console.log('✅ Backfill complete!')
    console.log('='.repeat(60))
    console.log(`Total products: ${totalProducts}`)
    console.log(`Succeeded: ${succeeded}`)
    console.log(`Failed: ${failed}`)
    console.log('='.repeat(60))
}

// Run the script
main().catch(error => {
    console.error('💥 Fatal error:', error)
    process.exit(1)
})

# PriceCharting Scraper API

Flask API for scraping individual products by variant_key. Designed to be deployed on Render.com.

## Features

- ✅ REST API endpoint for scraping single products
- ✅ CORS enabled for frontend access
- ✅ Automatic database updates (graded_sales + pop_count)
- ✅ Health check endpoint for monitoring
- ✅ Production-ready with Gunicorn

## Deployment on Render.com

### Option 1: Using render.yaml (Recommended)

1. Push this repo to GitHub
2. Go to [Render Dashboard](https://dashboard.render.com/)
3. Click "New +" → "Blueprint"
4. Connect your GitHub repository
5. Render will automatically detect `render.yaml`
6. Set environment variables:
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_KEY`: Your Supabase service key
7. Click "Apply" to deploy

### Option 2: Manual Setup

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name**: `pricecharting-scraper-api`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn api:app`
5. Add environment variables:
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_KEY`: Your Supabase service key
6. Click "Create Web Service"

### Environment Variables

Make sure to set these in Render's dashboard:

- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_KEY` - Your Supabase service role key (not anon key)

## API Endpoints

### Health Check
```
GET /health
```

Response:
```json
{
  "status": "healthy"
}
```

### Scrape Product (URL Parameter)
```
GET/POST /api/scrape/<variant_key>
```

Example:
```bash
curl https://your-app.onrender.com/api/scrape/sv3pt5-173
```

### Scrape Product (Request Body)
```
POST /api/scrape
Content-Type: application/json

{
  "variant_key": "sv3pt5-173"
}
```

Example:
```bash
curl -X POST https://your-app.onrender.com/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"variant_key": "sv3pt5-173"}'
```

### Success Response
```json
{
  "success": true,
  "variant_key": "sv3pt5-173",
  "product_id": "12345",
  "product_name": "Charizard ex",
  "stats": {
    "total_sales": 45,
    "pop_grades": 10,
    "sales_saved": 45
  },
  "pricecharting_url": "https://www.pricecharting.com/game/..."
}
```

### Error Response
```json
{
  "success": false,
  "error": "Product not found with variant_key: sv3pt5-173"
}
```

## Usage from TypeScript

### Using Fetch API
```typescript
async function scrapeProduct(variantKey: string) {
  const response = await fetch(
    `https://your-app.onrender.com/api/scrape/${variantKey}`,
    {
      method: 'POST'
    }
  );

  const data = await response.json();

  if (!data.success) {
    throw new Error(data.error);
  }

  return data;
}

// Usage
try {
  const result = await scrapeProduct('sv3pt5-173');
  console.log(`Scraped ${result.stats.total_sales} sales`);
} catch (error) {
  console.error('Scrape failed:', error);
}
```

### Using Axios
```typescript
import axios from 'axios';

async function scrapeProduct(variantKey: string) {
  const { data } = await axios.post(
    `https://your-app.onrender.com/api/scrape/${variantKey}`
  );

  if (!data.success) {
    throw new Error(data.error);
  }

  return data;
}
```

### Alternative: POST with Body
```typescript
async function scrapeProduct(variantKey: string) {
  const response = await fetch('https://your-app.onrender.com/api/scrape', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ variant_key: variantKey })
  });

  return await response.json();
}
```

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export SUPABASE_URL="your-url"
export SUPABASE_KEY="your-key"
```

3. Run the server:
```bash
python api.py
```

The API will be available at `http://localhost:5000`

## Testing

Test the API locally:
```bash
# Health check
curl http://localhost:5000/health

# Scrape a product
curl http://localhost:5000/api/scrape/sv3pt5-173

# With POST body
curl -X POST http://localhost:5000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"variant_key": "sv3pt5-173"}'
```

## Notes

- The API scrapes PriceCharting for PSA 7, 8, 9, and 10 sales data
- Data is automatically saved to your Supabase database
- The endpoint works regardless of the product's `is_eligible` status
- First request may be slow due to cold starts on Render's free tier
- Subsequent requests are faster once the server is warm

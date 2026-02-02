#!/bin/bash

# Quick setup script for GitHub Actions deployment

echo "🚀 Setting up PriceCharting scraper for GitHub Actions"
echo "======================================================="
echo ""

# Check if git is initialized
if [ ! -d .git ]; then
    echo "📁 Initializing git repository..."
    git init
    git branch -M main
else
    echo "✅ Git repository already initialized"
fi

# Check if requirements.txt exists
if [ ! -f requirements.txt ]; then
    echo "❌ requirements.txt not found!"
    exit 1
fi

echo ""
echo "📦 Next steps:"
echo ""
echo "1. Create a GitHub repository:"
echo "   - Go to https://github.com/new"
echo "   - Name it: pricecharting-scraper (or your choice)"
echo "   - Make it private to keep your data secure"
echo ""
echo "2. Add your files and push:"
echo "   git add ."
echo "   git commit -m 'Initial commit: PriceCharting grade scraper'"
echo "   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git"
echo "   git push -u origin main"
echo ""
echo "3. Add secrets to GitHub:"
echo "   - Go to: Settings → Secrets and variables → Actions"
echo "   - Click 'New repository secret'"
echo "   - Add SUPABASE_URL: https://your-project.supabase.co"
echo "   - Add SUPABASE_KEY: (your key)"
echo ""
echo "4. Your workflow will run:"
echo "   - Automatically every 3 days at 2 AM UTC"
echo "   - Or manually from the Actions tab"
echo ""
echo "5. Monitor progress:"
echo "   - GitHub: Actions tab → View workflow runs"
echo "   - Locally: python check_progress.py"
echo ""
echo "📊 How it works:"
echo "   - Job 1: Syncs eligible products (market_price >= \$15)"
echo "   - Jobs 2-4: Process ~9,900 products each (5.5 hours/job)"
echo "   - Total: ~29,700 products per run (~18 hours)"
echo "   - Runs every 3 days to keep data fresh"
echo ""
echo "💰 Cost: \$0 (GitHub Actions free tier)"
echo ""
echo "✨ Done! Follow the steps above to deploy."
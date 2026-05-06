#!/bin/bash
# ============================================================
# StockAI Railway Deployment Script
# Run this locally after cloning the repo
# ============================================================

set -e

echo "🚀 StockAI Railway Deployment Script"
echo "========================================"

# Step 1: Install Railway CLI (if not installed)
if ! command -v railway &> /dev/null; then
    echo "📦 Installing Railway CLI..."
    curl -fsSL https://railway.app/install.sh | sh
fi

# Step 2: Login to Railway
echo "🔑 Please login to Railway..."
railway login --browserless
# OR: railway login (opens browser)

# Step 3: Create new project
echo "📁 Creating Railway project 'stockai-system'..."
railway project create stockai-system

# Step 4: Add PostgreSQL plugin
echo "🗄️  Adding PostgreSQL..."
railway add postgres

# Step 5: Link project to current directory
echo "🔗 Linking project..."
railway link

# Step 6: Set environment variables
echo "⚙️  Setting environment variables..."

# Read JWT keys
JWT_PRIVATE_KEY=$(cat deployment/jwt-private-key.pem)
JWT_PUBLIC_KEY=$(cat deployment/jwt-public-key.pem)

railway variables set \
  DEEPSEEK_API_KEY="sk-dfc6b1209c354d56b017f1cf50ef6877" \
  SILICONFLOW_API_KEY="sk-eqctxvzlxynzzlsjnczqmypfjclqxoanyzkzxdrunesdarqt" \
  JWT_SECRET_KEY="$JWT_PRIVATE_KEY" \
  JWT_PUBLIC_KEY="$JWT_PUBLIC_KEY" \
  SECRET_KEY="630c7477e38fcf16ae1e87b1f19179fa11c0f40cf6b261de1692711eb826e37f" \
  FLASK_ENV="production" \
  FLASK_DEBUG="0" \
  ADMIN_SEED_PASSWORD="FTiVUue5aiGqseH6"

# Step 7: Link to GitHub repo
echo "🔗 Connect Railway to GitHub repo..."
echo "   Go to Railway Dashboard > Project > Settings > GitHub"
echo "   Connect: marchyma-commits/stockai-system"
echo "   Branch: master"
echo "   Root Directory: (leave empty)"

# Step 8: Deploy
echo "🔄 Triggering deployment..."
railway up --detach

# Step 9: Wait for deployment
echo "⏳ Waiting for deployment..."
sleep 30

# Step 10: Run migration (if using DB)
echo "🗄️  Running database migrations..."
railway run alembic upgrade head

# Step 11: Seed admin
echo "👤 Seeding admin user..."
railway run python backend/seed_admin.py

# Step 12: Delete seed password
echo "🔐 Deleting ADMIN_SEED_PASSWORD..."
railway variables delete ADMIN_SEED_PASSWORD

# Step 13: Get URL
echo "🌐 Getting production URL..."
railway domain

echo ""
echo "✅ Deployment complete!"
echo "========================================"

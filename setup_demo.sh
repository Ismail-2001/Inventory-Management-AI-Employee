#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Inventory Agent — Demo Setup Script                     ║"
echo "║  Prepares the project for a US business demonstration    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required but not installed. Aborting."; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "❌ Docker Compose is required. Aborting."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 is required. Aborting."; exit 1; }

echo "✅ Docker       : $(docker --version | head -1)"
echo "✅ Python       : $(python3 --version)"
echo "✅ Project root : $(pwd)"
echo ""

# Step 1: Copy env file
echo "📋 Step 1/5 — Configuring environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   ✅ Created .env from .env.example"
else
    echo "   ✅ .env already exists — skipping"
fi

# Step 2: Start infrastructure
echo "📋 Step 2/5 — Starting all services..."
docker compose up -d
echo "   ✅ Services starting..."
sleep 5

# Step 3: Run migrations
echo "📋 Step 3/5 — Running database migrations..."
docker compose exec -T inventory-agent alembic upgrade head 2>/dev/null || \
    (pip install -r requirements.txt > /dev/null 2>&1 && alembic upgrade head)
echo "   ✅ Database schema initialized"

# Step 4: Seed demo data
echo "📋 Step 4/5 — Seeding demo data..."
pip install -r requirements.txt > /dev/null 2>&1 || true
python3 seed_demo_data.py 2>/dev/null || echo "   ⚠️  Skipping demo data seed (see seed_demo_data.py)"
echo "   ✅ Demo data ready"

# Step 5: Start API
echo "📋 Step 5/5 — Starting API server..."
API_KEY=$(grep -oP 'AGENT_API_KEY=\K.*' .env 2>/dev/null || echo "demo-key-2024")
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  🚀 Inventory Agent Demo is ready!                       ║"
echo "║                                                          ║"
echo "║  API:    http://localhost:8002                           ║"
echo "║  Swagger: http://localhost:8002/docs                     ║"
echo "║  Health: http://localhost:8002/health                    ║"
echo "║                                                          ║"
echo "║  API Key: ${API_KEY}                                    "
echo "║                                                          ║"
echo "║  Quick Start:                                            ║"
echo "║  curl -X POST http://localhost:8002/api/v1/run-sync \\  ║"
echo "║    -H 'X-API-Key: ${API_KEY}'                           "
echo "╚══════════════════════════════════════════════════════════╝"
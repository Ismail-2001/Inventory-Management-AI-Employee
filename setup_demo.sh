#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Inventory Agent — Demo Setup Script                     ║"
echo "║  Prepares the project for a US business demonstration    ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required. Aborting."; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "❌ Docker Compose is required. Aborting."; exit 1; }

echo "✅ Docker       : $(docker --version | head -1)"
echo "✅ Project root : $(pwd)"
echo ""

# Step 1: Copy env file
echo "📋 Step 1/5 — Configuring environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   ✅ Created .env from .env.example"
    echo "   ⚠️  Edit .env to set your LLM API key (GROQ_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY)"
else
    echo "   ✅ .env already exists"
fi

# Step 2: Start services
echo "📋 Step 2/5 — Starting services..."
docker compose up -d --build
echo "   ✅ Waiting for PostgreSQL health check..."
docker compose exec inventory-agent sh -c 'for i in 1 2 3 4 5; do curl -sf http://localhost:8002/health >/dev/null && break; sleep 2; done'
echo "   ✅ Services ready"

# Step 3: Run migrations
echo "📋 Step 3/5 — Running database migrations..."
docker compose exec -T inventory-agent alembic upgrade head
echo "   ✅ Database schema initialized"

# Step 4: Seed demo data
echo "📋 Step 4/5 — Seeding demo data..."
docker compose exec -T inventory-agent python seed_demo_data.py || echo "   ⚠️  Seed skipped (DB may already have data)"
echo "   ✅ Demo data ready"

# Step 5: Print summary
echo "📋 Step 5/5 — Done"
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
echo "║  Frontend (dev):                                          ║"
echo "║  cd inventory-frontend && npm ci && npm run dev          ║"
echo "║  → http://localhost:5173                                 ║"
echo "║                                                          ║"
echo "║  Quick Start:                                            ║"
echo "║  curl -X POST http://localhost:8002/api/v1/run-sync \\  ║"
echo "║    -H 'X-API-Key: ${API_KEY}'                           ║"
echo "╚══════════════════════════════════════════════════════════╝"
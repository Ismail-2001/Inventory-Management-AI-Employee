# Inventory Agent 🤖📦

**AI Employee #2** — AI-powered inventory management, demand forecasting, and reorder optimization for ecommerce businesses.

## What It Does

- **Stock Analysis**: Analyze inventory levels and get actionable recommendations
- **Demand Forecasting**: Predict sales for next 30/60/90 days
- **Reorder Optimization**: Calculate optimal reorder quantities
- **Bulk Analysis**: Analyze entire inventory catalog at once
- **Stockout Prediction**: Know exactly when you'll run out of stock

## Quick Start

### 1. Setup

```bash
git clone https://github.com/Ismail-2001/inventory-agent.git
cd inventory-agent
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY
```

### 2. Run with Docker

```bash
docker compose up -d
```

### 3. Run Locally

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8002
```

### 4. Test It

```bash
# Health check
curl http://localhost:8002/health

# Analyze an item
curl -X POST http://localhost:8002/api/v1/analyze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-key-2024" \
  -d '{
    "product_id": "SKU-001",
    "name": "Wireless Headphones",
    "current_stock": 150,
    "daily_sales": 8.5,
    "lead_time_days": 7,
    "unit_cost": 25.00,
    "unit_price": 79.99,
    "category": "electronics"
  }'
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Agent info |
| GET | `/health` | Health check |
| POST | `/api/v1/analyze` | Analyze single item |
| POST | `/api/v1/bulk` | Analyze multiple items |
| POST | `/api/v1/forecast` | Get demand forecast |

## Example Response

```json
{
  "product_id": "SKU-001",
  "product_name": "Wireless Headphones",
  "current_stock": 150,
  "recommended_stock": 500,
  "recommended_action": "maintain",
  "reorder_quantity": 0,
  "urgency": "low",
  "days_of_stock_remaining": 17.6,
  "stockout_risk_days": 25,
  "demand_forecast_30d": 255,
  "demand_forecast_60d": 510,
  "demand_forecast_90d": 765,
  "cost_impact": 1250.0,
  "reasoning": "Current inventory is optimal. 17.6 days remaining.",
  "seasonal_alert": null,
  "supplier_recommendation": "Consider negotiating bulk discount"
}
```

## Pricing

| Plan | Setup | Monthly | Includes |
|------|-------|---------|----------|
| Starter | $1,500 | $500 | 1 agent, basic integration |
| Growth | $3,000 | $1,000 | 2 agents, full integration |
| Enterprise | Custom | Custom | Multi-agent, SLA |

## Requirements

- Python 3.12+
- Google Gemini API key (or OpenAI key)
- Docker (optional)

## License

Proprietary — All rights reserved.
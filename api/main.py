"""
Inventory Agent - API Server
Run: uvicorn api.main:app --reload --port 8002
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import os

from agent.inventory_agent import agent, InventoryItem, InventoryAnalysis, BulkAnalysisRequest, BulkAnalysisResponse


app = FastAPI(
    title="Inventory Agent",
    description="AI-powered inventory management, demand forecasting, and reorder optimization",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("AGENT_API_KEY", "demo-key-2024")

async def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


@app.get("/")
async def root():
    return {
        "agent": "Inventory Agent",
        "version": "1.0.0",
        "status": "active",
        "capabilities": [
            "Single Item Analysis",
            "Bulk Inventory Analysis",
            "Demand Forecasting",
            "Reorder Optimization",
            "Stockout Prediction"
        ],
        "endpoints": {
            "analyze": "POST /api/v1/analyze",
            "bulk": "POST /api/v1/bulk",
            "forecast": "POST /api/v1/forecast",
            "health": "GET /health"
        },
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent": "inventory",
        "version": "1.0.0",
        "provider": "gemini" if os.getenv("GOOGLE_API_KEY") else "mock"
    }


@app.post("/api/v1/analyze", response_model=InventoryAnalysis)
async def analyze_inventory(
    item: InventoryItem,
    x_api_key: str = Depends(verify_api_key)
):
    """
    Analyze a single inventory item and get recommendations.

    Example:
    {
        "product_id": "SKU-001",
        "name": "Wireless Headphones",
        "current_stock": 150,
        "daily_sales": 8.5,
        "lead_time_days": 7,
        "unit_cost": 25.00,
        "unit_price": 79.99,
        "category": "electronics"
    }
    """
    try:
        result = await agent.analyze(item)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/bulk", response_model=BulkAnalysisResponse)
async def analyze_bulk(
    request: BulkAnalysisRequest,
    x_api_key: str = Depends(verify_api_key)
):
    """
    Analyze multiple inventory items at once.
    Returns individual results + summary statistics.
    """
    try:
        result = await agent.analyze_bulk(request.items)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/forecast")
async def forecast_demand(
    item: InventoryItem,
    x_api_key: str = Depends(verify_api_key)
):
    """
    Get demand forecast for next 90 days.
    """
    try:
        result = await agent.forecast_demand(item)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
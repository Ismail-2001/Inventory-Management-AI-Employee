"""
Inventory Agent - API Server
Run: uvicorn api.main:app --reload --port 8002
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from typing import Optional
import os

from agent.inventory_agent import agent, InventoryItem, InventoryAnalysis, BulkAnalysisRequest, BulkAnalysisResponse
from shared.middleware import setup_middleware


app = FastAPI(
    title="Inventory Agent",
    description="AI-powered inventory management, demand forecasting, and reorder optimization",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

setup_middleware(app, rate_limit_per_minute=60)

API_KEY = os.getenv("AGENT_API_KEY", "demo-key-2024")


async def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


@app.on_event("shutdown")
async def shutdown():
    await agent.close()


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
            "Stockout Prediction",
        ],
        "endpoints": {
            "analyze": "POST /api/v1/analyze",
            "bulk": "POST /api/v1/bulk",
            "forecast": "POST /api/v1/forecast",
            "health": "GET /health",
        },
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent": "inventory",
        "version": "1.0.0",
        "provider": "gemini" if os.getenv("GOOGLE_API_KEY") else "mock",
    }


@app.post("/api/v1/analyze", response_model=InventoryAnalysis)
async def analyze_inventory(
    item: InventoryItem,
    x_api_key: str = Depends(verify_api_key),
):
    try:
        return await agent.analyze(item)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Analysis failed")


@app.post("/api/v1/bulk", response_model=BulkAnalysisResponse)
async def analyze_bulk(
    request: BulkAnalysisRequest,
    x_api_key: str = Depends(verify_api_key),
):
    try:
        return await agent.analyze_bulk(request.items)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Bulk analysis failed")


@app.post("/api/v1/forecast")
async def forecast_demand(
    item: InventoryItem,
    x_api_key: str = Depends(verify_api_key),
):
    try:
        return await agent.forecast_demand(item)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Forecast failed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

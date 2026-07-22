"""
Inventory Agent - API Server
Run: uvicorn api.main:app --reload --port 8002
"""

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
import os

from agent.db import close_checkpointer, create_checkpointer
from agent.graph import build_graph

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse

from api.rate_limit import limiter
from agent.inventory_agent import agent, InventoryItem, InventoryAnalysis, BulkAnalysisRequest, BulkAnalysisResponse
from api.routes.operations import router as ops_router
from api.routes.purchase_orders import router as po_router
from api.routes.run_sync import router as run_sync_router
from api.routes.webhooks import router as webhooks_router
from agent.auth import verify_api_key
from agent.config import settings


def _get_provider() -> str:
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "mock"


app = FastAPI(
    title="Inventory Agent",
    description="AI-powered inventory management, demand forecasting, and reorder optimization",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/health")
async def health(request: Request):
    return {
        "status": "healthy",
        "agent": "inventory",
        "version": "1.0.0",
        "provider": _get_provider(),
        "model": settings.model_name,
    }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": exc.__class__.__name__},
    )

app.include_router(run_sync_router)
app.include_router(po_router)
app.include_router(webhooks_router)
app.include_router(ops_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.post("/api/v1/analyze", response_model=InventoryAnalysis, deprecated=True)
async def analyze_inventory(
    request: Request,
    item: InventoryItem,
    x_api_key: str = Depends(verify_api_key)
):
    """
    DEPRECATED: this is the original single-shot demo endpoint, kept only
    because tests/test_agent.py still exercises the underlying agent module.
    New integrations should use POST /api/v1/run-sync, which runs the real
    LangGraph pipeline (sync -> forecast -> risk -> po_draft -> notify)
    against actual Shopify data instead of a manually-posted single item.

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


@app.post("/api/v1/bulk", response_model=BulkAnalysisResponse, deprecated=True)
async def analyze_bulk(
    request: Request,
    request_body: BulkAnalysisRequest,
    x_api_key: str = Depends(verify_api_key)
):
    """DEPRECATED: see /api/v1/analyze. Use /api/v1/run-sync instead."""
    try:
        result = await agent.analyze_bulk(request_body.items)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/forecast", deprecated=True)
async def forecast_demand(
    request: Request,
    item: InventoryItem,
    x_api_key: str = Depends(verify_api_key)
):
    """DEPRECATED: see /api/v1/analyze. Use /api/v1/run-sync instead."""
    try:
        result = await agent.forecast_demand(item)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.on_event("startup")
async def startup():
    settings.validate_required()

    app.state.checkpointer = create_checkpointer()
    app.state.graph = build_graph().compile(checkpointer=app.state.checkpointer, interrupt_after=["notify_pending"])

    from agent.scheduler import start
    start()


@app.on_event("shutdown")
async def shutdown():
    await close_checkpointer(getattr(app.state, "checkpointer", None))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

"""
Inventory Agent — Production API Server
Run: uvicorn api.main:app --host 0.0.0.0 --port 8002
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agent.db import close_checkpointer, create_checkpointer
from agent.graph import build_graph

from slowapi import _rate_limit_exceeded_handler
from shared.task_queue import task_queue
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse

from shared.log_config import configure_logging
configure_logging()

from agent.telemetry import setup_telemetry
setup_telemetry()

from opentelemetry import trace
from api.rate_limit import limiter
from agent.inventory_agent import agent, InventoryItem, InventoryAnalysis, BulkAnalysisRequest, BulkAnalysisResponse
from api.routes.operations import router as ops_router
from api.routes.purchase_orders import router as po_router
from api.routes.run_sync import router as run_sync_router
from api.routes.webhooks import router as webhooks_router
from agent.auth import verify_api_key
from agent.config import settings


_dev_notifications: list[dict] = []


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

from starlette.middleware.base import BaseHTTPMiddleware
from passlib.hash import bcrypt
from agent.models import Merchant, MerchantTier

_tier_cache: dict[str, MerchantTier] = {}

class TierLookupMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key") or ""
        if api_key:
            prefix = api_key[:8]
            cached = _tier_cache.get(prefix)
            if cached:
                request.state.merchant_tier = cached
            elif prefix:
                try:
                    from agent.db import async_session_factory
                    from sqlalchemy import select
                    async with async_session_factory() as session:
                        result = await session.execute(
                            select(Merchant).where(Merchant.key_prefix == prefix).limit(1)
                        )
                        merchant = result.scalar_one_or_none()
                        if merchant:
                            tier = MerchantTier(merchant.tier) if merchant.tier in ("developer", "business", "enterprise") else MerchantTier.developer
                            _tier_cache[prefix] = tier
                            request.state.merchant_tier = tier
                except Exception:
                    pass
        return await call_next(request)

app.add_middleware(TierLookupMiddleware)


@app.post("/api/v1/dev-webhook")
async def dev_webhook(request: Request):
    body = await request.json()
    _dev_notifications.append({"text": body.get("text", "")})
    if len(_dev_notifications) > 50:
        _dev_notifications.pop(0)
    return {"ok": True}


@app.get("/api/v1/dev-webhook")
async def dev_webhook_log():
    return _dev_notifications


@app.get("/health")
async def health(request: Request):
    return {
        "status": "healthy",
        "agent": "inventory",
        "version": "1.0.0",
        "region": settings.deployment_region,
        "provider": _get_provider(),
        "model": settings.model_name,
    }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

app.include_router(run_sync_router)
app.include_router(po_router)
app.include_router(webhooks_router)
app.include_router(ops_router)
from api.routes.keys import router as keys_router
app.include_router(keys_router)
from api.routes.usage import router as usage_router
app.include_router(usage_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from agent.telemetry import RequestTracingMiddleware
app.add_middleware(RequestTracingMiddleware)

from starlette.middleware.base import BaseHTTPMiddleware

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int = 1_048_576):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request too large"})
        return await call_next(request)

app.add_middleware(RequestSizeLimitMiddleware, max_bytes=1_048_576)

class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                headers.extend([
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                ])
                if settings.domain:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

app.add_middleware(SecurityHeadersMiddleware)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "inventory-frontend" / "dist"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.post("/api/v1/analyze", response_model=InventoryAnalysis, deprecated=True)
@limiter.limit("5/minute")
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
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/v1/bulk", response_model=BulkAnalysisResponse, deprecated=True)
@limiter.limit("3/minute")
async def analyze_bulk(
    request: Request,
    request_body: BulkAnalysisRequest,
    x_api_key: str = Depends(verify_api_key)
):
    """DEPRECATED: see /api/v1/analyze. Use /api/v1/run-sync instead."""
    try:
        result = await agent.analyze_bulk(request_body.items)
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/v1/forecast", deprecated=True)
@limiter.limit("5/minute")
async def forecast_demand(
    request: Request,
    item: InventoryItem,
    x_api_key: str = Depends(verify_api_key)
):
    """DEPRECATED: see /api/v1/analyze. Use /api/v1/run-sync instead."""
    try:
        result = await agent.forecast_demand(item)
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.on_event("startup")
async def startup():
    settings.validate_required()

    app.state.checkpointer = create_checkpointer()
    app.state.graph = build_graph().compile(checkpointer=app.state.checkpointer, interrupt_after=["notify_pending"])

    task_queue.start(app)
    from agent.scheduler import start
    start()


@app.on_event("shutdown")
async def shutdown():
    await task_queue.stop()
    await close_checkpointer(getattr(app.state, "checkpointer", None))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

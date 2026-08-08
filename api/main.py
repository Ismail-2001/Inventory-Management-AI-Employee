"""
Inventory Agent — Production API Server
Run: uvicorn api.main:app --host 0.0.0.0 --port 8002
"""

import asyncio
import contextlib
import logging
import os
import signal
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.responses import JSONResponse, Response

from agent.db import close_checkpointer, create_checkpointer
from agent.graph import build_graph
from shared.log_config import configure_logging
from shared.task_queue import task_queue

configure_logging()

from agent.telemetry import setup_telemetry

setup_telemetry()

from agent.auth import verify_api_key
from agent.config import settings
from agent.inventory_agent import BulkAnalysisRequest, BulkAnalysisResponse, InventoryAnalysis, InventoryItem, agent
from api.rate_limit import _get_tier_limit, limiter
from api.routes.operations import router as ops_router
from api.routes.purchase_orders import router as po_router
from api.routes.run_sync import router as run_sync_router
from api.routes.webhooks import router as webhooks_router

logger = logging.getLogger(__name__)


_dev_notifications: list[dict[str, Any]] = []


def _get_provider() -> str:
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "mock"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings.validate_required()

    app.state.checkpointer = create_checkpointer()
    app.state.graph = build_graph().compile(checkpointer=app.state.checkpointer, interrupt_after=["notify_pending"])

    task_queue.start(app)
    from agent.scheduler import start

    start()

    try:
        from shared.redis_cache import _get_redis

        r = _get_redis()
        if r is not None:
            await r.ping()
    except Exception:
        pass

    _shutdown_event = asyncio.Event()
    _inflight = {"count": 0}
    _original_handler = signal.getsignal(signal.SIGTERM)

    async def _graceful_shutdown() -> None:
        logger.info("Graceful shutdown initiated — draining in-flight requests")
        _shutdown_event.set()

    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        loop.create_task(_graceful_shutdown())

    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _signal_handler)

    yield

    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, ValueError):
            loop.remove_signal_handler(sig)

    drain_timeout = 10.0
    start_time = time.monotonic()
    while _inflight["count"] > 0 and (time.monotonic() - start_time) < drain_timeout:
        logger.info("Waiting for %d in-flight request(s) to complete", _inflight["count"])
        await asyncio.sleep(0.2)

    await task_queue.stop()
    await close_checkpointer(getattr(app.state, "checkpointer", None))
    try:
        from shared.redis_cache import close_redis

        await close_redis()
    except Exception:
        pass

    try:
        from agent.db import engine

        await engine.dispose()
    except Exception:
        pass

    logger.info("Graceful shutdown complete")


app = FastAPI(
    title="Inventory Agent",
    description="AI-powered inventory management, demand forecasting, and reorder optimization",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.state.limiter = limiter


async def _rate_limit_handler(request: Request, exc: Exception) -> Response:
    return _rate_limit_exceeded_handler(request, exc)  # type: ignore[arg-type]


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

from starlette.middleware.base import BaseHTTPMiddleware

from agent.config import settings as _cfg
from agent.models import Merchant, MerchantTier

_tier_cache: Any = None
_tier_cache_dict: Any = None

if _cfg.redis_url:
    try:
        from shared.redis_cache import RedisCache as _TierCache

        _tier_cache = _TierCache(namespace="tier", ttl_seconds=300, max_size=200)
    except Exception:
        from collections import OrderedDict

        _tier_cache = None
else:
    _tier_cache = None

if _tier_cache is None:
    from collections import OrderedDict

    _tier_cache_dict = OrderedDict()
else:
    _tier_cache_dict = None

_TIER_CACHE_MAX = 200


class TierLookupMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        api_key = request.headers.get("x-api-key") or request.headers.get("X-API-Key") or ""
        if api_key:
            prefix = api_key[:8]
            if _tier_cache is not None:
                cached = await _tier_cache.get(prefix)
                if cached is not None:
                    request.state.merchant_tier = MerchantTier(cached) if isinstance(cached, str) else cached
                elif prefix:
                    try:
                        from sqlalchemy import select

                        from agent.db import async_session_factory

                        async with async_session_factory() as session:
                            result = await session.execute(
                                select(Merchant).where(Merchant.key_prefix == prefix).limit(1)
                            )
                            merchant = result.scalar_one_or_none()
                            if merchant:
                                tier = (
                                    MerchantTier(merchant.tier)
                                    if merchant.tier in ("developer", "business", "enterprise")
                                    else MerchantTier.developer
                                )
                                await _tier_cache.set(prefix, tier.value)
                                request.state.merchant_tier = tier
                    except Exception:
                        pass
            elif _tier_cache_dict is not None:
                cached = _tier_cache_dict.get(prefix)
                if cached is not None:
                    _tier_cache_dict.move_to_end(prefix)
                    request.state.merchant_tier = cached
                elif prefix:
                    try:
                        from sqlalchemy import select

                        from agent.db import async_session_factory

                        async with async_session_factory() as session:
                            result = await session.execute(
                                select(Merchant).where(Merchant.key_prefix == prefix).limit(1)
                            )
                            merchant = result.scalar_one_or_none()
                            if merchant:
                                tier = (
                                    MerchantTier(merchant.tier)
                                    if merchant.tier in ("developer", "business", "enterprise")
                                    else MerchantTier.developer
                                )
                                _tier_cache_dict[prefix] = tier
                                if len(_tier_cache_dict) > _TIER_CACHE_MAX:
                                    _tier_cache_dict.popitem(last=False)
                                request.state.merchant_tier = tier
                    except Exception:
                        pass
        return await call_next(request)


app.add_middleware(TierLookupMiddleware)


@app.post("/api/v1/dev-webhook")
async def dev_webhook(request: Request) -> dict[str, Any]:
    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="Not found")
    body = await request.json()
    _dev_notifications.append({"text": body.get("text", "")})
    if len(_dev_notifications) > 50:
        _dev_notifications.pop(0)
    return {"ok": True}


@app.get("/api/v1/dev-webhook")
async def dev_webhook_log() -> list[dict[str, Any]]:
    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="Not found")
    return _dev_notifications


@app.get("/api/v1/config")
async def frontend_config() -> dict[str, Any]:
    result: dict[str, Any] = {}
    if settings.environment == "production":
        result["auth_mode"] = "proxy"
    else:
        result["auth_mode"] = "key"
        result["api_key"] = settings.agent_api_key

    from agent.sso import get_sso_providers

    providers = get_sso_providers()
    result["sso_enabled"] = len(providers) > 0
    result["sso_providers"] = [{"name": p.name, "type": p.provider_type} for p in providers]

    return result


@app.get("/health")
async def health(request: Request) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "healthy",
        "agent": "inventory",
        "version": "1.0.0",
        "region": settings.deployment_region,
        "provider": _get_provider(),
        "model": settings.model_name,
    }
    try:
        from agent.db import engine

        async with engine.connect() as conn:
            from sqlalchemy import text

            await conn.execute(text("SELECT 1"))
        result["database"] = "ok"
    except Exception:
        result["status"] = "degraded"
        result["database"] = "error"
    try:
        from shared.redis_cache import _get_redis

        r = _get_redis()
        if r is not None:
            await r.ping()
            result["redis"] = "ok"
        else:
            result["redis"] = "not_configured"
    except Exception:
        result["redis"] = "error"
        if result["status"] == "healthy":
            result["status"] = "degraded"

    from agent.sso import get_sso_providers

    sso_providers = get_sso_providers()
    result["sso"] = "configured" if sso_providers else "not_configured"

    return result


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
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
from api.routes.audit import router as audit_router

app.include_router(audit_router)
from api.routes.sso import router as sso_router

app.include_router(sso_router)
from api.routes.branding import router as branding_router

app.include_router(branding_router)

from shared.metrics import setup_metrics

setup_metrics(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from agent.telemetry import RequestTracingMiddleware

app.add_middleware(RequestTracingMiddleware)  # type: ignore[arg-type]


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, max_bytes: int = 1_048_576) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request too large"})
        return await call_next(request)


app.add_middleware(RequestSizeLimitMiddleware, max_bytes=1_048_576)


class SecurityHeadersMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                headers.extend(
                    [
                        (
                            b"content-security-policy",
                            b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'",
                        ),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    ]
                )
                if settings.domain:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


app.add_middleware(SecurityHeadersMiddleware)  # type: ignore[arg-type]


class CorrelationIdMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from shared.metrics import metrics

        request = Request(scope, receive)
        correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", correlation_id.encode()))
                message["headers"] = headers
            await send(message)

        scope["correlation_id"] = correlation_id
        await self.app(scope, receive, send_wrapper)
        elapsed = time.perf_counter() - start
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        metrics.inc("http_requests_total", method=method, path=path, status=str(status_code))
        metrics.observe("http_request_duration_seconds", elapsed, method=method, path=path)


app.add_middleware(CorrelationIdMiddleware)  # type: ignore[arg-type]


class InflightTracker:
    def __init__(self) -> None:
        self.count = 0
        self._lock = asyncio.Lock()

    async def increment(self) -> None:
        async with self._lock:
            self.count += 1
        self._emit()

    async def decrement(self) -> None:
        async with self._lock:
            self.count = max(0, self.count - 1)
        self._emit()

    def _emit(self) -> None:
        from shared.metrics import metrics

        metrics.gauge("in_flight_requests", self.count)


inflight_tracker = InflightTracker()


class InflightMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        await inflight_tracker.increment()
        try:
            await self.app(scope, receive, send)
        finally:
            await inflight_tracker.decrement()


app.add_middleware(InflightMiddleware)  # type: ignore[arg-type]

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "inventory-frontend" / "dist"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


@app.post("/api/v1/analyze", response_model=InventoryAnalysis, deprecated=True)
@limiter.limit(_get_tier_limit)
async def analyze_inventory(
    request: Request, item: InventoryItem, x_api_key: str = Depends(verify_api_key)
) -> InventoryAnalysis:
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.post("/api/v1/bulk", response_model=BulkAnalysisResponse, deprecated=True)
@limiter.limit(_get_tier_limit)
async def analyze_bulk(
    request: Request, request_body: BulkAnalysisRequest, x_api_key: str = Depends(verify_api_key)
) -> BulkAnalysisResponse:
    """DEPRECATED: see /api/v1/analyze. Use /api/v1/run-sync instead."""
    try:
        result = await agent.analyze_bulk(request_body.items)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.post("/api/v1/forecast", deprecated=True)
@limiter.limit(_get_tier_limit)
async def forecast_demand(
    request: Request, item: InventoryItem, x_api_key: str = Depends(verify_api_key)
) -> dict[str, Any]:
    """DEPRECATED: see /api/v1/analyze. Use /api/v1/run-sync instead."""
    try:
        result = await agent.forecast_demand(item)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)

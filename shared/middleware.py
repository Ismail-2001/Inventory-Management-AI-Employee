"""
Shared FastAPI middleware for all agents.

Rate limiting (in-memory sliding window).
Safe error handling (no stack traces exposed).
Content-Type validation.
Request ID tracking.
"""

import os
import time
import uuid
import logging
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger("agent.middleware")


class InMemoryRateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: Dict[str, List[float]] = {}

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        now = time.time()
        window_start = now - self.window_seconds
        buckets = self._buckets.setdefault(key, [])
        buckets[:] = [t for t in buckets if t > window_start]
        if len(buckets) >= self.max_requests:
            retry_after = int(buckets[0] + self.window_seconds - now) + 1
            return False, retry_after
        buckets.append(now)
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_requests: int = 60, window_seconds: float = 60.0):
        super().__init__(app)
        self.limiter = InMemoryRateLimiter(max_requests, window_seconds)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in ("/health", "/", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        api_key = request.headers.get("x-api-key", "")
        rate_key = f"{client_ip}:{api_key}"

        allowed, retry_after = self.limiter.is_allowed(rate_key)
        if not allowed:
            return Response(
                status_code=429,
                content='{"detail":"Rate limit exceeded. Try again later."}',
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)


def safe_error_handler(request: Request, exc: HTTPException):
    logger.warning("HTTP %s on %s %s: %s", exc.status_code, request.method, request.url.path, exc.detail)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


def safe_unhandled_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def setup_middleware(app: FastAPI, rate_limit_per_minute: int = 60):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RateLimitMiddleware, max_requests=rate_limit_per_minute)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.middleware("http")
    async def validate_content_type(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" not in content_type:
                return Response(
                    status_code=415,
                    content='{"detail":"Unsupported media type. Use application/json"}',
                    media_type="application/json",
                )
        return await call_next(request)

    app.add_exception_handler(HTTPException, safe_error_handler)
    app.add_exception_handler(Exception, safe_unhandled_handler)

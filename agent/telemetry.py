import os
import time
from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, TypeVar

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

F = TypeVar("F", bound=Callable[..., Any])


class _NoOpExporter(SpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


_tracer: Any | None = None


def setup_telemetry() -> None:
    global _tracer
    if _tracer is not None:
        return

    resource = Resource.create({"service.name": "inventory-agent", "service.version": "1.0.0"})
    provider = TracerProvider(resource=resource)

    otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if otel_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otel_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception:
            pass
    else:
        provider.add_span_processor(BatchSpanProcessor(_NoOpExporter()))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(__name__)


def get_tracer() -> Any:
    global _tracer
    if _tracer is None:
        setup_telemetry()
    return _tracer


def trace_node(name: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            tracer = get_tracer()
            start = time.perf_counter()
            with tracer.start_as_current_span(name) as span:
                span.set_attribute("node.name", name)
                try:
                    result: dict[str, Any] = await func(state)
                    span.set_attribute("node.success", True)
                    span.set_attribute("node.duration_ms", round((time.perf_counter() - start) * 1000, 1))
                    span.set_attribute(
                        "node.output_keys",
                        ", ".join(result.keys()) if result else "none",
                    )
                    return result
                except Exception as e:
                    span.set_attribute("node.success", False)
                    span.set_attribute("node.duration_ms", round((time.perf_counter() - start) * 1000, 1))
                    span.record_exception(e)
                    raise

        return wrapper  # type: ignore[return-value]

    return decorator


class RequestTracingMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        tracer = get_tracer()
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        span_name = f"{method} {path}"

        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.url", path)
            start = time.perf_counter()
            try:
                await self.app(scope, receive, send)
            finally:
                span.set_attribute("http.duration_ms", round((time.perf_counter() - start) * 1000, 1))

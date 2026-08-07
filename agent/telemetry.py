import os
import time
from functools import wraps

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

from agent.config import settings


class _NoOpExporter(SpanExporter):
    def export(self, spans):
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis: int = 30000):
        pass


_tracer = None


def setup_telemetry():
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


def get_tracer():
    if _tracer is None:
        setup_telemetry()
    return _tracer


def trace_node(name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(state: dict) -> dict:
            tracer = get_tracer()
            start = time.perf_counter()
            with tracer.start_as_current_span(name) as span:
                span.set_attribute("node.name", name)
                try:
                    result = await func(state)
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

        return wrapper

    return decorator


class RequestTracingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
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

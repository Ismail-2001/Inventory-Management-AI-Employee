import os
from contextlib import asynccontextmanager
from functools import wraps
from typing import AsyncGenerator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from agent.config import settings

_initialized = False
_tracer = None


def _setup():
    global _initialized, _tracer
    if _initialized:
        return

    resource = Resource.create({"service.name": "inventory-agent", "service.version": "1.0.0"})
    provider = TracerProvider(resource=resource)

    otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if otel_endpoint:
        exporter = OTLPSpanExporter(endpoint=otel_endpoint)
    else:
        exporter = ConsoleSpanExporter()

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(__name__)
    _initialized = True


def get_tracer():
    _setup()
    return _tracer


def trace_node(name: str):
    tracer = get_tracer()

    def decorator(func):
        @wraps(func)
        async def wrapper(state: dict) -> dict:
            with tracer.start_as_current_span(name) as span:
                span.set_attribute("node.name", name)
                try:
                    result = await func(state)
                    span.set_attribute("node.success", True)
                    span.set_attribute(
                        "node.output_keys",
                        ", ".join(result.keys()) if result else "none",
                    )
                    return result
                except Exception as e:
                    span.set_attribute("node.success", False)
                    span.record_exception(e)
                    raise

        return wrapper

    return decorator

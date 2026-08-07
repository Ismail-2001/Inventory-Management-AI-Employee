import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from agent import telemetry as telemetry_module


def test_setup_telemetry_singleton():
    telemetry_module._tracer = None
    telemetry_module.setup_telemetry()
    first = telemetry_module._tracer
    assert first is not None

    telemetry_module.setup_telemetry()
    assert telemetry_module._tracer is first

    telemetry_module._tracer = None


def test_get_tracer_initializes_if_none():
    telemetry_module._tracer = None
    tracer = telemetry_module.get_tracer()
    assert tracer is not None
    telemetry_module._tracer = None


@pytest.mark.asyncio
async def test_trace_node_decorator_success():
    telemetry_module._tracer = None

    @telemetry_module.trace_node("test_node")
    async def my_node(state: dict) -> dict:
        return {"output": "ok"}

    result = await my_node({"input": "test"})
    assert result == {"output": "ok"}
    telemetry_module._tracer = None


@pytest.mark.asyncio
async def test_trace_node_decorator_error():
    telemetry_module._tracer = None

    @telemetry_module.trace_node("fail_node")
    async def bad_node(state: dict) -> dict:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await bad_node({})
    telemetry_module._tracer = None


@pytest.mark.asyncio
async def test_request_tracing_middleware_skips_non_http():
    called = []

    async def app(scope, receive, send):
        called.append(True)

    middleware = telemetry_module.RequestTracingMiddleware(app)

    await middleware({"type": "websocket"}, None, None)
    assert called == [True]

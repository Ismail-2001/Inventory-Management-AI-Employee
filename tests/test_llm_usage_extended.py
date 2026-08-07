import pytest
from unittest.mock import AsyncMock
from types import SimpleNamespace

from agent import llm_usage as llm_module


def test_estimate_cost_zero():
    assert llm_module._estimate_cost(0, 0) == 0.0


def test_estimate_cost_input_only():
    result = llm_module._estimate_cost(1000, 0)
    assert result == pytest.approx(0.00015, abs=1e-6)


def test_estimate_cost_output_only():
    result = llm_module._estimate_cost(0, 1000)
    assert result == pytest.approx(0.0006, abs=1e-6)


def test_estimate_cost_both():
    result = llm_module._estimate_cost(1000, 1000)
    assert result == pytest.approx(0.00075, abs=1e-6)


def test_estimate_cost_none_defaults():
    assert llm_module._estimate_cost(None, None) == 0.0


@pytest.mark.asyncio
async def test_log_llm_call_noop_on_none(monkeypatch):
    called = []
    original_factory = llm_module.async_session_factory

    class FakeFactory:
        def __call__(self):
            raise RuntimeError("should not be called")

    monkeypatch.setattr(llm_module, "async_session_factory", FakeFactory())
    await llm_module.log_llm_call("test_node", None)


@pytest.mark.asyncio
async def test_log_llm_call_records_usage(monkeypatch):
    class FakeSession:
        def __init__(self):
            self.added = []
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        def add(self, obj):
            self.added.append(obj)
        async def commit(self):
            pass

    session = FakeSession()
    monkeypatch.setattr(llm_module, "async_session_factory", lambda: session)

    await llm_module.log_llm_call("forecast_node", "The forecast predicts high demand")

    assert len(session.added) == 1
    usage = session.added[0]
    assert usage.node_name == "forecast_node"
    assert usage.tokens_in > 0
    assert usage.tokens_out > 0
    assert usage.estimated_cost > 0


@pytest.mark.asyncio
async def test_should_skip_when_cap_zero(monkeypatch):
    monkeypatch.setattr(llm_module.settings, "daily_llm_spend_cap", 0)
    result = await llm_module.should_skip_llm_call("node")
    assert result is False


@pytest.mark.asyncio
async def test_should_skip_when_at_cap(monkeypatch):
    monkeypatch.setattr(llm_module.settings, "daily_llm_spend_cap", 1.0)
    monkeypatch.setattr(llm_module, "get_daily_spend_total", AsyncMock(return_value=1.5))
    result = await llm_module.should_skip_llm_call("node")
    assert result is True


@pytest.mark.asyncio
async def test_should_not_skip_below_cap(monkeypatch):
    monkeypatch.setattr(llm_module.settings, "daily_llm_spend_cap", 5.0)
    monkeypatch.setattr(llm_module, "get_daily_spend_total", AsyncMock(return_value=2.0))
    result = await llm_module.should_skip_llm_call("node")
    assert result is False

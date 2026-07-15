import pytest

from agent.llm_usage import should_skip_llm_call


@pytest.mark.asyncio
async def test_should_skip_llm_call_when_spend_cap_reached(monkeypatch):
    async def fake_total(node_name=None):
        return 5.0

    monkeypatch.setattr("agent.llm_usage.get_daily_spend_total", fake_total)

    assert await should_skip_llm_call("po_draft", "prompt") is True


@pytest.mark.asyncio
async def test_should_not_skip_llm_call_when_spend_is_below_cap(monkeypatch):
    async def fake_total(node_name=None):
        return 4.0

    monkeypatch.setattr("agent.llm_usage.get_daily_spend_total", fake_total)

    assert await should_skip_llm_call("po_draft", "prompt") is False

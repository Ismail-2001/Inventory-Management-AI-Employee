import asyncio
from types import SimpleNamespace

import pytest
from starlette.requests import Request

import agent.scheduler as scheduler_module
import api.main as api_main
import api.routes.run_sync as run_sync_module


def test_startup_initializes_shared_graph_and_checkpointer(monkeypatch):
    class FakeSaver:
        pass

    class FakeCompiledGraph:
        pass

    class FakeBuilder:
        def __init__(self, graph):
            self.graph = graph

        def compile(self, checkpointer, interrupt_after):
            assert checkpointer is saver
            assert interrupt_after == ["notify_pending"]
            return self.graph

    saver = FakeSaver()
    graph = FakeCompiledGraph()

    monkeypatch.setattr(api_main.settings, "validate_required", lambda: None)
    monkeypatch.setattr(api_main, "create_checkpointer", lambda: saver)
    monkeypatch.setattr(api_main, "build_graph", lambda: FakeBuilder(graph))
    monkeypatch.setattr(scheduler_module, "start", lambda: None)

    async def _run_lifespan():
        async with api_main.lifespan(api_main.app):
            pass

    asyncio.run(_run_lifespan())

    assert api_main.app.state.checkpointer is saver
    assert api_main.app.state.graph is graph


@pytest.mark.asyncio
async def test_run_sync_uses_graph_from_app_state():
    class FakeGraph:
        async def ainvoke(self, state, config):
            return {
                "synced_products": 3,
                "synced_sales": 2,
                "risk_alerts": [],
                "purchase_orders": [],
            }

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/run-sync",
        "headers": [],
        "app": SimpleNamespace(state=SimpleNamespace(graph=FakeGraph())),
    }
    request = Request(scope, receive=lambda: None, send=lambda msg: None)

    merchant = SimpleNamespace(id=1)
    response = await run_sync_module.run_sync(request, merchant=merchant)

    assert response["synced_products"] == 3
    assert response["synced_sales"] == 2
    assert response["thread_id"]

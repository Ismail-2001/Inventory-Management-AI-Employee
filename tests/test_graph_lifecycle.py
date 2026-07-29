import asyncio
from types import SimpleNamespace

import api.main as api_main
import api.routes.run_sync as run_sync_module
import agent.scheduler as scheduler_module


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

    asyncio.run(api_main.startup())

    assert api_main.app.state.checkpointer is saver
    assert api_main.app.state.graph is graph


def test_run_sync_uses_graph_from_app_state(monkeypatch):
    class FakeGraph:
        async def ainvoke(self, state, config):
            return {
                "synced_products": 3,
                "synced_sales": 2,
                "risk_alerts": [],
                "purchase_orders": [],
            }

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(graph=FakeGraph())))

    def fail_compilation():
        raise AssertionError("run_sync should reuse the shared graph from app.state")

    monkeypatch.setattr(run_sync_module, "get_compiled_graph", fail_compilation)

    response = asyncio.run(run_sync_module.run_sync(request, merchant=object()))

    assert response["synced_products"] == 3
    assert response["synced_sales"] == 2
    assert response["thread_id"]

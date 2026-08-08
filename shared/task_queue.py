"""In-process background task queue for graph execution.

Enqueue a sync run and immediately return a task_id (HTTP 202).
The worker processes tasks sequentially on the event loop.
For multi-replica deployments, replace with ARQ/Celery + Redis.
"""
import asyncio
import uuid
from collections import OrderedDict
from typing import Any

from fastapi import FastAPI

_MAX_RESULTS = 200


class BackgroundTaskQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[tuple[str, dict[str, Any], dict[str, Any]]] = asyncio.Queue()
        self._results: OrderedDict[str, Any] = OrderedDict()
        self._worker: asyncio.Task[None] | None = None

    def start(self, app: FastAPI) -> None:
        self._worker = asyncio.create_task(self._worker_loop(app))

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    async def enqueue(self, initial_state: dict[str, Any], config: dict[str, Any]) -> str:
        task_id = str(uuid.uuid4())
        await self._queue.put((task_id, initial_state, config))
        self._emit_gauge()
        return task_id

    def get_result(self, task_id: str) -> Any | None:
        return self._results.get(task_id)

    def remove_result(self, task_id: str) -> None:
        self._results.pop(task_id, None)
        self._emit_gauge()

    def _emit_gauge(self) -> None:
        from shared.metrics import metrics
        metrics.gauge("task_queue_depth", self._queue.qsize())
        metrics.gauge("task_queue_results", len(self._results))

    async def _worker_loop(self, app: FastAPI) -> None:
        while True:
            task_id, initial_state, config = await self._queue.get()
            try:
                graph = app.state.graph
                result = await asyncio.wait_for(
                    graph.ainvoke(initial_state, config),
                    timeout=120.0,
                )
                self._results[task_id] = result
                if len(self._results) > _MAX_RESULTS:
                    self._results.popitem(last=False)
            except TimeoutError:
                self._results[task_id] = {"error": "Graph execution timed out"}
            except Exception:
                self._results[task_id] = {"error": "Internal error processing task"}
            finally:
                self._queue.task_done()
                self._emit_gauge()


task_queue = BackgroundTaskQueue()

"""In-process background task queue for graph execution.

Enqueue a sync run and immediately return a task_id (HTTP 202).
The worker processes tasks sequentially on the event loop.
For multi-replica deployments, replace with ARQ/Celery + Redis.
"""
import asyncio
import uuid
from collections import OrderedDict
from typing import Any

from fastapi import HTTPException

_MAX_RESULTS = 200


class BackgroundTaskQueue:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._results: OrderedDict[str, Any] = OrderedDict()
        self._worker: asyncio.Task | None = None

    def start(self, app):
        self._worker = asyncio.create_task(self._worker_loop(app))

    async def stop(self):
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass

    async def enqueue(self, initial_state: dict, config: dict) -> str:
        task_id = str(uuid.uuid4())
        await self._queue.put((task_id, initial_state, config))
        return task_id

    def get_result(self, task_id: str) -> Any | None:
        return self._results.get(task_id)

    def remove_result(self, task_id: str) -> None:
        self._results.pop(task_id, None)

    async def _worker_loop(self, app):
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
            except asyncio.TimeoutError:
                self._results[task_id] = {"error": "Graph execution timed out"}
            except Exception:
                self._results[task_id] = {"error": "Internal error processing task"}
            finally:
                self._queue.task_done()


task_queue = BackgroundTaskQueue()

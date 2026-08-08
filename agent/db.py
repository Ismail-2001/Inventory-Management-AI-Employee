import asyncio
import logging
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import QueuePool

from agent.config import settings

logger = logging.getLogger(__name__)

_checkout_times: dict[int, float] = {}
_POOL_WARN_THRESHOLD = 0.8


def _setup_pool_monitoring(engine: AsyncEngine) -> None:
    pool: QueuePool = engine.sync_engine.pool  # type: ignore[assignment]

    def _emit_pool_gauge() -> None:
        from shared.metrics import metrics
        db_name = engine.url.database or "default"
        metrics.gauge(
            "db_connection_pool",
            pool.checkedout(),
            database=db_name,
        )

    @event.listens_for(engine.sync_engine, "checkout")
    def on_checkout(dbapi_conn: Any, connection_rec: Any, connection_proxy: Any) -> None:
        _checkout_times[id(dbapi_conn)] = time.perf_counter()
        _emit_pool_gauge()

    @event.listens_for(engine.sync_engine, "checkin")
    def on_checkin(dbapi_conn: Any, connection_rec: Any) -> None:
        checkout_start = _checkout_times.pop(id(dbapi_conn), None)
        if checkout_start is not None:
            elapsed_ms = (time.perf_counter() - checkout_start) * 1000
            if elapsed_ms > 1000:
                logger.warning("Slow pool checkout: %.0fms (pool_size=%d)", elapsed_ms, pool.size())
        _emit_pool_gauge()

    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_conn: Any, connection_rec: Any) -> None:
        checked_out = pool.checkedout()
        total = pool.size() + pool.overflow()
        if total > 0 and checked_out / total >= _POOL_WARN_THRESHOLD:
            logger.warning(
                "Connection pool near exhaustion: %d/%d checked out (pool_size=%d, overflow=%d)",
                checked_out, total, pool.size(), pool.overflow(),
            )
        _emit_pool_gauge()


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    pool_pre_ping=True,
    pool_timeout=30,
    connect_args={
        "server_settings": {"statement_timeout": "30000", "lock_timeout": "10000"},
    },
)
_setup_pool_monitoring(engine)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

_read_engine: AsyncEngine | None = None
async_session_factory_readonly: async_sessionmaker[AsyncSession] | None = None
if settings.database_read_url:
    _read_engine = create_async_engine(
        settings.database_read_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        pool_pre_ping=True,
        pool_timeout=30,
        connect_args={
            "server_settings": {"statement_timeout": "30000", "lock_timeout": "10000"},
        },
    )
    _setup_pool_monitoring(_read_engine)
    async_session_factory_readonly = async_sessionmaker(_read_engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncIterator[AsyncSession]:
    factory = factory or async_session_factory
    session = factory()
    async with session as session_obj:
        yield session_obj


class Base(DeclarativeBase):
    pass


class AsyncPostgresSaver(PostgresSaver):
    """Wraps the sync PostgresSaver to provide async-compatible methods
    by delegating sync calls to a thread pool."""

    async def aget_tuple(self, config: Any) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(
        self,
        config: Any,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> Any:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: Any,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def aget(self, config: Any) -> Checkpoint | None:
        return await asyncio.to_thread(self.get, config)

    async def alist(
        self,
        config: Any | None = None,
        *,
        filter: dict[str, Any] | None = None,
        before: Any | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        tuples = await asyncio.to_thread(lambda: list(self.list(config, filter=filter, before=before, limit=limit)))
        for t in tuples:
            yield t


def create_checkpointer() -> AsyncPostgresSaver:
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        settings.checkpointer_database_url,
        min_size=1,
        max_size=5,
        open=True,
        timeout=30,
        kwargs={"options": "-c statement_timeout=30000"},
    )
    saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
    saver.setup()
    return saver


async def close_checkpointer(saver: AsyncPostgresSaver | None) -> None:
    if saver is None:
        return
    pool = getattr(saver, "_pool", None)
    if pool is not None:
        await pool.close()


async def cleanup_old_checkpoints(retention_days: int = 30) -> None:
    """Delete checkpoint data older than retention_days from the checkpointer tables."""
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        settings.checkpointer_database_url,
        min_size=1,
        max_size=1,
        open=True,
        timeout=30,
        kwargs={"options": "-c statement_timeout=120000"},
    )
    try:
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM langgraph_checkpoints WHERE created_at < NOW() - %s::interval",
                (f"{retention_days} days",),
            )
            cur.execute(
                "DELETE FROM langgraph_checkpoint_writes WHERE created_at < NOW() - %s::interval",
                (f"{retention_days} days",),
            )
            conn.commit()
    finally:
        pool.close()

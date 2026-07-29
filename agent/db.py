import asyncio
import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from agent.config import settings


engine = create_async_engine(settings.database_url, echo=False, pool_size=5, max_overflow=10, pool_recycle=3600, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

_read_engine = None
async_session_factory_readonly = None
if settings.database_read_url:
    _read_engine = create_async_engine(settings.database_read_url, echo=False, pool_size=10, max_overflow=20, pool_recycle=3600, pool_pre_ping=True)
    async_session_factory_readonly = async_sessionmaker(_read_engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope(factory=None):
    factory = factory or async_session_factory
    session = factory()
    if inspect.isawaitable(session):
        session = await session
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
        writes: list[tuple[str, Any]],
        task_id: str,
    ) -> None:
        return await asyncio.to_thread(self.put_writes, config, writes, task_id)

    async def aget(self, config: Any) -> Checkpoint | None:
        return await asyncio.to_thread(self.get, config)

    async def alist(
        self,
        config: Any | None = None,
        *,
        before: Any | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        tuples = await asyncio.to_thread(lambda: list(self.list(config, before=before, limit=limit)))
        for t in tuples:
            yield t


def create_checkpointer() -> AsyncPostgresSaver:
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(
        settings.checkpointer_database_url,
        min_size=1,
        max_size=5,
        open=True,
    )
    saver = AsyncPostgresSaver(pool)
    saver.setup()
    return saver


async def close_checkpointer(saver: AsyncPostgresSaver | None):
    if saver is None:
        return
    pool = getattr(saver, "_pool", None)
    if pool is not None:
        await pool.close()


async def cleanup_old_checkpoints(retention_days: int = 30):
    """Delete checkpoint data older than retention_days from the checkpointer tables."""
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(settings.checkpointer_database_url, min_size=1, max_size=1, open=True)
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
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

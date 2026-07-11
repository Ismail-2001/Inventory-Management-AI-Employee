import asyncio
from collections.abc import AsyncIterator
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


engine = create_async_engine(settings.database_url, echo=False, pool_size=5, max_overflow=10)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


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


def create_checkpointer() -> PostgresSaver:
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

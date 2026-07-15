from datetime import datetime, timezone

from sqlalchemy import select, func

from agent.config import settings
from agent.db import async_session_factory
from agent.models import LlmUsage


def _estimate_cost(tokens_in: int | None, tokens_out: int | None) -> float:
    in_cost = (tokens_in or 0) / 1000 * 0.00015
    out_cost = (tokens_out or 0) / 1000 * 0.0006
    return round(in_cost + out_cost, 6)


async def log_llm_call(node_name: str, response: str | None) -> None:
    if not response:
        return

    token_in = len(response.split()) // 2 + 1
    token_out = max(1, len(response.split()))
    estimated_cost = _estimate_cost(token_in, token_out)

    async with async_session_factory() as session:
        session.add(
            LlmUsage(
                node_name=node_name,
                tokens_in=token_in,
                tokens_out=token_out,
                estimated_cost=estimated_cost,
            )
        )
        await session.commit()


async def get_daily_spend_total(node_name: str | None = None) -> float:
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    async with async_session_factory() as session:
        query = select(func.coalesce(func.sum(LlmUsage.estimated_cost), 0.0)).where(LlmUsage.created_at >= today_start)
        if node_name:
            query = query.where(LlmUsage.node_name == node_name)
        result = await session.execute(query)
        return float(result.scalar_one() or 0.0)


async def should_skip_llm_call(node_name: str, prompt: str | None = None) -> bool:
    if settings.daily_llm_spend_cap <= 0:
        return False

    current_spend = await get_daily_spend_total(node_name)
    return current_spend >= settings.daily_llm_spend_cap

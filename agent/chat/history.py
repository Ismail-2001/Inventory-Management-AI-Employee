"""Persistence for chat conversations (chat_messages table)."""

from typing import Any

from sqlalchemy import func, select

from agent.db import async_session_factory
from agent.models import ChatMessage


async def save_message(
    *,
    merchant_id: int,
    conversation_id: str,
    role: str,
    content: str,
    user_id: str | None = None,
    actions: list[dict[str, Any]] | None = None,
    tool_trace: list[dict[str, Any]] | None = None,
    model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
) -> int:
    async with async_session_factory() as session:
        row = ChatMessage(
            merchant_id=merchant_id,
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            actions=actions or None,
            tool_trace=tool_trace or None,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return int(row.id)


def _to_dict(row: ChatMessage) -> dict[str, Any]:
    return {
        "id": row.id,
        "role": row.role,
        "content": row.content,
        "actions": row.actions or [],
        "tool_trace": row.tool_trace or [],
        "model": row.model,
        "tokens_in": row.tokens_in,
        "tokens_out": row.tokens_out,
        "cost_usd": row.cost_usd,
        "conversation_id": row.conversation_id,
        "user_id": row.user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def load_messages(merchant_id: int, conversation_id: str, limit: int = 200) -> list[dict[str, Any]]:
    """Full message list for a conversation, oldest first."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(ChatMessage)
            .where(
                ChatMessage.merchant_id == merchant_id,
                ChatMessage.conversation_id == conversation_id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(max(1, limit))
        )
        rows = list(result.scalars().all())
    return [_to_dict(row) for row in reversed(rows)]


async def load_history(merchant_id: int, conversation_id: str, limit: int) -> list[dict[str, Any]]:
    """Compact role/content history for the LLM (oldest first, capped)."""
    if limit <= 0:
        return []
    messages = await load_messages(merchant_id, conversation_id, limit=max(limit * 2, 40))
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m["role"] in ("user", "assistant") and (m["content"] or "").strip()
    ]
    return history[-limit:]


async def list_conversations(merchant_id: int, limit: int = 50) -> list[dict[str, Any]]:
    async with async_session_factory() as session:
        agg = await session.execute(
            select(
                ChatMessage.conversation_id,
                func.count(ChatMessage.id),
                func.max(ChatMessage.created_at),
            )
            .where(ChatMessage.merchant_id == merchant_id)
            .group_by(ChatMessage.conversation_id)
            .order_by(func.max(ChatMessage.created_at).desc())
            .limit(max(1, limit))
        )
        conversations: list[dict[str, Any]] = [
            {
                "conversation_id": row[0],
                "message_count": int(row[1]),
                "updated_at": row[2].isoformat() if row[2] else None,
                "preview": "",
                "last_role": None,
            }
            for row in agg.all()
        ]

        previews: dict[str, ChatMessage] = {}
        ids = [c["conversation_id"] for c in conversations]
        if ids:
            recent = await session.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.merchant_id == merchant_id,
                    ChatMessage.conversation_id.in_(ids),
                )
                .order_by(ChatMessage.id.desc())
                .limit(150)
            )
            for row in recent.scalars().all():
                previews.setdefault(row.conversation_id, row)

    for conversation in conversations:
        last = previews.get(conversation["conversation_id"])
        if last:
            text = (last.content or "").strip()
            conversation["preview"] = text[:120] + ("…" if len(text) > 120 else "")
            conversation["last_role"] = last.role
    return conversations

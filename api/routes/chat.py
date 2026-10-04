"""Chat API — streaming natural-language assistant over live inventory data.

POST /api/v1/chat streams Server-Sent Events while the LangGraph agent runs:

    event types: start | delta | tool | message | error
    each line:   data: {json}\\n\\n

Write actions (e.g. draft_purchase_order) are never executed by the agent —
they surface as pending actions on the final ``message`` event and require an
explicit confirm (which creates a pending_approval PO) or cancel.
"""

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.auth import verify_api_key
from agent.chat.actions import ActionError, cancel_action, confirm_action
from agent.chat.agent import ChatTurnRunner, get_chat_llm
from agent.chat.history import list_conversations, load_history, load_messages, save_message
from agent.chat.tools import ToolContext
from agent.config import settings
from agent.models import Merchant
from api.rate_limit import _get_tier_limit, limiter

logger = logging.getLogger(__name__)

router = APIRouter()

_CONVERSATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)
    conversation_id: str | None = Field(default=None, max_length=64)


class ActionRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _validate_conversation_id(conversation_id: str | None) -> str:
    if conversation_id is None:
        return ""
    if not _CONVERSATION_ID_RE.match(conversation_id):
        raise HTTPException(status_code=400, detail="Invalid conversation_id")
    return conversation_id


def _resolve_user_id(request: Request) -> str | None:
    sso_user = getattr(request.state, "sso_user", None)
    if isinstance(sso_user, dict):
        for key in ("email", "sub", "name"):
            value = sso_user.get(key)
            if value:
                return str(value)[:128]
    return None


async def _chat_event_stream(
    *,
    merchant_id: int,
    conversation_id: str,
    user_id: str | None,
    message: str,
    disconnect_check: Any,
) -> AsyncIterator[str]:
    """Run one chat turn, relaying runner events as SSE frames."""
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(event: dict[str, Any]) -> None:
        await queue.put(event)

    history = await load_history(merchant_id, conversation_id, settings.chat_history_messages)
    runner = ChatTurnRunner(llm=get_chat_llm(), ctx=ToolContext(merchant_id=merchant_id), emit=emit)

    async def produce() -> None:
        try:
            result = await runner.run(history, message)
            await save_message(
                merchant_id=merchant_id,
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=result.content,
                actions=result.actions or None,
                tool_trace=result.tool_trace or None,
                model=result.model,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                cost_usd=result.cost_usd,
            )
            await queue.put(
                {
                    "type": "message",
                    "conversation_id": conversation_id,
                    "content": result.content,
                    "actions": result.actions,
                    "tool_trace": result.tool_trace,
                    "model": result.model,
                    "steps": result.steps,
                    "usage": {
                        "tokens_in": result.tokens_in,
                        "tokens_out": result.tokens_out,
                        "cost_usd": result.cost_usd,
                    },
                }
            )
        except Exception:  # noqa: BLE001 — surface as an SSE error, never a hung stream
            logger.exception("chat stream failed")
            await queue.put({"type": "error", "message": "Sorry — that turn failed. Please try again."})
        finally:
            await queue.put(None)

    task = asyncio.create_task(produce())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield _sse(event)
            if await disconnect_check():
                break
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@router.post("/api/v1/chat")
@limiter.limit(_get_tier_limit)
async def chat(request: Request, body: ChatRequest, merchant: Merchant = Depends(verify_api_key)) -> StreamingResponse:
    conversation_id = _validate_conversation_id(body.conversation_id) or uuid.uuid4().hex
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty")
    if len(message) > settings.chat_max_input_chars:
        raise HTTPException(
            status_code=400,
            detail=f"Message exceeds {settings.chat_max_input_chars} characters",
        )

    user_id = _resolve_user_id(request)
    await save_message(
        merchant_id=merchant.id,
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=message,
    )

    stream = _chat_event_stream(
        merchant_id=merchant.id,
        conversation_id=conversation_id,
        user_id=user_id,
        message=message,
        disconnect_check=request.is_disconnected,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _new_conversation_id() -> str:
    return uuid.uuid4().hex


@router.get("/api/v1/chat/history")
async def chat_history(
    conversation_id: str = Query(..., min_length=1, max_length=64),
    limit: int = Query(default=200, ge=1, le=500),
    merchant: Merchant = Depends(verify_api_key),
) -> dict[str, Any]:
    _validate_conversation_id(conversation_id)
    messages = await load_messages(merchant.id, conversation_id, limit=limit)
    return {"conversation_id": conversation_id, "messages": messages}


@router.get("/api/v1/chat/conversations")
async def chat_conversations(merchant: Merchant = Depends(verify_api_key)) -> dict[str, Any]:
    return {"conversations": await list_conversations(merchant.id)}


@router.post("/api/v1/chat/actions/{action_id}/confirm")
async def chat_action_confirm(
    request: Request,
    action_id: str,
    body: ActionRequest,
    merchant: Merchant = Depends(verify_api_key),
) -> dict[str, Any]:
    _validate_conversation_id(body.conversation_id)
    try:
        return await confirm_action(
            merchant_id=merchant.id,
            conversation_id=body.conversation_id,
            action_id=action_id,
            actor=_resolve_user_id(request),
        )
    except ActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/api/v1/chat/actions/{action_id}/cancel")
async def chat_action_cancel(
    request: Request,
    action_id: str,
    body: ActionRequest,
    merchant: Merchant = Depends(verify_api_key),
) -> dict[str, Any]:
    _validate_conversation_id(body.conversation_id)
    try:
        return await cancel_action(
            merchant_id=merchant.id,
            conversation_id=body.conversation_id,
            action_id=action_id,
            actor=_resolve_user_id(request),
        )
    except ActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

"""Chat API tests: SSE streaming, validation, history, and action confirmation."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import agent.chat.agent as chat_agent_mod
import api.routes.chat as chat_route
import api.routes.purchase_orders as po_route
from agent.chat import actions as actions_mod
from agent.models import ChatMessage, POStatus
from shared.llm_client import LLMToolResult, StreamEvent, ToolCall


class FakeLLM:
    model = "fake-model"

    def __init__(self, text: str = "You have 12 widgets in stock.", tool_calls: list[ToolCall] | None = None):
        self.text = text
        self.tool_calls = tool_calls or []
        self.calls: list[list[dict[str, Any]]] = []

    async def call_stream(self, messages: list[dict[str, Any]], tools: Any = None) -> Any:
        self.calls.append(messages)
        yield StreamEvent(kind="delta", text=self.text)
        yield StreamEvent(
            kind="final",
            result=LLMToolResult(
                text=self.text,
                model=self.model,
                input_tokens=7,
                output_tokens=3,
                cost_usd=0.002,
                tool_calls=self.tool_calls,
            ),
        )


def _request(method: str = "POST", path: str = "/api/v1/chat") -> Request:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 4242),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope, receive=receive, send=lambda message: None)


def _parse_sse(frames: list[str]) -> list[dict[str, Any]]:
    events = []
    for frame in frames:
        assert frame.startswith("data: ")
        assert frame.endswith("\n\n")
        events.append(json.loads(frame[len("data: ") : -2]))
    return events


async def _collect(response: Any) -> list[dict[str, Any]]:
    frames: list[str] = []
    async for chunk in response.body_iterator:
        frames.append(chunk)
    return _parse_sse(frames)


@pytest.fixture(autouse=True)
def _agent_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the turn out of the real DB/LLM usage tables."""

    async def no_skip(node_name: str, prompt: str | None = None) -> bool:
        return False

    async def noop_log(node_name: str, response: str | None, prompt: str | None = None) -> None:
        return None

    monkeypatch.setattr(chat_agent_mod, "should_skip_llm_call", no_skip)
    monkeypatch.setattr(chat_agent_mod, "log_llm_call", noop_log)


@pytest.fixture
def no_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_route.limiter, "enabled", False)


@pytest.mark.asyncio
async def test_chat_post_streams_sse_turn(monkeypatch: pytest.MonkeyPatch, no_rate_limit: None) -> None:
    fake_llm = FakeLLM()
    monkeypatch.setattr(chat_route, "get_chat_llm", lambda: fake_llm)
    monkeypatch.setattr(chat_route, "load_history", AsyncMock(return_value=[]))
    saved: list[dict[str, Any]] = []

    async def fake_save(**kwargs: Any) -> int:
        saved.append(kwargs)
        return len(saved)

    monkeypatch.setattr(chat_route, "save_message", fake_save)

    response = await chat_route.chat(
        _request(),
        chat_route.ChatRequest(message="how many widgets?"),
        merchant=SimpleNamespace(id=0),
    )

    assert response.media_type == "text/event-stream"
    assert response.headers["X-Accel-Buffering"] == "no"

    events = await _collect(response)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "start"
    assert "delta" in kinds
    assert kinds[-1] == "message"

    final = events[-1]
    assert final["content"] == "You have 12 widgets in stock."
    assert final["actions"] == []
    assert final["usage"]["tokens_in"] == 7
    assert final["conversation_id"]

    # User prompt persisted first, assistant reply second, same conversation.
    assert [s["role"] for s in saved] == ["user", "assistant"]
    assert saved[0]["content"] == "how many widgets?"
    assert saved[1]["content"] == "You have 12 widgets in stock."
    assert saved[0]["conversation_id"] == saved[1]["conversation_id"]
    assert saved[1]["model"] == "fake-model"


@pytest.mark.asyncio
async def test_chat_reuses_supplied_conversation_id(monkeypatch: pytest.MonkeyPatch, no_rate_limit: None) -> None:
    monkeypatch.setattr(chat_route, "get_chat_llm", lambda: FakeLLM())
    monkeypatch.setattr(chat_route, "load_history", AsyncMock(return_value=[]))
    saved: list[dict[str, Any]] = []

    async def fake_save(**kwargs: Any) -> int:
        saved.append(kwargs)
        return 1

    monkeypatch.setattr(chat_route, "save_message", fake_save)

    response = await chat_route.chat(
        _request(),
        chat_route.ChatRequest(message="hi", conversation_id="conv-abc_123"),
        merchant=SimpleNamespace(id=7),
    )
    events = await _collect(response)
    assert events[-1]["conversation_id"] == "conv-abc_123"
    assert all(s["conversation_id"] == "conv-abc_123" for s in saved)
    assert all(s["merchant_id"] == 7 for s in saved)


@pytest.mark.asyncio
async def test_chat_rejects_empty_message(no_rate_limit: None) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await chat_route.chat(_request(), chat_route.ChatRequest(message="   "), merchant=SimpleNamespace(id=0))
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_chat_rejects_oversized_message(monkeypatch: pytest.MonkeyPatch, no_rate_limit: None) -> None:
    long_message = "x" * (chat_route.settings.chat_max_input_chars + 1)
    with pytest.raises(HTTPException) as excinfo:
        await chat_route.chat(_request(), chat_route.ChatRequest(message=long_message), merchant=SimpleNamespace(id=0))
    assert excinfo.value.status_code == 400
    assert str(chat_route.settings.chat_max_input_chars) in excinfo.value.detail


@pytest.mark.asyncio
async def test_chat_rejects_malformed_conversation_id(no_rate_limit: None) -> None:
    with pytest.raises(HTTPException) as excinfo:
        await chat_route.chat(
            _request(),
            chat_route.ChatRequest(message="hi", conversation_id="not valid!"),
            merchant=SimpleNamespace(id=0),
        )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_history_endpoint_returns_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"id": 1, "role": "user", "content": "hi"}]
    monkeypatch.setattr(chat_route, "load_messages", AsyncMock(return_value=rows))

    result = await chat_route.chat_history(conversation_id="conv-1", merchant=SimpleNamespace(id=3))

    assert result["conversation_id"] == "conv-1"
    assert result["messages"] == rows


@pytest.mark.asyncio
async def test_conversations_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"conversation_id": "a", "message_count": 4}]
    monkeypatch.setattr(chat_route, "list_conversations", AsyncMock(return_value=rows))

    result = await chat_route.chat_conversations(merchant=SimpleNamespace(id=3))

    assert result["conversations"] == rows


class FakeActionsSession:
    def __init__(self, messages: list[ChatMessage]):
        self.messages = messages
        self.added: list[Any] = []
        self.commits = 0
        self.persisted: list[Any] = []

    async def __aenter__(self) -> FakeActionsSession:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    async def execute(self, stmt: Any) -> Any:
        try:
            raw_params: dict[str, Any] = dict(stmt.compile().params)
        except Exception:  # noqa: BLE001 — fall back to unfiltered rows
            raw_params = {}
        # Bind keys are suffixed (conversation_id_1) — normalize to column names.
        params = {re.sub(r"_\d+$", "", k): v for k, v in raw_params.items()}
        rows = self.messages
        if "conversation_id" in params:
            rows = [m for m in rows if m.conversation_id == params["conversation_id"]]
        if "merchant_id" in params:
            rows = [m for m in rows if m.merchant_id == params["merchant_id"]]

        class Result:
            def scalars(self_inner) -> Any:
                return self_inner

            def all(self_inner) -> list[ChatMessage]:
                return rows

        return Result()

    async def get(self, model: Any, pk: Any) -> ChatMessage | None:
        return self.messages[0] if self.messages else None

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj: Any) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = 4242

    def add(self, obj: Any) -> None:
        self.added.append(obj)


def _action_message(action: dict[str, Any], merchant_id: int = 0) -> ChatMessage:
    return ChatMessage(
        id=5,
        merchant_id=merchant_id,
        conversation_id="conv-1",
        role="assistant",
        content="Drafted a PO for you.",
        actions=[action],
    )


def _pending_action(**overrides: Any) -> dict[str, Any]:
    action: dict[str, Any] = {
        "id": "act-1",
        "tool": "draft_purchase_order",
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
        "params": {
            "sku_id": 11,
            "sku_code": "WID-1",
            "quantity": 30,
            "unit_cost": 2.5,
            "total_cost": 75.0,
            "supplier_id": 2,
            "reasoning": "chat draft",
        },
    }
    action.update(overrides)
    return action


def _install_actions(
    monkeypatch: pytest.MonkeyPatch, action: dict[str, Any], merchant_id: int = 0
) -> FakeActionsSession:
    session = FakeActionsSession([_action_message(action, merchant_id=merchant_id)])
    monkeypatch.setattr(actions_mod, "async_session_factory", lambda: session)
    monkeypatch.setattr(actions_mod, "log_audit_event", AsyncMock())
    return session


@pytest.mark.asyncio
async def test_confirm_creates_pending_approval_po(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _install_actions(monkeypatch, _pending_action())

    result = await actions_mod.confirm_action(
        merchant_id=0, conversation_id="conv-1", action_id="act-1", actor="owner@example.com"
    )

    assert result["status"] == "confirmed"
    assert result["po_status"] == "pending_approval"

    created = session.added[0]
    assert created.status == POStatus.pending_approval
    assert created.quantity == 30
    assert created.total_cost == 75.0
    assert created.approved_at is None
    assert created.merchant_id is None  # demo merchant id 0 has no FK row
    assert session.commits >= 1
    # Action state is persisted back onto the assistant message.
    assert session.messages[0].actions[0]["status"] == "confirmed"
    assert session.messages[0].actions[0]["po_id"] == 4242


@pytest.mark.asyncio
async def test_confirm_never_auto_approves_and_audits(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_actions(monkeypatch, _pending_action(), merchant_id=5)

    await actions_mod.confirm_action(merchant_id=5, conversation_id="conv-1", action_id="act-1")

    assert actions_mod.log_audit_event.await_count == 1  # type: ignore[attr-defined]
    kwargs = actions_mod.log_audit_event.await_args.kwargs  # type: ignore[attr-defined]
    assert kwargs["action"] == "chat_action_confirmed"
    assert kwargs["target_type"] == "purchase_order"
    assert kwargs["merchant_id"] == 5


@pytest.mark.asyncio
async def test_confirm_expired_action_returns_410(monkeypatch: pytest.MonkeyPatch) -> None:
    expired = _pending_action(expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat())
    session = _install_actions(monkeypatch, expired)

    with pytest.raises(actions_mod.ActionExpired) as excinfo:
        await actions_mod.confirm_action(merchant_id=0, conversation_id="conv-1", action_id="act-1")

    assert excinfo.value.status_code == 410
    assert session.added == []
    assert session.messages[0].actions[0]["status"] == "expired"


@pytest.mark.asyncio
async def test_confirm_twice_conflicts(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_actions(monkeypatch, _pending_action(status="confirmed", po_id=99))

    with pytest.raises(actions_mod.ActionConflict) as excinfo:
        await actions_mod.confirm_action(merchant_id=0, conversation_id="conv-1", action_id="act-1")

    assert excinfo.value.status_code == 409


@pytest.mark.asyncio
async def test_confirm_wrong_conversation_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_actions(monkeypatch, _pending_action())

    with pytest.raises(actions_mod.ActionNotFound) as excinfo:
        await actions_mod.confirm_action(merchant_id=0, conversation_id="other-conv", action_id="act-1")

    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_cancel_marks_action_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _install_actions(monkeypatch, _pending_action())

    result = await actions_mod.cancel_action(
        merchant_id=0, conversation_id="conv-1", action_id="act-1", actor="owner@example.com"
    )

    assert result["status"] == "cancelled"
    assert session.messages[0].actions[0]["status"] == "cancelled"
    assert session.added == []


@pytest.mark.asyncio
async def test_route_confirm_translates_action_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_actions(monkeypatch, _pending_action(expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat()))

    with pytest.raises(HTTPException) as excinfo:
        await chat_route.chat_action_confirm(
            _request(method="POST", path="/api/v1/chat/actions/act-1/confirm"),
            action_id="act-1",
            body=chat_route.ActionRequest(conversation_id="conv-1"),
            merchant=SimpleNamespace(id=0),
        )
    assert excinfo.value.status_code == 410


@pytest.mark.asyncio
async def test_approve_without_thread_skips_graph_resume(monkeypatch: pytest.MonkeyPatch) -> None:
    po = SimpleNamespace(id=7, status=POStatus.pending_approval, quantity=5)
    updates: dict[str, Any] = {}

    async def fake_resolve(po_id: int) -> tuple[Any, str | None]:
        return po, None

    async def fake_update(po_id: int, status: POStatus, **extra: Any) -> None:
        updates.update(status=status, **extra)

    async def fake_resume(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("graph resume must not run without a thread")

    monkeypatch.setattr(po_route, "_resolve_po", fake_resolve)
    monkeypatch.setattr(po_route, "_update_po_status", fake_update)
    monkeypatch.setattr(po_route, "_resume_graph", fake_resume)
    monkeypatch.setattr(po_route, "_mark_edited_if_changed", AsyncMock())
    monkeypatch.setattr(po_route, "log_audit_event", AsyncMock())

    result = await po_route._approve_po_impl(None, 7, "tester", None, merchant_id=0)  # type: ignore[arg-type]

    assert result["status"] == "approved"
    assert updates["status"] == POStatus.approved
    assert updates["approved_by"] == "tester"


@pytest.mark.asyncio
async def test_approve_with_thread_still_resumes_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    po = SimpleNamespace(id=7, status=POStatus.pending_approval, quantity=5)
    resumed: list[tuple[Any, ...]] = []

    async def fake_resolve(po_id: int) -> tuple[Any, str | None]:
        return po, "thread-1"

    async def fake_update(po_id: int, status: POStatus, **extra: Any) -> None:
        po.status = status

    async def fake_resume(request: Any, thread_id: str, resume_value: str) -> None:
        resumed.append((thread_id, resume_value))

    monkeypatch.setattr(po_route, "_resolve_po", fake_resolve)
    monkeypatch.setattr(po_route, "_update_po_status", fake_update)
    monkeypatch.setattr(po_route, "_resume_graph", fake_resume)
    monkeypatch.setattr(po_route, "_mark_edited_if_changed", AsyncMock())
    monkeypatch.setattr(po_route, "log_audit_event", AsyncMock())

    await po_route._approve_po_impl(None, 7, "tester", None, merchant_id=0)  # type: ignore[arg-type]

    assert resumed == [("thread-1", "approve")]

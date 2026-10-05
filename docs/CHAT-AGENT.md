# Chat Agent — Natural-Language Interface

The inventory agent can be driven through a streaming chat API: ask questions in plain
English, watch the LangGraph tool-calling loop work against live Postgres data, and
approve every write action explicitly before anything changes.

```
User ──POST /api/v1/chat──▶ SSE stream (start · delta · tool · message · error)
        │                        │
        │                        └─ LangGraph: assistant ⇄ tools (read-only) loop
        │                              └─ draft_purchase_order → pending action (not executed)
        └──POST /api/v1/chat/actions/{id}/confirm ──▶ creates status=pending_approval PO
                                /cancel             ──▶ discards the proposal
```

## Endpoints

All endpoints require API-key auth (`X-API-Key` / `Authorization: Bearer`), are
merchant-scoped, and the chat POST is rate-limited per the standard tier limits.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/chat` | Run one turn; streams SSE. Body: `{message, conversation_id?}`. New conversations are created implicitly (UUID) when `conversation_id` is omitted. |
| `GET` | `/api/v1/chat/history?conversation_id=&limit=` | Replay stored messages for a conversation (default limit 200, max 500). |
| `GET` | `/api/v1/chat/conversations` | Recent conversations (id, preview, message count, updated_at). |
| `POST` | `/api/v1/chat/actions/{action_id}/confirm` | Confirm a pending action. Body: `{conversation_id}`. |
| `POST` | `/api/v1/chat/actions/{action_id}/cancel` | Cancel a pending action. Body: `{conversation_id}`. |

### SSE events (`POST /api/v1/chat`)

Each frame is `data: {json}\n\n`:

| `type` | Payload | Meaning |
| --- | --- | --- |
| `start` | `{model}` | Turn started. |
| `delta` | `{text}` | Incremental assistant text (streamed from the LLM). |
| `tool` | `{name, phase: started\|finished\|failed, ok, summary, elapsed_ms, mutating}` | A tool call began/finished. |
| `message` | `{conversation_id, content, actions, tool_trace, model, steps, usage:{tokens_in, tokens_out, cost_usd}}` | Final assembled message; both `content` and `delta` frames carry the answer (use one, not both). |
| `error` | `{message}` | Turn failed — the stream still terminates cleanly. |

Limits: input rejected over `CHAT_MAX_INPUT_CHARS` (default 4000); at most
`CHAT_MAX_STEPS` (default 6) LangGraph iterations per turn; `conversation_id` must match
`^[A-Za-z0-9_-]{1,64}$`.

## Tools

Read-only tools execute directly against Postgres during the loop:

- `get_inventory_status` — on-hand, reorder point, stockout risk per SKU.
- `get_sku_details` — single SKU: supplier, lead time, costs, safety stock.
- `lookup_supplier` — supplier record for a SKU or supplier id.
- `forecast_demand` — engine forecast (baseline or ensemble) with history.
- `calculate_reorder_quantity` — suggested order quantity + rationale.
- `forecast_error_summary` — model accuracy (MAPE/bias) over recent windows.

`draft_purchase_order` is the only mutating tool and is **never executed by the agent**.
It returns a pending action attached to the final `message`:

```json
{
  "id": "act_...", "tool": "draft_purchase_order", "status": "pending",
  "expires_at": "2026-10-04T10:15:00+00:00",
  "params": {"sku_id": 7, "sku_code": "SKU-1001", "quantity": 50,
             "unit_cost": 10, "total_cost": 500, "reasoning": "..."}
}
```

## Safety rails

- **Human confirmation**: `confirm` always creates the PO with `status=pending_approval`
  (never `approved`); the existing PO approval workflow is the second gate. Audit events
  `chat_action_confirmed` / `chat_action_cancelled` record the actor.
- **Expiry**: actions expire after `CHAT_ACTION_TTL_MINUTES` (default 15). Confirming or
  cancelling an expired action returns `410` and persists `status=expired`; a
  confirmed/cancelled action returns `409`.
- **Prompt-injection defense**: user text is sanitized (control characters stripped,
  instruction-delimiter fencing) at send time inside `LLMClient` — history is stored raw.
- **Isolation**: every query filters by the authenticated merchant (demo merchant `0` is
  unscoped); conversation ids are validated and merchant-checked on every read/write.
- **Budget**: turn-level token/cost budget fallbacks answer without tools when exceeded;
  `should_skip_llm_call`/`log_llm_call` cost controls wrap every call (metric:
  `chat_tool_calls_total{tool,result}`).

## Frontend

`/chat` (Chat page) streams over `fetch` + `ReadableStream`, renders tool chips as they
run, and shows pending actions as amber Confirm/Cancel cards. Conversations can be
reopened from the header selector.

## Configuration

| Env var | Default | Meaning |
| --- | --- | --- |
| `CHAT_MAX_STEPS` | `6` | Max LangGraph iterations per turn. |
| `CHAT_MAX_INPUT_CHARS` | `4000` | Reject longer user messages (`400`). |
| `CHAT_HISTORY_MESSAGES` | `20` | Prior messages replayed as LLM history. |
| `CHAT_ACTION_TTL_MINUTES` | `15` | Pending-action lifetime. |

## Data model

`chat_messages` (migration `017_chat_messages`): `id, merchant_id, conversation_id,
role (user|assistant), content, actions (JSONB), tool_trace (JSONB), user_id, model,
tokens_in, tokens_out, cost_usd, created_at`, indexed by
`(merchant_id, conversation_id, created_at)`.

## Tests

- `tests/test_chat_tools.py` — tool behavior against fake sessions.
- `tests/test_chat_agent.py` — LangGraph loop, SSE events, safety rails, fallbacks.
- `tests/test_chat_api.py` — SSE endpoint, validation, history, confirm/cancel lifecycle,
  PO approval without a graph thread.
- `inventory-frontend/src/pages/Chat.test.tsx` — streaming UI, action cards, errors.

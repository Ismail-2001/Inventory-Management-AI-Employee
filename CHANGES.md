# Backend fixes — July 2026

**Reconciliation note:** these fixes were originally built against the repo state before commit `b978e43` (OpenCode's `AsyncPostgresSaver` fix to `agent/db.py`). Before packaging, I pulled the live repo again, confirmed OpenCode's commit only touched `agent/db.py`, and merged my 7 fixes on top of that fresh state rather than the older one — so nothing from either change set is lost. Re-verified compile + all 22 tests + a combined import of every touched module (mine and OpenCode's) together.

## 8. `psycopg_pool` missing from requirements.txt
**File:** `requirements.txt`
OpenCode's `agent/db.py` fix imports `from psycopg_pool import ConnectionPool`, but `requirements.txt` only listed `psycopg>=3.2.0` — the pool extra isn't bundled by default. A fresh `pip install -r requirements.txt` would have installed cleanly and then crashed on import. Changed to `psycopg[binary,pool]>=3.2.0`. Found while reconciling, not part of the original 7.

Seven real gaps found during a full read-through of the actual repo, fixed and verified. All 22 pure-logic tests (`test_signing`, `test_forecast`, `test_risk`, `test_ordering`) still pass after these changes.

## 1. Multi-tenancy — `merchant_id` added
**Files:** `alembic/versions/004_multi_tenant_scoping.py`, `agent/models.py`
`skus` and `purchase_orders` had no `merchant_id` column — the system was effectively single-store. Added nullable FK columns + indexes + a backfill for existing rows. `sales_history`, `forecasts`, `risk_alerts` deliberately left un-duplicated — they're scoped indirectly via `sku.merchant_id` since every real query already joins through `sku_id`.
**Not done (follow-up, bigger than a gap-fix):** the Shopify sync functions still assume one global store via `settings.shopify_store_domain`. Looping sync per-merchant with per-merchant credentials is real Phase 4 work, not included here.

## 2. RBAC now enforced on PO approval
**File:** `api/routes/purchase_orders.py`
`require_role()` existed in `agent/auth.py` but wasn't applied anywhere. Added `Depends(require_role("owner", "staff"))` to `/po/{id}/approve` and `/po/{id}/reject`. A `viewer` role can no longer approve spend with a valid API key.
Note: the signed-link `/po/action` route (email approval) intentionally has no role check — the signed token itself is the authorization there, by design.

## 3. Startup config validation now actually runs
**File:** `api/main.py`
`settings.validate_required()` was defined but never called. Now runs in the FastAPI `startup` event — missing `SHOPIFY_ADMIN_API_TOKEN` etc. now fails the app at boot instead of starting silently broken. Verified: raises `Missing required settings: SHOPIFY_ADMIN_API_TOKEN. Check your .env file.`

## 4. Demo API key gated by environment
**Files:** `agent/config.py`, `agent/auth.py`
Added `ENVIRONMENT` and `ALLOW_DEMO_KEY` settings. The `demo-key-2024` bypass now only works when `ALLOW_DEMO_KEY=true`, which defaults to `false` when `ENVIRONMENT=production`. Verified via direct import test.

## 5. CORS wildcard removed
**Files:** `agent/config.py`, `api/main.py`
`allow_origins=["*"]` combined with `allow_credentials=True` is an invalid/unsafe combination browsers actually reject. Replaced with `ALLOWED_ORIGINS` env var (comma-separated), defaulting to localhost dev origins.

## 6. Legacy endpoints marked deprecated, not deleted
**File:** `api/main.py`
`/api/v1/analyze`, `/bulk`, `/forecast` (the original single-shot demo) still coexisted with the real LangGraph pipeline (`/run-sync`, `/po/*`, `/webhooks/*`). Deleting them would have broken `tests/test_agent.py`, which still exercises the underlying module. Marked `deprecated=True` (shows in OpenAPI docs) with a docstring pointing to `/run-sync` as the real path. Actual removal is a follow-up once `test_agent.py` is retired or rewritten.

## 7. Webhooks now do targeted syncs, not full catalog resyncs
**Files:** `agent/shopify_sync.py`, `agent/webhooks.py`
All three webhook handlers previously called `sync_products_and_inventory()` — a full catalog pull — on every single event. At scale (5,000+ SKU catalogs) this burns the GraphQL rate limit fast.
- `inventory_levels/update` → new `sync_single_variant()`, queries exactly one `InventoryItem` by the id Shopify actually sends (not a variant id — these are different gid types in Shopify's model, a subtlety worth flagging since it's an easy mistake).
- `orders/create` → writes directly into `sales_history` from the webhook payload's line items (Shopify already sends quantity/SKU in the payload — no reason to call back out to the API at all).
- `products/update` → upserts directly from the payload's `variants` array (also already present in what Shopify sends) — zero extra API calls.

## Verified, not just written
- All 7 changed/added files pass `python3 -m py_compile`
- All 22 existing pure-logic tests still pass
- `agent.models`, `agent.config`, `agent.auth`, `agent.webhooks`, `agent.shopify_sync` all import cleanly
- `validate_required()` confirmed to actually raise on missing config
- `allow_demo_key` confirmed to resolve `False` under `ENVIRONMENT=production`

## 9. Signed-URL approval endpoint fixed (crashed on every call)
**Files:** `api/routes/purchase_orders.py:178`
`po_action_via_token` was missing the `request: Request` parameter, causing `NameError` on every Slack link click. Fixed by adding `request: Request = Depends()`.

## 10. Webhook sales history no longer overwrites same-day records
**File:** `agent/webhooks.py:119-121`
Changed `set_={"units_sold": stmt.excluded.units_sold}` (overwrite) to `set_={"units_sold": SalesHistory.units_sold + stmt.excluded.units_sold}` (accumulate). Without this fix, two orders for the same SKU on the same day would silently erase each other.

## 11. `thread_id` now attached to POs during graph execution
**File:** `agent/nodes/po_draft_node.py` (PurchaseOrder constructor)
Added `thread_id=state.get("thread_id")` to the PO creation. Previously, `thread_id` was set in a post-hoc DB update in `run_sync` — a race condition where approvals arriving between graph completion and DB update would fail with "No active approval thread."

## 12. Slack notification failure no longer crashes the pipeline
**File:** `agent/nodes/notify_node.py` (notify_pending_node)
Wrapped the Slack HTTP POST in a try/except. A Slack outage or network error now logs a warning and continues — it does not abort the entire graph run.

## 13. Demo infrastructure added
**Files:** `setup_demo.sh`, `seed_demo_data.py`, `demo_script.md` (new)
- `setup_demo.sh` — one-command demo environment setup (Docker + migrations + data seed)
- `seed_demo_data.py` — populates 10 realistic US DTC SKUs with 90-day sales history
- `demo_script.md` — 15-minute client presentation script with live commands

## 14. `run_sync.py` cleaned up
**File:** `api/routes/run_sync.py`
Removed post-hoc DB update for `thread_id` — POs now carry `thread_id` from graph execution (see #11). Removed now-unused imports (`PurchaseOrder`, `async_session_factory`). Added docstring.

## 15. README directory tree updated
**File:** `README.md` (project tree section)
Added `setup_demo.sh`, `seed_demo_data.py`, and `demo_script.md` to the full project tree listing so new contributors and reviewers can discover the demo infrastructure files.

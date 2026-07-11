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

## Still open (not silently claimed as done)
- Full multi-tenant Shopify sync loop (per-merchant credentials, scheduled per merchant)
- Row-Level Security on the new `merchant_id` columns (schema is ready for it — Phase 4 Step 5 in the roadmap doc)
- `test_agent.py` / legacy `inventory_agent.py` retirement

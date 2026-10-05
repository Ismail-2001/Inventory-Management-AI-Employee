# ROI & Performance Dashboard

The dashboard (default landing page at `/`) answers one question: **is the AI Employee paying for
itself?** Every tile carries an info popover with its definition, this document is the full
methodology behind those numbers, and every formula is also visible in the page's
"How we calculate these numbers" panel.

- **API**: `GET /api/v1/roi?days=30` (or `GET /api/v1/roi?start=YYYY-MM-DD&end=YYYY-MM-DD`)
- **Backend**: `agent/roi.py` (`calculate_roi_report`) + `api/routes/roi.py`
- **Frontend**: `inventory-frontend/src/pages/Dashboard.tsx`, tooltip component `MetricHelp.tsx`
- **Tests**: `tests/test_roi.py` (aggregations + route), `src/pages/Dashboard.test.tsx`,
  `inventory-frontend/e2e/dashboard.spec.ts`

## Date ranges

| Control | Query | Constraints |
|---|---|---|
| Preset `7d` / `30d` / `90d` | `?days=N` | 1–365 (400 outside that range) |
| Custom | `?start=…&end=…` | Inclusive window, at most 366 days |

The window is applied with **warehouse-local naive timestamps** derived from the requested dates
and all timestamps are compared as UTC-aware values, so day boundaries do not depend on the
caller's timezone. Default when no range is given: the last 30 days.

## Value & efficiency

### Value generated (USD)

```
value = stockout revenue protected + capital freed
```

- **Stockout revenue protected** — see *Stockouts avoided* below: `units × unit_cost` summed over
  qualifying PO outcomes, multiplied by `ROI_REVENUE_MULTIPLIER` (default **2.0**). The multiplier
  represents gross-margin/markup on the revenue those units would have generated; set it to your
  real multiplier for a tighter number.
- **Capital freed** — *Excess avoided* at cost: quantities trimmed from drafted POs before
  approval plus POs rejected outright, each valued at `quantity × unit_cost`.

### LLM cost (USD)

```
cost = Σ llm_usage.estimated_cost + Σ chat_messages.cost_usd (role = assistant)
```

Windowed on `llm_usage.created_at` / `chat_messages.created_at`. This includes pipeline nodes
(forecast reasoning, PO drafting, weekly reflection, chat replies). Token pricing is the table
price recorded by `shared/llm_client.py` at call time.

> **Caveat:** LLM usage rows are tracked globally, not per merchant — the cost shown on a
> merchant-scoped dashboard includes the whole deployment's spend, while value is scoped to the
> merchant. This makes the ratio conservative for multi-tenant deployments.

### ROI multiple

```
roi_multiple = value_generated ÷ llm_cost          (rounded to 1 decimal)
```

Rendered as `—` when `llm_cost = 0` (no measured token spend in the window — value was produced at
no recorded cost; dividing by zero would be meaningless).

### Hours saved

```
hours = decided_POs × ROI_MANUAL_PO_MINUTES ÷ 60    (default 12 minutes per PO)
```

`decided_POs` are POs created in the window that reached `approved` or `rejected`.
`ROI_MANUAL_PO_MINUTES` encodes the manual work each decision replaces: check stock, research the
supplier, draft the order, chase the approval. Set it to your own time study.

## Operational impact

### Stockouts avoided

Counts evaluated **PO outcomes** where:

1. `expected_stockout_prevented = true` — pre-delivery demand exceeded on-hand stock (a stockout
   was imminent before the PO landed), **and**
2. `actual_stockout_occurred = false` — no stockout actually happened.

```
units  = Σ quantity                      (on qualifying POs)
revenue = Σ quantity × unit_cost × ROI_REVENUE_MULTIPLIER
```

`events` is the number of qualifying outcomes. Outcomes still in `pending` evaluation are neither
counted nor penalised.

### Excess avoided

```
units   = Σ (original_quantity − quantity) for POs edited before approval (only when reduced)
        + quantity for POs rejected
capital = Σ units × unit_cost
```

Both subtotals are reported (`trimmed_pos`, `rejected_pos`) so operators can see how much was
trimmed versus declined outright. This is inventory commitment that never happened.

### PO acceptance & time to decision

Applies to POs **created** in the window that reached a decision:

- `accepted = approved`, `rejected`, `decided = accepted + rejected`
- `acceptance_rate_pct = accepted ÷ decided × 100`
- `accepted_as_is` vs `edited_then_approved` splits approvals by whether the operator changed the
  drafted quantity before approving (`edited_before_approval`)
- `avg_hours_to_decision` — mean hours from PO creation to the recorded decision. Approvals use the
  `audit_log` `po.approve` event timestamp (falling back to `approved_at` when no audit event
  exists, e.g. seeded data); rejections use `po.reject`. Decisions without a usable timestamp are
  excluded and reported as `decisions_with_timestamp`.

### Forecast accuracy

All figures come from persisted `forecasts` rows created in the window:

- `backtest_wmape` / `backtest_bias` are stored as **fractions** (0.15 = 15%) and reported as
  percentages.
- **Ensemble** = rows with `model_version = ensemble_v2`; **Baseline** = `exp_smoothing_v1`.
- `wmape_improvement_pct = (baseline − ensemble) ÷ baseline × 100` — positive means the ensemble is
  more accurate.
- **Forecast Error** (independent check) = mean `forecast_error_pct` over evaluated PO outcomes in
  the window — actual demand vs what the forecast predicted for the ordered horizon. It is an
  aggregate over `po_outcomes`, not derived from `forecasts`.
- The daily trend line shows each engine's wMAPE per day (most recent 60 days), so operators can
  see whether the new engine stays ahead of the baseline over time.

## Health

### At-risk SKUs

A **live snapshot, not windowed**: unresolved (`status = open`) `risk_alerts` with level `critical`
or `warning`, deduplicated to the latest alert per SKU, top 8 by severity/recency. It answers
"what needs attention right now", independent of the selected range.

### Forecast coverage & confidence

- `coverage_pct` = forecasts in the window persisted with a p10–p90 interval ÷ all forecasts in the
  window.
- Confidence buckets compare the interval width against demand:
  `width = (p90 − p10) ÷ max(p50, 0.01)` → **tight** `≤ 0.5`, **typical** `≤ 1.0`, **wide** `> 1.0`.
  Wide buckets mean the engine is uncertain — treat those forecasts as directional only.

### Engine health (fallback rate)

```
fallback_rate_pct = forecasts with model_meta.fallback_used ÷ total_forecasts × 100
```

A fallback is a run where the ensemble raised an error and the legacy engine served instead.
Runs that **timed out write no row at all**, so they are excluded from both numerator and
denominator (a timeout therefore does not inflate or hide the fallback rate). The chips below the
rate show the model-version distribution for the window.

## Assumptions & configuration

| Variable | Default | Meaning |
|---|---|---|
| `ROI_REVENUE_MULTIPLIER` | `2.0` | Revenue markup applied to stockout-protected units |
| `ROI_MANUAL_PO_MINUTES` | `12` | Manual minutes replaced by each decided PO |

Both are read from `agent/config.py` and echoed inside the payload (`efficiency.assumptions`) so
the UI can state its assumptions inline.

## Reading empty windows

Zero-activity windows are not errors. The dashboard renders explicit empty states
(`No PO decisions yet`, `Not enough forecast data yet`, `All clear — no SKUs at risk`) and `—`
instead of fabricated zeros where a ratio or average would be meaningless (acceptance with no
decided POs, ROI with no cost, time-to-decision with no timestamps).

# Post-Flip Observation Window — 6 Oct to 20 Oct 2026

**Status: ACTIVE — Day 1 of 14.** Ensembles serves as the global default
(migration `018`, PR #52). This log is the running evidence record for the
observation window: short entries on every check, formal status notes at
Day 7 (~13 Oct) and Day 14 (~20 Oct), which are cross-posted to
[issue #51](https://github.com/Ismail-2001/Inventory-Management-AI-Employee/issues/51).

## Safety stance (this window)

- **No changes** to forecasting logic, model selection, or defaults unless a
  clear production problem appears (see decision rules below).
- Kill switch stays ready and tested: `FORECAST_ENGINE_OVERRIDE=exponential`
  (env, no redeploy — see [FORECAST-ENGINE-RUNBOOK.md](FORECAST-ENGINE-RUNBOOK.md)),
  plus per-merchant demotion via `POST /api/v1/forecast-engine`.
- Prefer observation and documentation over code changes. No new features.

## Signals and where to read them

| Signal | Source | Healthy | Investigate |
|---|---|---|---|
| Engine distribution | `SELECT id, forecast_engine FROM merchants` | all rows `ensemble` (unless deliberately overridden) | any row ≠ `ensemble` with no recorded decision |
| Served engine per forecast | `SELECT model_version, COUNT(*) FROM forecasts GROUP BY 1` | `ensemble_v2` for runs on the default | `exp_smoothing_v1` rows appearing without an override/merchant flag |
| Fallback rate | `forecasts` rows where `(model_meta->>'fallback_used') = 'true'`; `forecast_fallback_count{reason}` on `GET /metrics`; ROI endpoint `engine_fallback_rate` | 0, or explained | > 5% of rows in any 24 h window, or any `circuit_breaker` reason |
| Timeouts / breaker | `forecast_timeout_total`, `forecast_circuit_tripped` on `GET /metrics` | 0 | any non-zero |
| Accuracy | row-level `backtest_wmape` / `backtest_bias` trend per `model_version`; outcomes `forecast_error_pct` (also on `GET /api/v1/roi`) | stable vs Day-1 baseline | sustained worsening vs baseline |
| Engine used counters | `forecast_engine_used{engine,merchant}` on `GET /metrics` | `engine="ensemble"` only | any other engine while no override is set |
| Manual demotions / overrides | `audit_log` actions `forecast_engine_*`; `merchants.forecast_engine`; process env `FORECAST_ENGINE_OVERRIDE` | none | any change without a logged decision |
| Alert volume | Alert rules in `prometheus/rules.yml`: `ForecastCircuitBreakerTripped`, `EnsembleFallbackStorm`, `ForecastMapeRegression` | no firings | any firing — record and triage |
| Scheduler jobs (when `ENABLE_SCHEDULER=1`) | `daily_forecast_promotions` (24 h), `weekly_forecast_report` (Mon 08:30) | runs as configured | promotion/demotion events without review |

Notes on this environment: `/metrics` counters live in process memory (they
reset when the API restarts and only advance while a process runs); the
`forecasts`, `po_outcomes`, and `audit_log` tables are the durable record.
When the API stack is down, the DB signals above are authoritative.

## Cadence

1. **Every check (daily, max 48 h):** run the CHECKS block below, append a
   dated line to the log at the bottom of this file.
2. **Day 7 (~13 Oct)** and **Day 14 (~20 Oct):** write a status note in
   issue #51 covering stability, fallback frequency, unexpected behavior,
   and any merchant opt-outs.
3. **Day 14 final:** apply the decision rules, update this log, update
   [FORECAST-PROMOTION-MEMO.md](FORECAST-PROMOTION-MEMO.md) with online
   results, and set issue #51 to its final status per item.

## Check schedule (≤48 h gaps — this log is the single source of truth)

Every row is a planned touch: routine checks append a dated line below;
Day-7 and Day-14 also mirror a status note into issue #51. Issue comments
and the memo *reference* this log — they never carry evidence that is not
recorded here first.

| # | Planned | Type | Status |
|---|---|---|---|
| 1 | 6 Oct | Baseline + cadence confirmation | done (2 entries) |
| 2 | 8 Oct | Routine CHECKS | pending |
| 3 | 10 Oct | Routine CHECKS | pending |
| 4 | 12 Oct | Routine CHECKS | pending |
| 5 | 13 Oct | Routine CHECKS + **Day-7 note** (issue #51) | pending |
| 6 | 14 Oct | Routine CHECKS | pending |
| 7 | 16 Oct | Routine CHECKS | pending |
| 8 | 18 Oct | Routine CHECKS | pending |
| 9 | 20 Oct | Final CHECKS + **Day-14 note** (issue #51) | pending |

Mark rows done as checks are executed; gaps > 48 h must be explained in
the corresponding log entry.

## Decision rules (pre-registered — evidence, not vibes)

- **Critical → kill switch:** any `ForecastCircuitBreakerTripped` or
  `EnsembleFallbackStorm` alert, fallback share > 5% of rows in 24 h, or
  forecast failures blocking runs. Action: set
  `FORECAST_ENGINE_OVERRIDE=exponential`, triage root cause, fix as a small
  follow-up, only then remove the override.
- **Medium-tier coverage (0.51, p10–p90):** *acceptable at this window's end*
  if (a) no decision-quality issue is observed (risk/PO flow unchanged, no
  forecast alerts, outcomes not worse than baseline) and pooled coverage stays
  inside 0.75–0.90 when measurable; otherwise open a **soft, non-blocking**
  follow-up for low-volume interval calibration. Either way the note records
  which branch was taken and why.
- **Auto-demotion:** implement only if the window produces clear evidence —
  e.g. a merchant on `ensemble` showing `forecast_mape_ratio > 0.85`
  sustained across ≥ 2 checks with live data and no operator action taken.
  Otherwise close as **"not required at this time."**
- **Intermittent tier:** cannot be validated on the demo seed (no
  zero-inflated SKUs exist there). Re-scope to a future observation item that
  runs when real sparse/production history is available — not a window
  blocker.

## CHECKS (copy-paste)

```bash
# Durable signals (works without the API stack)
psql "$DATABASE_URL" -c "SELECT id, name, forecast_engine FROM merchants;"
psql "$DATABASE_URL" -c "SELECT model_version, COUNT(*), \
  COUNT(*) FILTER (WHERE (model_meta->>'fallback_used')='true') AS fallbacks, \
  MAX(created_at) FROM forecasts GROUP BY 1;"
psql "$DATABASE_URL" -c "SELECT ROUND(AVG(backtest_wmape)::numeric,4), \
  ROUND(AVG(backtest_bias)::numeric,4) FROM forecasts WHERE backtest_wmape IS NOT NULL;"
psql "$DATABASE_URL" -c "SELECT COUNT(*), ROUND(AVG(forecast_error_pct)::numeric,2) FROM po_outcomes;"
psql "$DATABASE_URL" -c "SELECT action, created_at FROM audit_log \
  WHERE action LIKE 'forecast%' ORDER BY created_at DESC LIMIT 10;"

# Live signals (only while the API is running)
curl -s localhost:8002/metrics | grep -E \
  'forecast_engine_used|forecast_fallback_count|forecast_timeout_total|forecast_circuit'
curl -s -H "x-api-key: $AGENT_API_KEY" localhost:8002/api/v1/forecast-engine
curl -s -H "x-api-key: $AGENT_API_KEY" "localhost:8002/api/v1/roi?days=7" | <engine fallback rate>

# Alert history since last check
gh api "repos/Ismail-2001/Inventory-Management-AI-Employee/actions/runs?branch=main" --jq '.workflow_runs[0:5]'
```

## Exit criteria

- [ ] 7–14 days of clean (or clearly understood) online behavior recorded below
- [ ] Day-7 status note posted to issue #51
- [ ] Day-14 status note posted to issue #51 with final per-item status
- [ ] Coverage decision and auto-demotion decision recorded per the rules above
- [ ] Promotion memo updated with online results
- [ ] Decision: "promotion confirmed" or "specific small follow-up required"

## Status note structures

### Day-7 note (~13 Oct) — post to issue #51, mirror in the log

> **Post-flip observation — Day 7 status (13 Oct 2026)**
>
> - **Cadence:** checks run on \<dates\> (≤48 h gaps: yes/no); log: this file
> - **Stability:** default still `ensemble`; merchants on `ensemble`: n/1;
>   no config/code drift; CI on `main` green for every push
> - **Fallback frequency:** rows since window start: n; `fallback_used`: n
>   (share); timeouts / circuit trips: n
> - **Accuracy signals:** row-level wMAPE/bias vs Day-1 baseline;
>   `po_outcomes` n + mean `forecast_error_pct` (or "no samples yet");
>   forecast alerts fired: none / \<list + triage\>
> - **Anomalies:** none / \<describe, root cause, whether a critical trigger
>   fired\>
> - **Merchant opt-outs:** none / \<list with audit-log refs\>
> - **Interim verdict:** stable / concern (+ follow-up)
> - **Rule status:** coverage rule — evidence so far; auto-demotion rule —
>   evidence so far; intermittent — re-scope confirmed

### Day-14 note (~20 Oct) — post to issue #51, mirror in the log

> **Post-flip observation — Day 14 status + verdict (20 Oct 2026)**
>
> - **Cadence:** checks run: n, gaps: none / \<reason\>
> - **Full-window behavior:** stability, fallback frequency (window totals),
>   anomalies, opt-outs
> - **Decision rules applied:**
>   - [ ] Critical triggers fired? (fallback > 5%/24 h, breaker, storm alert)
>         → if no: record "no code changes were warranted this window"
>   - [ ] **Medium coverage 0.51:** observed harm (alerts, risk/PO issues,
>         outcomes worse than baseline)? pooled coverage in 0.75–0.90?
>         → **ACCEPT** (record why) or **SOFT-FOLLOWUP** (open non-blocking
>         interval-calibration issue)
>   - [ ] **Auto-demotion:** sustained `forecast_mape_ratio > 0.85` across
>         ≥ 2 checks with live data? → **IMPLEMENT** (re-scope as follow-up)
>         or **CLOSE as "not required at this time"**
>   - [ ] **Intermittent:** → **RE-SCOPE** on #51: "requires real
>         sparse/production data — cannot be validated on demo seed"
> - **Memo updated** with online results (PR link)
> - **Verdict:** `promotion confirmed` **or** `specific small follow-up
>   required (list)` — exactly one, explicit
> - **Pilot readiness:** outstanding forecast blockers: none / list

---

## Status log

### Day 1 — 6 Oct 2026 (baseline)

**Configuration verified**
- `alembic_version = 018`; merchants: `1 Demo US Retailer → ensemble`
  (0 manual overrides, 0 demotions, `forecast_promoted_at = NULL` — promoted
  by the default flip, not by a gate run; expected).
- Kill-switch drill (settings only, nothing served): override
  `exponential` resolves `engine=exponential source=global_override`, then
  restored. Path works.

**Live smoke — first post-flip forecast rows through the real code path**
(resolve via `resolve_engine`, serve via `calculate_forecast`, engine
`ensemble` — forecast step only, no LLM downstream):

| SKU | tier | velocity | selected model | served | fallback | p50 | row wMAPE |
|---|---|---|---|---|---|---|---|
| 1 | medium | 2.59 u/d | `ses` | `ensemble_v2` | no | 4.71 | 0.93 |
| 2 | high | 30.58 u/d | `seasonal_holt` | `ensemble_v2` | no | 33.39 | 0.08 |
| 7 | medium | 3.40 u/d | `mean` | `ensemble_v2` | no | 3.03 | 0.49 |

Both velocity gates observed live: trend models excluded below 10 u/d
(medium SKUs got flat models), stockout imputation skipped
(`imputed_days = 0` below threshold). 3/3 rows `ensemble_v2`,
**0 fallbacks**.

**Activity counters at baseline**
- `forecasts` rows: 3 (all from this smoke, all `ensemble_v2`, 0 fallback);
  prior rows cleared by the test-suite DB reset — this is the true floor.
- `po_outcomes`: 0 rows — outcome-based accuracy (`forecast_error_pct`)
  has no samples yet; first PO deliveries are the trigger.
- `audit_log`: 0 forecast events in the last 14 d (no engine changes, no
  promotions, no demotions).
- Alert rules armed: `ForecastCircuitBreakerTripped`,
  `EnsembleFallbackStorm`, `ForecastMapeRegression` (> 0.85).
- Environment: API/Prometheus/Redis not currently running (Postgres only);
  `/metrics` baselines will be captured when the stack is up. CI on `main`
  green (last run: all checks pass).

**Verdict:** stable configuration, code path exercised, safety controls
verified. Nothing to fix. Next check by **8 Oct**; Day-7 note **~13 Oct**.

### Cadence check — 6 Oct 2026 (confirmation)

CHECKS re-run the same day to confirm the protocol executes end-to-end and
nothing drifted after the Day-1 entry:

- **All values identical to the Day-1 baseline:** `alembic 018`;
  merchant on `ensemble`; `forecasts` 3 rows, all `ensemble_v2`,
  **0 fallbacks**, no new rows since the smoke (`MAX(created_at)` = Day-1
  smoke); row-level avg wMAPE 0.50 / bias −0.17; `po_outcomes` 0;
  `audit_log` 0 forecast events.
- **No drift:** `FORECAST_ENGINE_DEFAULT` still defaults to `ensemble`,
  `FORECAST_ENGINE_OVERRIDE` unset, `TREND_MIN_DAILY = 10.0` untouched,
  local `main` == `origin/main` (65b641f), 0 open PRs.
- **Pipeline health:** post-merge CI for PR #55 finished **all 7 checks
  success** (runner slowness cleared; docker-build + Trivy completed);
  Deploy-to-Production success.
- **Anomalies:** none. Opt-outs: none.

Day-7 and Day-14 note structures are pre-drafted in *Status note
structures* above — next check by **8 Oct**.

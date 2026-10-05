# Forecast Tuning

How the demand forecasting pipeline chooses models, applies flags, and how to
roll changes out safely.

## Model versions (feature flags)

`FORECAST_MODEL_VERSION` controls what production serves:

| Value | Behavior |
|---|---|
| `exp_smoothing_v1` | Legacy v1 — exponential smoothing with 90-day window (production default) |
| `shadow` | **Computes and persists both v1 and ensemble_v2**, serves v1 (dev/CI default) |
| `ensemble_v2` | Serves the ensemble (post-backtest production target) |

Defaults are environment-aware: production → `exp_smoothing_v1`, everything
else → `shadow`. Any unknown value falls back to `exp_smoothing_v1`.

If `ensemble_v2` fails for any reason (bad data, model error), the node logs
the exception, increments `forecast_fallback_total`, and serves v1 — the
pipeline never fails because of forecasting.

## Engine selection (merchant-level)

`FORECAST_MODEL_VERSION` is the global/legacy switch. On top of it, each run
resolves a **canonical engine** (`ensemble | exponential | shadow`) once at
run start:

```
FORECAST_ENGINE_OVERRIDE  >  merchants.forecast_engine  >  FORECAST_ENGINE_DEFAULT  >  shadow
   (kill switch)              (per-merchant flag)           (default: ensemble)
```

| Variable | Default | Description |
|---|---|---|
| `FORECAST_ENGINE_DEFAULT` | `ensemble` | Engine for merchants without a stored flag |
| `FORECAST_ENGINE_OVERRIDE` | — | Global kill switch: forces every run (`exponential` = demote everyone) |
| `FORECAST_ENGINE_ROLLOUT_PERCENT` | `100` | Auto-promotion cohort: `merchant_id % 100 < percent` |
| `FORECAST_CIRCUIT_BREAKER_THRESHOLD` | `0.05` | Run-level ensemble failure/timeout rate that reruns the run on exponential |

Migration `018` made `ensemble` the column/server default and promoted the
parked `shadow` rows; `shadow` remains the measurement mode for tenants an
operator parks there (POST `shadow`), and the daily promotion job flips those
back to `ensemble` only after the safety gates pass. Operators can
inspect/override per tenant via
`GET/POST /api/v1/forecast-engine`. Full procedures:
[FORECAST-ENGINE-RUNBOOK.md](FORECAST-ENGINE-RUNBOOK.md).

## Ensemble v2 candidate models

`build_ensemble()` (in `agent/forecast.py`) fits each candidate on the SKU's
history, scores them on a hold-out window, and keeps the best:

| Candidate | Best for | Notes |
|---|---|---|
| `ses` | Flat/mean-reverting demand | alpha grid-selected simple exponential smoothing |
| `holt` | Trends | damped trend, non-negative clamped |
| `mean` | Short or noisy series | prefix-mean one-step baseline |
| `seasonal_holt` | Weekly seasonality | day-of-week deseasonalization + Holt; requires ≥14 days and seasonal strength ≥0.30 |
| `croston` | Intermittent demand | used when zero-share ≥0.70 or <14 nonzero days |
| `prophet` | Optional external | only if installed and eligible (see below) |

Selection = lowest hold-out wMAPE. When the top two candidates are within 10%
of each other, their paths are blended (equal weights).

Hold-out window by history size: `≥100d → 14d`, `≥40 → 7`, `≥25 → 5`,
`≥15 → 3`, otherwise no hold-out (all candidates score on training fit).

## Stockout (censored) correction

`FORECAST_STOCKOUT_CORRECTION` (default `true`). Zeros *between* nonzero
sales days are treated as unobserved demand (the SKU was likely out of stock)
and imputed from neighboring demand. Leading/trailing zeros are kept as real
zero-sales days. Set to `false` to disable.

## Confidence intervals

p10/p90 are computed from MAD-based robust sigma of the selected model's
hold-out residuals, scaled by √h (variance grows with horizon), floored at
`0.1 × max(mean demand, 1)` so new SKUs still get a usable band. Bands are
clamped at ≥0 and stored per SKU as `p10_daily_demand` / `p90_daily_demand`
plus days-of-cover equivalents.

## Prophet (optional)

Prophet is **not** a required dependency. To enable:

```bash
pip install -r requirements-forecast.txt
```

- `FORECAST_MODEL_PROPHET` (default `true`) gates its use entirely.
- Eligibility: ≥60 observations and ≥30 nonzero days.
- Timeouts (5s) and a circuit breaker (5 consecutive failures → open for
  300s) keep the pipeline safe; a timeout or failure means tier-0 models only.
- If no Prophet wheel is available for the deployment image, nothing breaks —
  the ensemble runs tier-0 models only.

## Other forecasting variables

| Variable | Default | Description |
|---|---|---|
| `FORECAST_HORIZON_DAYS` | `30` | Forecast horizon stored/returned |
| `FORECAST_HISTORY_DAYS` | `180` | Per-SKU history window loaded |
| `FORECAST_STOCKOUT_CORRECTION` | `true` | Impute censored (stockout) zero days |

## Metrics to watch

| Metric | Meaning |
|---|---|
| `forecast_runs_total{model}` | Runs per model version (v1 / v2) |
| `forecast_engine_used{engine,merchant}` | Which engine actually served each run |
| `forecast_fallback_total` | v2 failures that fell back to v1 — should stay ~0 |
| `forecast_fallback_count{reason}` | `ensemble_error` / `timeout` / `circuit_breaker` breakdown |
| `forecast_mape_ratio{merchant}` | Daily promotion-gate snapshot (> 0.85 would not promote) |
| `forecast_promotion_gate_pass{merchant}` | 1 when all gates pass for a shadow tenant |
| `forecast_promotion_status{merchant,engine}` | 1 for each tenant's current engine |
| `forecast_duration_seconds{model}` | Per-run latency (12s node timeout, 10s cache TTL) |

## Rollout & demotion procedure (merchant-level)

1. **New tenants** resolve to `ensemble` by default (column/server default +
   `FORECAST_ENGINE_DEFAULT` after migration `018`, which also promoted the
   tenants parked by `016`). To A/B a tenant, park it on `shadow` — both
   engines persist every run, exponential is served, and the safety gates
   decide promotion back.
2. Run the backtest against real history: `py -3.12 scripts/forecast_backtest.py`
   (see [FORECAST-ACCURACY.md](FORECAST-ACCURACY.md)).
3. The daily `daily_forecast_promotions` job promotes each shadow tenant
   once its gates pass (≥14 paired shadow days, MAPE ratio ≤ 0.85, bias and
   coverage checks) — or promote one manually:

   ```bash
   curl -X POST -H "x-api-key: $KEY" -H "content-type: application/json" \
     -d '{"engine": "ensemble"}' https://your-api/api/v1/forecast-engine
   ```

4. Watch `forecast_fallback_count{reason}` and `forecast_mape_ratio`.
   Demote a tenant (or everyone) by POSTing `exponential` or setting
   `FORECAST_ENGINE_OVERRIDE=exponential` — no redeploy needed.

The global `FORECAST_MODEL_VERSION` flag still applies as the fallback for
runs that carry no merchant-level engine (direct `graph.ainvoke` callers).

## Related

- [FORECAST-ENGINE-RUNBOOK.md](FORECAST-ENGINE-RUNBOOK.md) — promotion gates, kill switches, admin API, alerts
- [FORECAST-ACCURACY.md](FORECAST-ACCURACY.md) — metrics, backtest, baselines
- `agent/forecast.py` — ensemble engine (pure functions)
- `agent/forecast_engine.py` — engine resolution, gates, promotion job
- `agent/forecast_prophet.py` — optional Prophet adapter
- `tests/test_forecast_ensemble.py` — model math + no-regression guard
- `tests/test_forecast_promotion.py` — gates, breaker, admin API

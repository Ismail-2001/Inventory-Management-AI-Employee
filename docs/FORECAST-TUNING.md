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
| `forecast_fallback_total` | v2 failures that fell back to v1 — should stay ~0 |
| `forecast_duration_seconds{model}` | Per-run latency (12s node timeout, 10s cache TTL) |

## Rollout procedure (shadow-first)

1. **Dev/CI** runs `shadow` from day one — both rows persisted, v1 served.
2. Run the backtest against real history: `py -3.12 scripts/forecast_backtest.py`
   (see [FORECAST-ACCURACY.md](FORECAST-ACCURACY.md)).
3. If v2 pooled wMAPE ≤ v1 and coverage ≈ 0.80, set in production:

   ```bash
   fly secrets set FORECAST_MODEL_VERSION=ensemble_v2
   ```

4. Watch `forecast_fallback_total` and per-SKU `backtest_wmape` in the
   `forecasts` table for a week. Revert by setting the variable back to
   `exp_smoothing_v1` (no redeploy needed).

## Related

- [FORECAST-ACCURACY.md](FORECAST-ACCURACY.md) — metrics, backtest, baselines
- `agent/forecast.py` — ensemble engine (pure functions)
- `agent/forecast_prophet.py` — optional Prophet adapter
- `tests/test_forecast_ensemble.py` — model math + no-regression guard

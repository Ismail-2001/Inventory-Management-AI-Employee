# Forecast Accuracy

How forecast quality is measured, backtested, and guarded in CI.

## Metrics

| Metric | Formula | Read it as |
|---|---|---|
| **wMAPE** | `Σ|pred − actual| / Σ|actual|` | Absolute error weighted by demand — primary metric |
| **Bias %** | `Σ(pred − actual) / Σ|actual| × 100` | Over (+) / under (−) forecasting tendency |
| **MASE** | `mean(|pred − actual|) / mean(|actual_t − actual_{t−1}|)` | Error vs a naive one-step baseline; <1 beats naive |
| **Coverage** | share of days where `p10 ≤ actual ≤ p90` | Interval calibration — target ≈ 0.80 for a 10–90 band |

All metrics are computed per SKU on a hold-out window (default 14 days), then
aggregated **pooled** (weighted by per-SKU demand volume, the headline number)
and as **per-SKU means**.

## Running the backtest

```bash
DATABASE_URL=postgresql+asyncpg://... \
py -3.12 scripts/forecast_backtest.py --holdout 14 --min-history 60 --limit 500

# full per-SKU JSON for dashboards/PR comments
py -3.12 scripts/forecast_backtest.py --json backtest-report.json
```

Output:

```
backtest: 42 skus tested, 3 skipped (holdout=14d, min_history=60d)
models: {"croston": 4, "mean": 6, "seasonal_holt": 21, "ses": 11}

                wMAPE     bias%      MASE
v1 (legacy)     0.4120    -3.21     0.8340
v2 (ensemble)   0.2984    -0.87     0.6102
delta           -27.6%

per-sku wins: 36 improved / 6 regressed
p10-p90 coverage: 0.84 (target 0.80, period=14d)
```

Decision rule before flipping `FORECAST_MODEL_VERSION` to `ensemble_v2`:

- pooled wMAPE of v2 ≤ v1,
- coverage between 0.70 and 0.92,
- no large bias swing (|mean bias| ≤ 10%).

## CI guards

| Guard | Where | What it proves |
|---|---|---|
| No-regression sweep | `tests/test_forecast_ensemble.py::test_v2_wmape_not_worse_than_v1` | On synthetic seasonal/sparse/trend/constant series, v2 wMAPE ≤ v1 × 1.05 |
| Model math unit tests | `tests/test_forecast_ensemble.py` | Preparation, diagnosis, intervals, censoring, selection, node fallback |
| Backtest script tests | `tests/test_backtest_script.py` | Report computation + rendering on synthetic history |
| LLM eval suite | CI job `eval-suite` | Forecast accuracy + risk/PO quality scoring |
| Integration | CI job `integration-tests` | End-to-end pipeline against real Postgres |

## Stored accuracy

Every persisted `Forecast` row keeps its own quality fields (migration `015`):

| Column | Meaning |
|---|---|
| `backtest_wmape`, `backtest_bias` | Hold-out score of the selected model at write time |
| `p10_daily_demand`, `p90_daily_demand` | Confidence band (mean of band over horizon) |
| `days_of_cover_p10`, `days_of_cover_p90` | Days of stock under low/high demand |
| `horizon_days` | Forecast horizon used |
| `model_meta` | JSON: selected model, candidates + scores, blend flag, imputed days |

> **Baseline placeholder**: publish the first production numbers by running the
> backscript against the deployed database after go-live and pasting the
> summary table here. Until then, the synthetic CI guard is the reference.

## Related

- [FORECAST-TUNING.md](FORECAST-TUNING.md) — flags, models, rollout procedure
- `scripts/forecast_backtest.py` — backtest CLI
- `tests/test_forecast_ensemble.py` — accuracy guards

# Forecast Engine Runbook

Operating the merchant-level forecast engine: selection, kill switches,
auto-promotion gates, the circuit breaker, and what to watch.

## Engines

| Engine | Serves | Persists | Use when |
|---|---|---|---|
| `ensemble` | `ensemble_v2` rows | ensemble row | Primary — accuracy-proven per merchant |
| `exponential` | `exp_smoothing_v1` rows | v1 row | Kill switch / demotion / breaker fallback |
| `shadow` | `exp_smoothing_v1` rows | **both** rows | A/B measurement before promotion |

Legacy DB/env values are canonicalized: `exp_smoothing_v1 → exponential`,
`ensemble_v2 → ensemble`. Unknown values are ignored (never forced).

## Resolution precedence

Every run resolves its engine **once** at run start (`_initial_state` in
`api/routes/run_sync.py`) and carries it in graph state as `forecast_engine`:

```
FORECAST_ENGINE_OVERRIDE   (global kill switch — beats everything)
  > merchants.forecast_engine   (per-merchant flag: admin API or promotion job)
    > FORECAST_ENGINE_DEFAULT   (default: ensemble)
      > shadow                  (only if everything above is invalid)
```

Kill everyone back to exponential in one move (no redeploy):

```bash
fly secrets set FORECAST_ENGINE_OVERRIDE=exponential
```

Remove the override to return to per-merchant flags.

## Auto-promotion (daily job)

`daily_forecast_promotions` (every 24h) evaluates every merchant parked on
`shadow` and flips it to `ensemble` **only** when all gates pass *and* the
merchant is inside the rollout cohort (`merchant_id % 100 <
FORECAST_ENGINE_ROLLOUT_PERCENT`, default 100 = everyone).

Evaluation replays both engines on a 14-day hold-out of the merchant's own
sales history (`agent/forecast_engine.py`), tier-0 ensemble only —
deterministic, no Prophet/LLM calls in the gate path.

| Gate | Threshold | Why |
|---|---|---|
| `shadow_days` | ≥ 14 days with both engines persisted | Enough A/B pairs to judge |
| `min_evaluable_skus` | ≥ 3 SKUs with ≥28 days history | Statistically meaningful sample |
| `mape_ratio` | ensemble MAPE ≤ 0.85 × exponential MAPE | Must clearly beat v1 (fails if v1 MAPE is 0 — no proof, no promotion) |
| `high_velocity_bias` | \|bias\| ≤ 8% on SKUs ≥ 5 units/day | No systematic over/under-buying where it hurts most (vacuous pass if no high-velocity SKU) |
| `p50_coverage` | ≥ 45% of hold-out days inside the 50% interval | Intervals must not be fantasy |

On promotion the job sets `merchants.forecast_engine = ensemble`,
`forecast_promoted_at = now()`, writes an `forecast_engine_promoted` audit
event, and flips the `forecast_promotion_status{merchant, engine}` gauges.

If gates fail, **nothing changes** — the merchant stays on shadow and the
blocked gate names are visible via the API (below) and in
`forecast_mape_ratio`.

## Admin API

```bash
# what will this tenant serve next run? (+ optional gate evaluation)
curl -H "x-api-key: $KEY" "$BASE/api/v1/forecast-engine"
curl -H "x-api-key: $KEY" "$BASE/api/v1/forecast-engine?evaluate=true"

# force / demote this tenant (kill switch for one merchant)
curl -X POST -H "x-api-key: $KEY" -H "content-type: application/json" \
  -d '{"engine": "exponential"}' "$BASE/api/v1/forecast-engine"
```

The response reports `stored_engine` (DB flag), `active_engine` (what
resolution will serve), `source` (`global_override | merchant | default`),
the cohort flag, and — with `evaluate=true` — every gate with pass/value/
threshold. The demo tenant (id 0) is rejected: it has no persisted history.

## Circuit breaker (per run)

While serving `ensemble`, if more than
`FORECAST_CIRCUIT_BREAKER_THRESHOLD` (default 0.05 = 5%) of a run's SKUs
fail or time out, the node **reruns the whole run on `exponential`**,
records `forecast_circuit_tripped = true` in state, and increments
`forecast_fallback_count{reason="circuit_breaker"}` at ERROR level.
Per-SKU failures below the threshold still fall back individually and are
counted as `reason="ensemble_error"` / `reason="timeout"`.

## Metrics

| Metric | Read it as |
|---|---|
| `forecast_engine_used{engine,merchant}` | Which engine actually served each run |
| `forecast_fallback_count{reason}` | `ensemble_error` / `timeout` / `circuit_breaker` — should stay ~0 |
| `forecast_mape_ratio{merchant}` | Daily gate snapshot; > 0.85 = would not promote |
| `forecast_promotion_gate_pass{merchant}` | 1 when every gate passes for a shadow tenant (would promote today) |
| `forecast_promotion_status{merchant,engine}` | 1 for the tenant's current engine, 0 otherwise |
| `forecast_fallback_total` | Legacy alias of the non-breaker reasons (kept for dashboards) |

## Alerts

Defined in `prometheus/rules.yml` (group `inventory-agent-forecast`):

- **ForecastCircuitBreakerTripped** — a run fell back entirely; investigate
  ensemble errors/timeouts before touching flags.
- **EnsembleFallbackStorm** — >100 per-SKU ensemble fallbacks/hour.
- **ForecastMapeRegression** — a tenant's ratio stayed > 0.85 for 24h;
  if that tenant was already promoted, demote it.

## Weekly report

`weekly_forecast_report` (Mondays 08:30) emits per-merchant row counts by
`model_version` for the week plus gate snapshots for every shadow tenant,
to the audit log (`weekly_forecast_engine_report`) and Slack when
`SLACK_WEBHOOK_URL` is set. This is the A/B scoreboard: while a tenant is
in shadow, both engines write rows every run — compare them here.

## Demotion procedure

1. `POST /api/v1/forecast-engine {"engine": "exponential"}` for the tenant
   (or set the global override for everyone).
2. Confirm with `GET /api/v1/forecast-engine` → `active_engine`.
3. Open an incident note with the alert/metric that triggered it.
4. Fix the data/model issue, let the tenant re-accumulate shadow days
   (set it back to `shadow` to restart measurement), and wait for the daily
   job to re-promote — or promote manually once gates pass.

## Related

- [FORECAST-TUNING.md](FORECAST-TUNING.md) — model flags and ensemble internals
- [FORECAST-ACCURACY.md](FORECAST-ACCURACY.md) — backtest metrics behind the gates
- `agent/forecast_engine.py` — resolution, gates, promotion, weekly report
- `tests/test_forecast_promotion.py` — gate/breaker/API guarantees

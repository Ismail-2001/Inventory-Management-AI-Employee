import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { RefreshCw, TrendingUp } from 'lucide-react'
import { api, type RoiResponse, type RunSyncResponse } from '../lib/api'
import { MetricHelp } from '../components/MetricHelp'
import { AnimatedNumber } from '../components/AnimatedNumber'
import { cn, riskColor } from '../lib/utils'
import { showToast } from '../lib/toast'

type Range = { days?: number; start?: string; end?: string }

const PRESETS = [7, 30, 90]

const usd = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
const usdPrecise = (n: number) =>
  `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const num = (n: number, digits = 1) =>
  n.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: 0 })

function Panel({ title, help, children }: { title: string; help?: string; children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-lg border border-border bg-surface p-5"
    >
      <div className="mb-3 flex items-start justify-between gap-2">
        <h3 className="text-[13px] font-medium text-ink-muted">{title}</h3>
        {help && <MetricHelp text={help} />}
      </div>
      {children}
    </motion.div>
  )
}

function Stat({ label, value, sub, help, tone }: { label: string; value: ReactNode; sub: string; help?: string; tone?: 'healthy' | 'warning' | 'critical' }) {
  const toneClass = tone === 'healthy' ? 'text-healthy' : tone === 'warning' ? 'text-warning' : tone === 'critical' ? 'text-critical' : 'text-ink'
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] text-ink-muted">{label}</p>
        {help && <MetricHelp text={help} />}
      </div>
      <p className={cn('tabular mt-1 text-2xl font-medium', toneClass)}>{value}</p>
      <p className="mt-0.5 text-[11px] leading-snug text-ink-faint">{sub}</p>
    </div>
  )
}

export default function Dashboard() {
  const [roi, setRoi] = useState<RoiResponse | null>(null)
  const [range, setRange] = useState<Range>({ days: 30 })
  const [customOpen, setCustomOpen] = useState(false)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState<RunSyncResponse | null>(null)

  const fetchRoi = async (r: Range) => {
    try {
      setRoi(await api.getRoi(r))
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to load ROI metrics')
    }
  }

  useEffect(() => {
    void fetchRoi(range)
  }, [range])

  const selectPreset = (days: number) => {
    setCustomOpen(false)
    setRange({ days })
  }

  const applyCustom = () => {
    if (!start || !end) return
    setRange({ start, end })
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      const result = await api.runSync()
      setSyncResult(result)
      showToast(`Sync complete — ${result.synced_products} products, ${result.synced_sales} sales`)
      await fetchRoi(range)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-medium">Dashboard</h2>
          <p className="mt-1 text-[13.5px] text-ink-muted">
            ROI &amp; performance — see whether the AI Employee is paying for itself.
          </p>
        </div>
        <motion.button
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          onClick={handleSync}
          disabled={syncing}
          className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-gradient-to-br from-accent to-accent-hover px-4 text-sm font-medium text-ink-on-accent shadow-[0_4px_16px_-4px_rgba(43,58,103,0.5)] transition-shadow hover:shadow-[0_6px_20px_-4px_rgba(43,58,103,0.6)] disabled:pointer-events-none disabled:opacity-50"
        >
          <motion.span animate={syncing ? { rotate: 360 } : { rotate: 0 }} transition={syncing ? { repeat: Infinity, duration: 0.8, ease: 'linear' } : {}}>
            <RefreshCw className="h-3.5 w-3.5" />
          </motion.span>
          {syncing ? 'Syncing…' : 'Run Sync'}
        </motion.button>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {PRESETS.map(d => (
          <button
            key={d}
            onClick={() => selectPreset(d)}
            aria-pressed={!customOpen && range.days === d}
            className={cn(
              'h-8 rounded-md border px-3 text-[13px] font-medium transition-colors',
              !customOpen && range.days === d
                ? 'border-accent/40 bg-accent-bg text-accent'
                : 'border-border bg-surface text-ink-muted hover:text-ink',
            )}
          >
            {d}d
          </button>
        ))}
        <button
          onClick={() => setCustomOpen(o => !o)}
          aria-pressed={customOpen}
          className={cn(
            'h-8 rounded-md border px-3 text-[13px] font-medium transition-colors',
            customOpen ? 'border-accent/40 bg-accent-bg text-accent' : 'border-border bg-surface text-ink-muted hover:text-ink',
          )}
        >
          Custom
        </button>
        {customOpen && (
          <div className="flex flex-wrap items-center gap-1.5">
            <input
              type="date"
              aria-label="Start date"
              value={start}
              onChange={e => setStart(e.target.value)}
              className="h-8 rounded-md border border-border bg-surface px-2 text-[12.5px] text-ink"
            />
            <input
              type="date"
              aria-label="End date"
              value={end}
              onChange={e => setEnd(e.target.value)}
              className="h-8 rounded-md border border-border bg-surface px-2 text-[12.5px] text-ink"
            />
            <button
              onClick={applyCustom}
              disabled={!start || !end}
              className="h-8 rounded-md bg-accent px-3 text-[13px] font-medium text-ink-on-accent transition-colors hover:bg-accent-hover disabled:pointer-events-none disabled:opacity-40"
            >
              Apply
            </button>
          </div>
        )}
        {roi && (
          <span className="ml-auto font-mono text-[11.5px] text-ink-faint">
            {roi.period.start.slice(0, 10)} → {roi.period.end.slice(0, 10)} · {roi.period.days}d
          </span>
        )}
      </div>

      <AnimatePresence>
        {syncResult && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden rounded-lg border border-accent/20 bg-accent-bg p-4 font-mono text-[12.5px] text-accent"
          >
            Synced {syncResult.synced_products} products, {syncResult.synced_sales} sales.&nbsp;
            {syncResult.risk_alerts} risk alerts, {syncResult.purchase_orders} purchase orders drafted.
          </motion.div>
        )}
      </AnimatePresence>

      {!roi ? (
        <p className="py-16 text-center text-[13px] text-ink-faint">Loading ROI metrics…</p>
      ) : (
        <RoiSections roi={roi} syncResult={syncResult} />
      )}
    </div>
  )
}

function RoiSections({ roi, syncResult }: { roi: RoiResponse; syncResult: RunSyncResponse | null }) {
  const op = roi.operational
  const eff = roi.efficiency
  const health = roi.health
  const accuracy = op.forecast_accuracy
  const decisions = op.po_decisions
  const conf = health.forecast_confidence
  const engine = health.engine
  const atRisk = health.at_risk

  const trend = accuracy.series.map(p => ({
    date: p.date.slice(5),
    ensemble: p.ensemble_wmape_pct,
    baseline: p.baseline_wmape_pct,
  }))
  const hasAccuracyData = accuracy.ensemble_count + accuracy.baseline_count + accuracy.outcome_count > 0

  return (
    <>
          <div>
            <h3 className="mb-3 text-[13px] font-medium text-ink-muted">Value &amp; efficiency</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat
                label="Value generated"
                value={usd(eff.value_generated_usd)}
                sub="Revenue protected + capital freed"
                help={`Stockout revenue protected (units x unit cost x ${eff.assumptions.revenue_multiplier}x markup) plus capital not committed on trimmed or rejected POs, within the selected window.`}
              />
              <Stat
                label="LLM cost"
                value={usdPrecise(eff.llm.cost_usd)}
                sub={`${eff.llm.calls.toLocaleString('en-US')} calls · ${eff.llm.tokens_in.toLocaleString('en-US')} in / ${eff.llm.tokens_out.toLocaleString('en-US')} out tokens`}
                help="Estimated token spend for this window: pipeline nodes (llm_usage.estimated_cost) plus chat replies (chat_messages.cost_usd). Usage is tracked globally, not per tenant."
              />
              <Stat
                label="ROI"
                value={eff.roi_multiple === null ? '—' : `${num(eff.roi_multiple)}x`}
                sub="Value ÷ LLM cost"
                tone={eff.roi_multiple !== null && eff.roi_multiple >= 1 ? 'healthy' : undefined}
                help="Value generated divided by LLM cost for the selected window. Shown as — when cost is $0 (value was generated with no measured token spend)."
              />
              <Stat
                label="Hours saved"
                value={`${num(eff.hours_saved)}`}
                sub={`${eff.hours_saved_basis.decided_pos} POs x ${eff.hours_saved_basis.minutes_per_po} min of manual work`}
                help={`Assumes each decided PO would otherwise take ${eff.assumptions.minutes_per_po} minutes of manual effort (research supplier, check stock, draft order, chase approval). Configurable via ROI_MANUAL_PO_MINUTES.`}
              />
            </div>
          </div>

          <div>
            <h3 className="mb-3 text-[13px] font-medium text-ink-muted">Operational impact</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat
                label="Stockouts avoided"
                value={`${op.stockouts_avoided.units.toLocaleString('en-US')} units`}
                sub={`${op.stockouts_avoided.events} events · ${usd(op.stockouts_avoided.revenue_protected_usd)} revenue protected`}
                tone="healthy"
                help="PO outcomes where pre-delivery demand exceeded stock on hand (a stockout was imminent) and no stockout actually occurred. Units = quantities on those POs; revenue = units x unit cost x markup."
              />
              <Stat
                label="Excess avoided"
                value={`${op.excess_reduction.units.toLocaleString('en-US')} units`}
                sub={`${op.excess_reduction.trimmed_pos} trimmed · ${op.excess_reduction.rejected_pos} declined · ${usd(op.excess_reduction.capital_freed_usd)} freed`}
                help="Inventory commitment that never happened: quantities operators trimmed before approval plus POs declined outright, valued at unit cost."
              />
              <Stat
                label="PO acceptance"
                value={`${num(decisions.acceptance_rate_pct)}%`}
                sub={decisions.decided ? `${decisions.accepted} of ${decisions.decided} decided POs accepted` : 'No decided POs in window'}
                tone="healthy"
                help="Share of decided POs created in this window that were approved: accepted ÷ (accepted + rejected)."
              />
              <Stat
                label="Time to decision"
                value={decisions.avg_hours_to_decision === null ? '—' : `${num(decisions.avg_hours_to_decision)}h`}
                sub={decisions.decisions_with_timestamp ? `avg across ${decisions.decisions_with_timestamp} decisions` : 'No decision timestamps yet'}
                help="Average hours from PO creation to its recorded decision, using audit-log approve/reject events (approvals fall back to approved_at)."
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel
              title="PO decisions"
              help="All POs created in the window that reached a decision. Accepted (as-is) means the operator approved the drafted quantity unchanged."
            >
              {decisions.decided > 0 ? (
                <div className="space-y-3">
                  <p className="tabular text-3xl font-medium text-ink">{num(decisions.acceptance_rate_pct)}%</p>
                  <div className="space-y-1.5 font-mono text-[12.5px] text-ink-muted">
                    <p className="flex justify-between">
                      <span>Accepted (as-is)</span>
                      <span className="tabular text-ink">{decisions.accepted_as_is}</span>
                    </p>
                    <p className="flex justify-between">
                      <span>Edited then Approved</span>
                      <span className="tabular text-ink">{decisions.edited_then_approved}</span>
                    </p>
                    <p className="flex justify-between">
                      <span>Rejected</span>
                      <span className="tabular text-ink">{decisions.rejected}</span>
                    </p>
                    <p className="flex justify-between border-t border-border pt-1.5">
                      <span>Avg time to decision</span>
                      <span className="tabular text-ink">
                        {decisions.avg_hours_to_decision === null ? '—' : `${num(decisions.avg_hours_to_decision)}h`}
                      </span>
                    </p>
                  </div>
                </div>
              ) : (
                <p className="text-[13px] text-ink-faint">No PO decisions yet</p>
              )}
            </Panel>

            <Panel
              title="Forecast Accuracy"
              help="Backtest wMAPE on each persisted forecast: the ensemble engine vs the legacy baseline engine, plus an independent error measure from evaluated PO outcomes."
            >
              {hasAccuracyData ? (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3 font-mono text-[12.5px] text-ink-muted">
                    <div className="rounded-md bg-surface-sunken p-2.5">
                      <p className="text-[11px] text-ink-faint">Ensemble wMAPE</p>
                      <p className="tabular text-[15px] font-medium text-ink">
                        {accuracy.ensemble_wmape_pct === null ? '—' : `${num(accuracy.ensemble_wmape_pct)}%`}
                      </p>
                    </div>
                    <div className="rounded-md bg-surface-sunken p-2.5">
                      <p className="text-[11px] text-ink-faint">Baseline wMAPE</p>
                      <p className="tabular text-[15px] font-medium text-ink">
                        {accuracy.baseline_wmape_pct === null ? '—' : `${num(accuracy.baseline_wmape_pct)}%`}
                      </p>
                    </div>
                  </div>
                  <div className="space-y-1 font-mono text-[12.5px] text-ink-muted">
                    <div className="flex justify-between gap-3">
                      <span>Improvement</span>
                      <span className={cn('tabular font-medium', (accuracy.wmape_improvement_pct ?? 0) >= 0 ? 'text-healthy' : 'text-critical')}>
                        {accuracy.wmape_improvement_pct === null ? '—' : `${accuracy.wmape_improvement_pct >= 0 ? '+' : ''}${num(accuracy.wmape_improvement_pct)}%`}
                      </span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span>Forecast Error</span>
                      <span className="tabular text-ink">
                        {accuracy.outcome_mape_pct === null ? '—' : `${num(accuracy.outcome_mape_pct)}%`}{' '}
                        <span className="text-ink-faint">({accuracy.outcome_count} outcomes)</span>
                      </span>
                    </div>
                  </div>
                  {trend.length > 0 && (
                    <div className="h-[150px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={trend} margin={{ top: 6, right: 8, left: -14, bottom: 0 }}>
                          <CartesianGrid stroke="#eef0ec" vertical={false} />
                          <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#8a8f97' }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
                          <YAxis tick={{ fontSize: 10, fill: '#8a8f97' }} axisLine={false} tickLine={false} width={40} unit="%" />
                          <Tooltip
                            cursor={{ stroke: '#cac8bb' }}
                            contentStyle={{ borderRadius: 8, border: '1px solid #e1e0d7', fontSize: 12, fontFamily: 'IBM Plex Mono, monospace' }}
                            formatter={(value: any, name: any) => [`${value}%`, name === 'ensemble' ? 'Ensemble' : 'Baseline']}
                          />
                          <Line type="monotone" dataKey="ensemble" stroke="#2b3a67" strokeWidth={2} dot={false} name="ensemble" connectNulls />
                          <Line type="monotone" dataKey="baseline" stroke="#8a8f97" strokeWidth={1.5} strokeDasharray="4 3" dot={false} name="baseline" connectNulls />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                  <p className="font-mono text-[11px] text-ink-faint">
                    Ensemble (solid) vs baseline (dashed) · {accuracy.ensemble_count} ensemble / {accuracy.baseline_count} baseline forecasts
                  </p>
                </div>
              ) : (
                <p className="text-[13px] text-ink-faint">Not enough forecast data yet</p>
              )}
            </Panel>
          </div>

          <div>
            <h3 className="mb-3 text-[13px] font-medium text-ink-muted">Health</h3>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <Panel
                title="At-risk SKUs"
                help="Live snapshot (not windowed): SKUs with unresolved critical/warning risk alerts right now, one entry per SKU using the latest alert."
              >
                <p className={cn('tabular text-3xl font-medium', atRisk.total > 0 ? (atRisk.critical > 0 ? 'text-critical' : 'text-warning') : 'text-healthy')}>
                  {atRisk.total}
                </p>
                <p className="mt-0.5 text-[11px] text-ink-faint">
                  {atRisk.critical} critical · {atRisk.warning} warning
                </p>
                {atRisk.skus.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {atRisk.skus.map(s => (
                      <span key={s.sku_id} className={cn('rounded-full border px-2 py-0.5 font-mono text-[11px]', riskColor(s.risk_level))}>
                        {s.sku_code}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-[13px] text-ink-faint">All clear — no SKUs at risk</p>
                )}
              </Panel>

              <Panel
                title="Forecast coverage"
                help="Share of forecasts in this window persisted with p10–p90 confidence intervals. Width buckets compare (p90 − p10) ÷ p50: tight ≤ 0.5, typical ≤ 1.0, wide above 1.0."
              >
                <p className="tabular text-3xl font-medium text-ink">{num(conf.coverage_pct)}%</p>
                <p className="mt-0.5 text-[11px] text-ink-faint">
                  {conf.with_intervals} of {conf.total_forecasts} forecasts carry intervals
                </p>
                <div className="mt-3 space-y-1.5">
                  {conf.distribution.map(d => {
                    const share = conf.with_intervals > 0 ? (d.count / conf.with_intervals) * 100 : 0
                    return (
                      <div key={d.bucket} className="flex items-center gap-2">
                        <span className="w-14 shrink-0 text-[11px] text-ink-faint">{d.bucket}</span>
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-sunken">
                          <div className="h-1.5 rounded-full bg-accent" style={{ width: `${share}%` }} />
                        </div>
                        <span className="tabular w-6 text-right text-[11px] text-ink-muted">{d.count}</span>
                      </div>
                    )
                  })}
                </div>
              </Panel>

              <Panel
                title="Engine health"
                help="Fallback rate = forecasts where the ensemble raised an error and the legacy engine served instead (model_meta.fallback_used). Timed-out runs write no row and are excluded."
              >
                <p className={cn('tabular text-3xl font-medium', engine.fallback_rate_pct > 10 ? 'text-warning' : 'text-healthy')}>
                  {num(engine.fallback_rate_pct)}%
                </p>
                <p className="mt-0.5 text-[11px] text-ink-faint">
                  {engine.fallbacks} of {engine.total_forecasts} runs fell back
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {engine.distribution.map(d => (
                    <span key={d.model} className="rounded-full border border-border bg-surface-sunken px-2 py-0.5 font-mono text-[11px] text-ink-muted">
                      {d.model}: {d.count}
                    </span>
                  ))}
                </div>
              </Panel>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="rounded-lg border border-border bg-surface p-5"
            >
              <h3 className="mb-3 flex items-center gap-1.5 text-[13px] font-medium text-ink-muted">
                <TrendingUp className="h-3.5 w-3.5" /> Recent Sync
              </h3>
              {syncResult ? (
                <div className="space-y-1.5 font-mono text-[12.5px] text-ink-muted">
                  <p>Products synced: <span className="tabular text-ink"><AnimatedNumber value={syncResult.synced_products} /></span></p>
                  <p>Sales synced: <span className="tabular text-ink"><AnimatedNumber value={syncResult.synced_sales} /></span></p>
                  <p>Risk alerts: <span className="tabular text-ink"><AnimatedNumber value={syncResult.risk_alerts} /></span></p>
                  <p>POs drafted: <span className="tabular text-ink"><AnimatedNumber value={syncResult.purchase_orders} /></span></p>
                </div>
              ) : (
                <p className="text-[13px] text-ink-faint">Run a sync to see results</p>
              )}
            </motion.div>

            <details className="rounded-lg border border-border bg-surface p-5">
              <summary className="cursor-pointer select-none text-[13px] font-medium text-ink-muted">
                How we calculate these numbers
              </summary>
              <ul className="mt-3 list-disc space-y-1.5 pl-5 text-[12.5px] leading-relaxed text-ink-muted">
                <li>
                  <span className="font-medium text-ink">Value</span> = stockout revenue protected (units x unit cost x{' '}
                  {eff.assumptions.revenue_multiplier}x markup) + capital freed (trimmed + declined POs at cost).
                </li>
                <li>
                  <span className="font-medium text-ink">ROI</span> = total value ÷ LLM cost for the window.
                </li>
                <li>
                  <span className="font-medium text-ink">Time savings</span> = decided POs x {eff.assumptions.minutes_per_po} minutes
                  of assumed manual effort ÷ 60.
                </li>
                <li>
                  A stockout counts as avoided when pre-delivery demand exceeded stock on hand before the PO landed and none occurred
                  after.
                </li>
                <li>
                  Backtest wMAPE on each persisted forecast row compares the ensemble engine with the legacy baseline engine.
                </li>
                <li>Full methodology, formulas and assumptions: docs/ROI-DASHBOARD.md.</li>
              </ul>
            </details>
          </div>
    </>
  )
}

import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { RefreshCw, TrendingUp } from 'lucide-react'
import { api, type MetricsResponse, type RunSyncResponse } from '../lib/api'
import { AnimatedNumber } from '../components/AnimatedNumber'
import { showToast } from '../lib/toast'

function pluralize(n: number, singular: string, plural: string) {
  return n === 1 ? singular : plural
}

function fmtPct(v: number) {
  return v % 1 === 0 ? `${v}%` : `${v.toFixed(1)}%`
}

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
}
const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] as const } },
} satisfies import('framer-motion').Variants

export default function Dashboard() {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
  const [syncResult, setSyncResult] = useState<RunSyncResponse | null>(null)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    api.getMetrics(7).then(setMetrics).catch(() => {})
  }, [])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const res = await api.runSync()
      setSyncResult(res)
      showToast(`Synced ${res.synced_products} products, ${res.synced_sales} sales`)
      api.getMetrics(7).then(setMetrics).catch(() => {})
    } catch (e: any) {
      showToast(e.message)
    } finally {
      setSyncing(false)
    }
  }

  const acc = metrics?.acceptance
  const fore = metrics?.forecast_error

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-6">
      <motion.div variants={item} className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-medium">Dashboard</h2>
          <p className="mt-1 text-[13.5px] text-ink-muted">Inventory overview and key metrics</p>
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
      </motion.div>

      <AnimatePresence>
        {syncResult && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden rounded-lg border border-accent/20 bg-accent-bg p-4 font-mono text-[12.5px] text-accent"
          >
            Synced {syncResult.synced_products} products, {syncResult.synced_sales} sales.&nbsp;
            {syncResult.risk_alerts > 0 && `${syncResult.risk_alerts} ${pluralize(syncResult.risk_alerts, 'risk alert', 'risk alerts')}, `}
            {syncResult.purchase_orders > 0 && `${syncResult.purchase_orders} ${pluralize(syncResult.purchase_orders, 'PO drafted', 'POs drafted')}.`}
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div variants={container} className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
        <StatCard variants={item} label="Accepted (as-is)" value={acc?.accepted_as_is_pct ?? 0} sub={acc ? `${acc.accepted_as_is} of ${acc.total}` : ''} tone="healthy" hasData={!!acc} />
        <StatCard variants={item} label="Edited then Approved" value={acc?.edited_then_approved_pct ?? 0} sub={acc ? `${acc.edited_then_approved} orders` : ''} tone="warning" hasData={!!acc} />
        <StatCard variants={item} label="Rejected" value={acc?.rejected_pct ?? 0} sub={acc ? `${acc.rejected} orders` : ''} tone="critical" hasData={!!acc} />
        <StatCard variants={item} label="Forecast Error" value={fore?.mean_error_pct ?? 0} sub={fore ? `from ${fore.count} outcomes` : ''} tone="default" hasData={!!fore} />
      </motion.div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <motion.div variants={item} whileHover={{ y: -2 }} className="rounded-lg border border-border bg-surface p-5 transition-shadow hover:shadow-md">
          <h3 className="mb-3 flex items-center gap-1.5 text-[13px] font-medium text-ink-muted">
            <TrendingUp className="h-3.5 w-3.5" /> Recent Sync
          </h3>
          {syncResult ? (
            <div className="space-y-1.5 font-mono text-[12.5px] text-ink-muted">
              <p>Products synced: <span className="tabular text-ink"><AnimatedNumber value={syncResult.synced_products} /></span></p>
              <p>Sales records: <span className="tabular text-ink"><AnimatedNumber value={syncResult.synced_sales} /></span></p>
              <p>Risk alerts: <span className="tabular text-ink"><AnimatedNumber value={syncResult.risk_alerts} /></span></p>
              <p>POs drafted: <span className="tabular text-ink"><AnimatedNumber value={syncResult.purchase_orders} /></span></p>
            </div>
          ) : (
            <p className="text-[13px] text-ink-faint">Run a sync to see results</p>
          )}
        </motion.div>

        <motion.div variants={item} whileHover={{ y: -2 }} className="rounded-lg border border-border bg-surface p-5 transition-shadow hover:shadow-md">
          <h3 className="mb-3 text-[13px] font-medium text-ink-muted">Forecast Accuracy</h3>
          {fore ? (
            <div className="space-y-1.5 font-mono text-[12.5px] text-ink-muted">
              <p>Mean error: <span className="tabular font-medium text-ink">{fmtPct(fore.mean_error_pct)}</span></p>
              <p>Range: <span className="tabular text-ink">{fmtPct(fore.min_error_pct)} – {fmtPct(fore.max_error_pct)}</span></p>
              <p>Stockout rate: <span className="tabular text-ink">{fmtPct(fore.stockout_rate)}</span></p>
            </div>
          ) : (
            <p className="text-[13px] text-ink-faint">Not enough outcome data yet</p>
          )}
        </motion.div>
      </div>
    </motion.div>
  )
}

function StatCard({ label, value, sub, tone, hasData, variants }: { label: string; value: number; sub: string; tone: 'healthy' | 'warning' | 'critical' | 'default'; hasData: boolean; variants?: any }) {
  const toneClass: Record<string, string> = {
    healthy: 'text-healthy',
    warning: 'text-warning',
    critical: 'text-critical',
    default: 'text-ink',
  }
  return (
    <motion.div variants={variants} whileHover={{ y: -3, transition: { duration: 0.15 } }} className="rounded-lg bg-surface-sunken p-4 transition-shadow hover:shadow-md">
      <p className="text-[13px] text-ink-muted">{label}</p>
      <p className={`tabular mt-1 text-2xl font-medium ${toneClass[tone]}`}>
        {hasData ? <AnimatedNumber value={value} suffix="%" decimals={1} /> : '—'}
      </p>
      <p className="mt-0.5 text-[11px] text-ink-faint">{sub}</p>
    </motion.div>
  )
}

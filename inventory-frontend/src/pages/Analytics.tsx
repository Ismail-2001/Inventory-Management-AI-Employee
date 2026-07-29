import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { api, type MetricsResponse } from '../lib/api'
import { showToast } from '../lib/toast'

function pluralize(n: number, singular: string, plural: string) {
  return n === 1 ? singular : plural
}

function fmtPct(v: number) {
  return v % 1 === 0 ? `${v}%` : `${v.toFixed(1)}%`
}

function MinBar(props: any) {
  const { x, y, width, height, fill } = props
  return <rect x={x} y={y} width={Math.max(width, 4)} height={height} fill={fill} rx={6} />
}

export default function Analytics() {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null)
  const [weekloading, setWeekloading] = useState(false)
  const [evalLoading, setEvalLoading] = useState(false)

  useEffect(() => {
    api.getMetrics(30).then(setMetrics).catch(() => {})
  }, [])

  const handleWeekly = async () => {
    setWeekloading(true)
    try {
      const res = await api.triggerWeekly()
      showToast(`Weekly report generated: ${res.insights_count} ${pluralize(res.insights_count, 'insight', 'insights')}`)
    } catch (e: any) {
      showToast(e.message)
    } finally {
      setWeekloading(false)
    }
  }

  const handleEval = async () => {
    setEvalLoading(true)
    try {
      const res = await api.triggerOutcomeEval()
      showToast(`Evaluated ${res.evaluated} pending ${pluralize(res.evaluated, 'outcome', 'outcomes')}`)
      api.getMetrics(30).then(setMetrics).catch(() => {})
    } catch (e: any) {
      showToast(e.message)
    } finally {
      setEvalLoading(false)
    }
  }

  const acc = metrics?.acceptance
  const fore = metrics?.forecast_error

  const acceptanceData = [
    { label: 'Accepted', value: acc?.accepted_as_is_pct ?? 0, tone: '#2f6b4c' },
    { label: 'Edited', value: acc?.edited_then_approved_pct ?? 0, tone: '#96660f' },
    { label: 'Rejected', value: acc?.rejected_pct ?? 0, tone: '#a83a32' },
  ]

  const errorData = fore ? [
    { label: 'Min', value: fore.min_error_pct },
    { label: 'Mean', value: fore.mean_error_pct },
    { label: 'Max', value: fore.max_error_pct },
  ] : []

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-medium">Analytics</h2>
          <p className="mt-1 text-[13.5px] text-ink-muted">Agent performance and forecast accuracy</p>
        </div>
        <div className="flex gap-2">
          <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            onClick={handleEval} disabled={evalLoading}
            className="inline-flex h-9 items-center justify-center rounded-md border border-border-strong bg-surface px-4 text-sm font-medium transition-colors hover:border-accent hover:text-accent disabled:pointer-events-none disabled:opacity-40"
          >
            {evalLoading ? 'Evaluating…' : 'Evaluate Outcomes'}
          </motion.button>
          <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            onClick={handleWeekly} disabled={weekloading}
            className="inline-flex h-9 items-center justify-center rounded-md bg-gradient-to-br from-accent to-accent-hover px-4 text-sm font-medium text-ink-on-accent shadow-[0_4px_16px_-4px_rgba(43,58,103,0.5)] disabled:pointer-events-none disabled:opacity-50"
          >
            {weekloading ? 'Running…' : 'Run Weekly Report'}
          </motion.button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="rounded-lg border border-border bg-surface p-5">
          <h3 className="mb-4 text-[13px] font-medium text-ink-muted">PO Acceptance Rates</h3>
          {acc ? (
            <div className="h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={acceptanceData} layout="vertical" margin={{ left: 8, right: 24 }}>
                  <XAxis type="number" domain={[0, 100]} hide />
                  <YAxis type="category" dataKey="label" width={70} tick={{ fontSize: 12, fill: '#5b6169' }} axisLine={false} tickLine={false} />
                  <Tooltip
                    cursor={{ fill: '#eef0ec' }}
                    contentStyle={{ borderRadius: 8, border: '1px solid #e1e0d7', fontSize: 12, fontFamily: 'IBM Plex Mono, monospace' }}
                    formatter={(v: any) => [fmtPct(v), '']}
                  />
                  <Bar dataKey="value" shape={<MinBar />} radius={[0, 6, 6, 0]} animationDuration={800} animationEasing="ease-out">
                    {acceptanceData.map((d, i) => <Cell key={i} fill={d.tone} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-[13px] text-ink-faint">No PO data yet</p>
          )}
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }} className="rounded-lg border border-border bg-surface p-5">
          <h3 className="mb-4 text-[13px] font-medium text-ink-muted">Forecast Error Distribution</h3>
          {fore ? (
            <>
              <div className="h-[160px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={errorData} margin={{ top: 8 }}>
                    <XAxis dataKey="label" tick={{ fontSize: 12, fill: '#5b6169' }} axisLine={false} tickLine={false} />
                    <YAxis hide />
                    <Tooltip
                      cursor={{ fill: '#eef0ec' }}
                      contentStyle={{ borderRadius: 8, border: '1px solid #e1e0d7', fontSize: 12, fontFamily: 'IBM Plex Mono, monospace' }}
                      formatter={(v: any) => [fmtPct(v), '']}
                    />
                    <Bar dataKey="value" fill="#2b3a67" radius={[6, 6, 0, 0]} animationDuration={800} animationEasing="ease-out" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="text-center font-mono text-[12px] text-ink-muted">
                Based on {fore.count} evaluated {pluralize(fore.count, 'outcome', 'outcomes')} · Stockout rate: {fore.stockout_rate}%
              </p>
            </>
          ) : (
            <p className="text-[13px] text-ink-faint">Not enough outcome data yet</p>
          )}
        </motion.div>
      </div>
    </motion.div>
  )
}

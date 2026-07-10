import { useEffect, useState } from 'react'
import { api, type MetricsResponse } from '../lib/api'

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
      alert(`Weekly report generated: ${res.insights_count} insights`)
    } catch (e: any) {
      alert(e.message)
    } finally {
      setWeekloading(false)
    }
  }

  const handleEval = async () => {
    setEvalLoading(true)
    try {
      const res = await api.triggerOutcomeEval()
      alert(`Evaluated ${res.evaluated} pending outcomes`)
      api.getMetrics(30).then(setMetrics).catch(() => {})
    } catch (e: any) {
      alert(e.message)
    } finally {
      setEvalLoading(false)
    }
  }

  const acc = metrics?.acceptance
  const fore = metrics?.forecast_error

  const barData = [
    { label: 'Accepted As-Is', value: acc?.accepted_as_is_pct ?? 0, color: 'bg-green-400' },
    { label: 'Edited & Approved', value: acc?.edited_then_approved_pct ?? 0, color: 'bg-amber-400' },
    { label: 'Rejected', value: acc?.rejected_pct ?? 0, color: 'bg-red-400' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Analytics</h2>
          <p className="text-sm text-gray-500 mt-1">Agent performance and forecast accuracy</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleEval}
            disabled={evalLoading}
            className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {evalLoading ? 'Evaluating...' : 'Evaluate Outcomes'}
          </button>
          <button
            onClick={handleWeekly}
            disabled={weekloading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {weekloading ? 'Running...' : 'Run Weekly Report'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">PO Acceptance Rates</h3>
          {acc ? (
            <div className="space-y-4">
              {barData.map(d => (
                <div key={d.label}>
                  <div className="flex justify-between text-sm text-gray-600 mb-1">
                    <span>{d.label}</span>
                    <span className="font-medium">{d.value}%</span>
                  </div>
                  <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${d.color} transition-all`}
                      style={{ width: `${d.value}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400">No PO data yet</p>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Forecast Error Distribution</h3>
          {fore ? (
            <div className="space-y-4">
              <div className="flex items-end gap-3 h-32">
                <div className="flex-1 flex flex-col items-center">
                  <span className="text-lg font-bold text-gray-900">{fore.min_error_pct}%</span>
                  <span className="text-xs text-gray-400 mt-1">Min</span>
                  <div className="w-full bg-gray-100 rounded-t mt-1" style={{ height: '24px' }} />
                </div>
                <div className="flex-1 flex flex-col items-center">
                  <span className="text-lg font-bold text-gray-900">{fore.mean_error_pct}%</span>
                  <span className="text-xs text-gray-400 mt-1">Mean</span>
                  <div
                    className="w-full bg-blue-400 rounded-t mt-1"
                    style={{ height: '48px' }}
                  />
                </div>
                <div className="flex-1 flex flex-col items-center">
                  <span className="text-lg font-bold text-gray-900">{fore.max_error_pct}%</span>
                  <span className="text-xs text-gray-400 mt-1">Max</span>
                  <div className="w-full bg-gray-100 rounded-t mt-1" style={{ height: '24px' }} />
                </div>
              </div>
              <p className="text-sm text-gray-500 text-center">
                Based on {fore.count} evaluated outcome{fore.count !== 1 ? 's' : ''} &middot; Stockout rate: {fore.stockout_rate}%
              </p>
            </div>
          ) : (
            <p className="text-sm text-gray-400">Not enough outcome data yet</p>
          )}
        </div>
      </div>
    </div>
  )
}

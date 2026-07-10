import { useEffect, useState } from 'react'
import { api, type MetricsResponse, type RunSyncResponse } from '../lib/api'


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
      api.getMetrics(7).then(setMetrics).catch(() => {})
    } catch (e: any) {
      alert(e.message)
    } finally {
      setSyncing(false)
    }
  }

  const acc = metrics?.acceptance
  const fore = metrics?.forecast_error

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Dashboard</h2>
          <p className="text-sm text-gray-500 mt-1">Inventory overview and key metrics</p>
        </div>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {syncing ? 'Syncing...' : 'Run Sync'}
        </button>
      </div>

      {syncResult && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
          Synced {syncResult.synced_products} products, {syncResult.synced_sales} sales.&nbsp;
          {syncResult.risk_alerts > 0 && `${syncResult.risk_alerts} risk alerts, `}
          {syncResult.purchase_orders > 0 && `${syncResult.purchase_orders} POs drafted.`}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Accepted (as-is)" value={acc ? `${acc.accepted_as_is_pct}%` : '—'} sub={acc ? `${acc.accepted_as_is} of ${acc.total}` : ''} color="green" />
        <StatCard label="Edited then Approved" value={acc ? `${acc.edited_then_approved_pct}%` : '—'} sub={acc ? `${acc.edited_then_approved} orders` : ''} color="amber" />
        <StatCard label="Rejected" value={acc ? `${acc.rejected_pct}%` : '—'} sub={acc ? `${acc.rejected} orders` : ''} color="red" />
        <StatCard label="Forecast Error" value={fore ? `${fore.mean_error_pct}%` : '—'} sub={fore ? `from ${fore.count} outcomes` : ''} color="blue" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Recent Sync</h3>
          {syncResult ? (
            <div className="space-y-2 text-sm text-gray-600">
              <p>Products synced: {syncResult.synced_products}</p>
              <p>Sales records: {syncResult.synced_sales}</p>
              <p>Risk alerts: {syncResult.risk_alerts}</p>
              <p>POs drafted: {syncResult.purchase_orders}</p>
            </div>
          ) : (
            <p className="text-sm text-gray-400">Run a sync to see results</p>
          )}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Forecast Accuracy</h3>
          {fore ? (
            <div className="space-y-2 text-sm text-gray-600">
              <p>Mean error: <span className="font-medium">{fore.mean_error_pct}%</span></p>
              <p>Range: {fore.min_error_pct}% – {fore.max_error_pct}%</p>
              <p>Stockout rate: {fore.stockout_rate}%</p>
            </div>
          ) : (
            <p className="text-sm text-gray-400">Not enough outcome data yet</p>
          )}
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  const colors: Record<string, string> = {
    green: 'border-green-200 bg-green-50 text-green-700',
    amber: 'border-amber-200 bg-amber-50 text-amber-700',
    red: 'border-red-200 bg-red-50 text-red-700',
    blue: 'border-blue-200 bg-blue-50 text-blue-700',
  }
  return (
    <div className={`rounded-xl border p-4 ${colors[color] || colors.blue}`}>
      <p className="text-xs font-medium opacity-75">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
      <p className="text-xs opacity-75 mt-0.5">{sub}</p>
    </div>
  )
}

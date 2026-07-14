import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { api, type SkuSummary } from '../lib/api'

export default function Inventory() {
  const [items, setItems] = useState<SkuSummary[]>([])

  useEffect(() => {
    api.getSkus().then(setItems).catch(() => {})
  }, [])

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h2 className="text-xl font-medium">Inventory</h2>
        <p className="mt-1 text-[13.5px] text-ink-muted">All SKUs and stock levels</p>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13.5px]">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase tracking-wide text-ink-faint">
                <th className="px-4 py-2.5 font-medium">SKU</th>
                <th className="px-4 py-2.5 font-medium">Title</th>
                <th className="px-4 py-2.5 text-right font-medium">Stock</th>
                <th className="px-4 py-2.5 font-medium">Location</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-[13px] text-ink-faint">
                    No SKUs found — run a sync first.
                  </td>
                </tr>
              ) : (
                items.map(item => (
                  <tr key={item.id} className="border-b border-border last:border-0 hover:bg-surface-sunken/60">
                    <td className="px-4 py-3 font-mono text-[12px] text-ink-faint">{item.sku_code || item.shopify_variant_id}</td>
                    <td className="px-4 py-3">{item.title}</td>
                    <td className="tabular px-4 py-3 text-right font-medium">{item.current_stock}</td>
                    <td className="px-4 py-3 text-ink-muted">{item.location_id || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </motion.div>
  )
}

import { useEffect, useState } from 'react'
import { api } from '../lib/api'

interface SkuItem {
  id: number
  shopify_variant_id: string
  sku_code: string | null
  title: string
  current_stock: number
  location_id: string | null
}

export default function Inventory() {
  const [items, setItems] = useState<SkuItem[]>([])

  useEffect(() => {
    api.runSync().then(() => {
      setItems([])
    }).catch(() => {})
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Inventory</h2>
        <p className="text-sm text-gray-500 mt-1">All SKUs and stock levels</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="text-left px-4 py-3 font-medium text-gray-500">SKU</th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">Title</th>
                <th className="text-right px-4 py-3 font-medium text-gray-500">Stock</th>
                <th className="text-left px-4 py-3 font-medium text-gray-500">Location</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                    Run a sync from the Dashboard to load inventory data
                  </td>
                </tr>
              ) : (
                items.map(item => (
                  <tr key={item.id} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs">{item.sku_code || item.shopify_variant_id}</td>
                    <td className="px-4 py-3">{item.title}</td>
                    <td className="px-4 py-3 text-right font-medium">{item.current_stock}</td>
                    <td className="px-4 py-3 text-gray-500">{item.location_id || '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

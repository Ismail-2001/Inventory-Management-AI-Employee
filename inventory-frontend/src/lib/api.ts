const BASE = '/api/v1'

let _apiKey = ''

async function getApiKey(): Promise<string> {
  if (_apiKey) return _apiKey
  try {
    const res = await fetch(`${BASE}/config`)
    const cfg = await res.json()
    _apiKey = cfg.api_key || ''
  } catch {
    _apiKey = ''
  }
  return _apiKey
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const key = await getApiKey()
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(key ? { 'X-API-Key': key } : {}),
      ...options?.headers,
    },
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || `HTTP ${res.status}`)
  }
  return res.json()
}

export interface SkuSummary {
  id: number
  shopify_variant_id: string
  sku_code: string
  title: string
  current_stock: number
  location_id: string | null
}

export interface RiskAlert {
  sku_id: number
  risk_level: string
  reason: string
}

export interface PurchaseOrder {
  id: number
  sku_id: number
  supplier_id: number | null
  status: string
  quantity: number
  unit_cost: number
  total_cost: number
  reasoning_text: string | null
  approved_by: string | null
  approved_at: string | null
  rejected_reason: string | null
  created_at: string
  edited_before_approval: boolean | null
  original_quantity: number | null
}

export interface RunSyncResponse {
  status: string
  synced_products: number
  synced_sales: number
  risk_alerts: number
  purchase_orders: number
  thread_id: string
}

export interface MetricsResponse {
  acceptance: {
    total: number
    accepted_as_is: number
    accepted_as_is_pct: number
    edited_then_approved: number
    edited_then_approved_pct: number
    rejected: number
    rejected_pct: number
  }
  forecast_error: {
    count: number
    mean_error_pct: number
    min_error_pct: number
    max_error_pct: number
    stockout_rate: number
  } | null
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  runSync: () => request<RunSyncResponse>('/run-sync', { method: 'POST' }),
  getMetrics: (days = 30) => request<MetricsResponse>(`/metrics?days=${days}`),
  triggerOutcomeEval: () => request<{ status: string; evaluated: number }>('/evaluate-outcomes', { method: 'POST' }),
  triggerWeekly: () => request<{ status: string; insights_count: number }>('/run-weekly', { method: 'POST' }),
  getSkus: () => request<SkuSummary[]>('/skus'),
  approvePO: (poId: number, quantity?: number) => {
    const params = quantity != null ? `?quantity=${quantity}` : ''
    return request<{ status: string; po_id: number }>(`/po/${poId}/approve${params}`, { method: 'POST' })
  },
  rejectPO: (poId: number, reason?: string) => {
    const params = reason ? `?reason=${encodeURIComponent(reason)}` : ''
    return request<{ status: string; po_id: number }>(`/po/${poId}/reject${params}`, { method: 'POST' })
  },
}

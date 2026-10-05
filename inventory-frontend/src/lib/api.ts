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

export interface ChatAction {
  id: string
  tool: string
  status: 'pending' | 'confirmed' | 'cancelled' | 'expired'
  created_at: string
  expires_at: string
  params: {
    sku_id: number
    sku_code?: string
    title?: string
    supplier_id?: number | null
    quantity: number
    unit_cost: number
    total_cost: number
    reasoning?: string
  }
  po_id?: number
  confirmed_at?: string
  cancelled_at?: string
  expired_at?: string
}

export interface ChatToolTrace {
  name: string
  ok: boolean
  mutating: boolean
  summary: string
  elapsed_ms: number
}

export interface ChatMessageItem {
  id?: number
  role: 'user' | 'assistant'
  content: string
  actions?: ChatAction[]
  tool_trace?: ChatToolTrace[]
  model?: string | null
  conversation_id?: string
  created_at?: string | null
}

export interface ChatConversation {
  conversation_id: string
  message_count: number
  updated_at: string | null
  preview: string
  last_role: string | null
}

export type ChatStreamEvent =
  | { type: 'start'; model: string }
  | { type: 'delta'; text: string }
  | { type: 'tool'; name: string; phase: 'started' | 'finished' | 'failed'; ok: boolean; summary: string; elapsed_ms: number; mutating: boolean }
  | {
      type: 'message'
      conversation_id: string
      content: string
      actions: ChatAction[]
      tool_trace: ChatToolTrace[]
      model: string
      steps: number
      usage: { tokens_in: number; tokens_out: number; cost_usd: number }
    }
  | { type: 'error'; message: string }

/** POST /chat and relay every SSE frame to `onEvent` (start/delta/tool/message/error). */
export async function streamChat(
  payload: { message: string; conversation_id?: string },
  onEvent: (event: ChatStreamEvent) => void,
): Promise<void> {
  const key = await getApiKey()
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(key ? { 'X-API-Key': key } : {}),
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok || !res.body) {
    const err = await res.text()
    throw new Error(err || `HTTP ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const line = frame.split('\n').find(l => l.startsWith('data: '))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice(6)) as ChatStreamEvent)
      } catch {
        // ignore malformed frames (partial writes are already handled by buffering)
      }
    }
  }
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
  getChatHistory: (conversationId: string, limit = 200) =>
    request<{ conversation_id: string; messages: ChatMessageItem[] }>(
      `/chat/history?conversation_id=${encodeURIComponent(conversationId)}&limit=${limit}`,
    ),
  getChatConversations: () => request<{ conversations: ChatConversation[] }>('/chat/conversations'),
  confirmChatAction: (actionId: string, conversationId: string) =>
    request<{ status: string; po_id: number; po_status: string }>(`/chat/actions/${actionId}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId }),
    }),
  cancelChatAction: (actionId: string, conversationId: string) =>
    request<{ status: string; action_id: string }>(`/chat/actions/${actionId}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId }),
    }),
}

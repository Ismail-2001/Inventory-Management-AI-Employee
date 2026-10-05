import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { motion } from 'framer-motion'
import { Bot, Check, Loader2, Plus, Send, User, Wrench, X } from 'lucide-react'
import {
  api,
  streamChat,
  type ChatAction,
  type ChatMessageItem,
  type ChatStreamEvent,
  type ChatToolTrace,
} from '../lib/api'
import type { ChatConversation } from '../lib/api'
import { cn, formatDate } from '../lib/utils'
import { showToast } from '../lib/toast'

interface UiTool extends ChatToolTrace {
  phase: 'started' | 'finished' | 'failed'
}

interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  tools: UiTool[]
  actions: ChatAction[]
  streaming: boolean
}

const SUGGESTIONS = [
  'Which SKUs are below their reorder point?',
  'Draft a PO for SKU-1001, 50 units',
  'How accurate was the forecast last month?',
]

function toolLabel(name: string): string {
  return name.replace(/_/g, ' ')
}

function actionColor(status: ChatAction['status']): string {
  if (status === 'pending') return 'text-warning bg-warning-bg border-warning/20'
  if (status === 'confirmed') return 'text-healthy bg-healthy-bg border-healthy/20'
  if (status === 'cancelled') return 'text-critical bg-critical-bg border-critical/20'
  return 'text-ink-muted bg-surface-sunken border-border-strong'
}

function upsertTool(tools: UiTool[], ev: Extract<ChatStreamEvent, { type: 'tool' }>): UiTool[] {
  const chip: UiTool = {
    name: ev.name,
    ok: ev.ok,
    mutating: ev.mutating,
    summary: ev.summary,
    elapsed_ms: ev.elapsed_ms,
    phase: ev.phase === 'started' ? 'started' : ev.phase === 'failed' ? 'failed' : 'finished',
  }
  if (ev.phase === 'started') return [...tools, chip]
  const idx = tools.map(t => t.name).lastIndexOf(ev.name)
  if (idx === -1) return [...tools, chip]
  const next = [...tools]
  next[idx] = chip
  return next
}

function mapHistory(items: ChatMessageItem[]): UiMessage[] {
  return items.map((m, i) => ({
    id: `h${i}`,
    role: m.role,
    content: m.content,
    tools: (m.tool_trace ?? []).map(t => ({ ...t, phase: 'finished' as const })),
    actions: m.actions ?? [],
    streaming: false,
  }))
}

export default function Chat() {
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [conversations, setConversations] = useState<ChatConversation[]>([])
  const [actingOn, setActingOn] = useState<string | null>(null)
  const idRef = useRef(0)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const nextId = () => `m${++idRef.current}`

  const updateMessage = (id: string, fn: (m: UiMessage) => UiMessage) =>
    setMessages(prev => prev.map(m => (m.id === id ? fn(m) : m)))

  const refreshConversations = async () => {
    try {
      const data = await api.getChatConversations()
      setConversations(data.conversations)
    } catch {
      // conversation sidebar is best-effort
    }
  }

  useEffect(() => {
    void refreshConversations()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: 'end' })
  }, [messages])

  const handleEvent = (id: string, ev: ChatStreamEvent) => {
    if (ev.type === 'delta') {
      updateMessage(id, m => ({ ...m, content: m.content + ev.text }))
      return
    }
    if (ev.type === 'tool') {
      updateMessage(id, m => ({ ...m, tools: upsertTool(m.tools, ev) }))
      return
    }
    if (ev.type === 'message') {
      setConversationId(ev.conversation_id)
      updateMessage(id, m => ({
        ...m,
        content: ev.content,
        actions: ev.actions,
        tools: ev.tool_trace.length
          ? ev.tool_trace.map(t => ({ ...t, phase: 'finished' as const }))
          : m.tools.map(t => ({ ...t, phase: 'finished' as const })),
        streaming: false,
      }))
      void refreshConversations()
      return
    }
    if (ev.type === 'error') {
      updateMessage(id, m => ({ ...m, content: ev.message, streaming: false }))
    }
  }

  const send = async (text: string) => {
    if (busy) return
    const userId = nextId()
    const assistantId = nextId()
    setMessages(prev => [
      ...prev,
      { id: userId, role: 'user', content: text, tools: [], actions: [], streaming: false },
      { id: assistantId, role: 'assistant', content: '', tools: [], actions: [], streaming: true },
    ])
    setInput('')
    setBusy(true)
    try {
      await streamChat({ message: text, conversation_id: conversationId ?? undefined }, ev =>
        handleEvent(assistantId, ev),
      )
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Something went wrong'
      updateMessage(assistantId, m => ({ ...m, content: message, streaming: false }))
      showToast(message)
    } finally {
      setBusy(false)
    }
  }

  const submit = () => {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    void send(text)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const newChat = () => {
    if (busy) return
    setMessages([])
    setConversationId(null)
  }

  const openConversation = async (id: string) => {
    if (busy) return
    setBusy(true)
    try {
      const data = await api.getChatHistory(id)
      setConversationId(id)
      setMessages(mapHistory(data.messages))
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to load conversation')
    } finally {
      setBusy(false)
    }
  }

  const confirmAction = async (action: ChatAction) => {
    if (!conversationId || actingOn) return
    setActingOn(action.id)
    try {
      const res = await api.confirmChatAction(action.id, conversationId)
      updateAction(action.id, 'confirmed', res.po_id)
      showToast(`PO #${res.po_id} created — pending approval`)
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to confirm action')
    } finally {
      setActingOn(null)
    }
  }

  const cancelAction = async (action: ChatAction) => {
    if (!conversationId || actingOn) return
    setActingOn(action.id)
    try {
      await api.cancelChatAction(action.id, conversationId)
      updateAction(action.id, 'cancelled')
      showToast('Action cancelled')
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to cancel action')
    } finally {
      setActingOn(null)
    }
  }

  const updateAction = (actionId: string, status: ChatAction['status'], poId?: number) => {
    setMessages(prev =>
      prev.map(m => ({
        ...m,
        actions: m.actions.map(a =>
          a.id === actionId ? { ...a, status, ...(poId != null ? { po_id: poId } : {}) } : a,
        ),
      })),
    )
  }

  const renderAction = (action: ChatAction) => {
    const pending = action.status === 'pending'
    return (
      <div
        key={action.id}
        className="mt-3 rounded-lg border border-warning/30 bg-warning-bg/60 p-3.5"
        data-testid="chat-action-card"
      >
        <div className="mb-2.5 flex items-center justify-between gap-3">
          <p className="text-[12.5px] font-medium">
            {action.tool === 'draft_purchase_order' ? 'Proposed purchase order' : 'Proposed action'}
          </p>
          <span
            className={cn(
              'rounded-full border px-2 py-0.5 text-[11px] font-medium',
              actionColor(action.status),
            )}
          >
            {action.status}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-3 rounded-md bg-surface px-3 py-2">
          <div>
            <p className="text-[11px] text-ink-faint">SKU</p>
            <p className="tabular text-[13.5px] font-medium">
              {action.params.sku_code ?? `#${action.params.sku_id}`}
            </p>
          </div>
          <div>
            <p className="text-[11px] text-ink-faint">Quantity</p>
            <p className="tabular text-[13.5px] font-medium">{action.params.quantity} units</p>
          </div>
          <div>
            <p className="text-[11px] text-ink-faint">Total</p>
            <p className="tabular text-[13.5px] font-medium">${action.params.total_cost.toFixed(2)}</p>
          </div>
        </div>
        {action.params.reasoning && (
          <p className="mt-2.5 font-mono text-[12px] leading-relaxed text-ink-muted">
            {action.params.reasoning}
          </p>
        )}
        {action.status === 'confirmed' && action.po_id != null && (
          <p className="mt-2 text-[12.5px] text-healthy">PO #{action.po_id} created — pending approval</p>
        )}
        {action.status === 'expired' && (
          <p className="mt-2 text-[12.5px] text-ink-muted">Expired — ask the agent to draft a new one.</p>
        )}
        {pending && (
          <div className="mt-3 flex gap-2">
            <button
              onClick={() => void confirmAction(action)}
              disabled={actingOn !== null}
              className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-[13px] font-medium text-ink-on-accent transition-colors hover:bg-accent-hover disabled:pointer-events-none disabled:opacity-40"
            >
              {actingOn === action.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              Confirm
            </button>
            <button
              onClick={() => void cancelAction(action)}
              disabled={actingOn !== null}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[13px] font-medium text-ink-muted transition-colors hover:text-ink disabled:pointer-events-none disabled:opacity-40"
            >
              <X className="h-3.5 w-3.5" />
              Cancel
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-medium">Ask the Inventory Agent</h2>
          <p className="mt-1 text-[13.5px] text-ink-muted">
            Real answers from your inventory data. Nothing changes without your approval.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={newChat}
            disabled={busy}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[13px] font-medium text-ink-muted transition-colors hover:text-ink disabled:pointer-events-none disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5" />
            New chat
          </button>
          <select
            aria-label="Recent conversations"
            value={conversationId ?? ''}
            onChange={e => {
              if (e.target.value) void openConversation(e.target.value)
            }}
            className="h-8 max-w-56 rounded-md border border-border bg-surface px-2 text-[13px] text-ink-muted"
          >
            <option value="">Recent conversations</option>
            {conversations.map(c => (
              <option key={c.conversation_id} value={c.conversation_id}>
                {c.preview.slice(0, 40) || 'Conversation'} · {formatDate(c.updated_at)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-border bg-surface">
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-bg text-accent">
                <Bot className="h-6 w-6" />
              </div>
              <div>
                <p className="text-[15px] font-medium">What should we look at?</p>
                <p className="mx-auto mt-1 max-w-sm text-[13px] text-ink-muted">
                  Ask about stock levels, forecasts, or suppliers — the agent reads live data and proposes
                  actions you approve.
                </p>
              </div>
              <div className="flex max-w-lg flex-wrap justify-center gap-2">
                {SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    onClick={() => {
                      setInput('')
                      void send(s)
                    }}
                    disabled={busy}
                    className="rounded-full border border-border bg-surface px-3 py-1.5 text-[12.5px] text-ink-muted transition-colors hover:border-accent/40 hover:text-accent disabled:pointer-events-none disabled:opacity-40"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map(msg =>
              msg.role === 'user' ? (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className="flex justify-end"
                >
                  <div className="flex max-w-[75%] items-start gap-2 rounded-lg rounded-br-sm bg-accent-bg px-3.5 py-2.5">
                    <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed">{msg.content}</p>
                    <User className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                  </div>
                </motion.div>
              ) : (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className="flex justify-start"
                >
                  <div className="max-w-[85%] rounded-lg rounded-bl-sm border border-border bg-surface-sunken px-3.5 py-2.5">
                    <div className="mb-1.5 flex items-center gap-1.5 text-ink-faint">
                      <Bot className="h-3.5 w-3.5" />
                      <span className="text-[11px] font-medium uppercase tracking-wide">Agent</span>
                    </div>
                    {msg.tools.length > 0 && (
                      <div className="mb-2 flex flex-wrap gap-1.5">
                        {msg.tools.map((t, i) => (
                          <span
                            key={`${t.name}-${i}`}
                            className={cn(
                              'inline-flex max-w-[280px] items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px]',
                              t.phase === 'started'
                                ? 'animate-pulse border-accent/30 bg-accent-bg text-accent'
                                : t.ok
                                  ? 'border-healthy/30 bg-healthy-bg text-healthy'
                                  : 'border-critical/30 bg-critical-bg text-critical',
                            )}
                          >
                            <Wrench className="h-3 w-3 shrink-0" />
                            <span className="truncate">
                              {toolLabel(t.name)}
                              {t.phase !== 'started' && t.summary ? ` · ${t.summary}` : ''}
                            </span>
                          </span>
                        ))}
                      </div>
                    )}
                    {msg.content ? (
                      <p className="whitespace-pre-wrap text-[13.5px] leading-relaxed">{msg.content}</p>
                    ) : msg.streaming ? (
                      <span className="inline-flex gap-1 py-1">
                        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-faint [animation-delay:0ms]" />
                        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-faint [animation-delay:150ms]" />
                        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-faint [animation-delay:300ms]" />
                      </span>
                    ) : null}
                    {msg.actions.map(renderAction)}
                  </div>
                </motion.div>
              ),
            )
          )}
          <div ref={bottomRef} />
        </div>

        <form
          onSubmit={e => {
            e.preventDefault()
            submit()
          }}
          className="flex items-end gap-2 border-t border-border p-3"
        >
          <textarea
            rows={2}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask about stock, forecasts, or draft a PO…"
            aria-label="Chat message"
            className="min-h-0 flex-1 resize-none rounded-md border border-border-strong bg-surface px-3 py-2 text-[13.5px] leading-relaxed placeholder:text-ink-faint focus:border-accent/50 focus:outline-none"
          />
          <motion.button
            whileTap={{ scale: 0.96 }}
            type="submit"
            aria-label="Send"
            disabled={busy || !input.trim()}
            className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-accent text-ink-on-accent transition-colors hover:bg-accent-hover disabled:pointer-events-none disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
          </motion.button>
        </form>
      </div>
    </div>
  )
}

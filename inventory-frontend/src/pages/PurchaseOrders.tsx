import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, X } from 'lucide-react'
import { api, type PurchaseOrder } from '../lib/api'
import { cn, formatDate, statusColor } from '../lib/utils'
import { showToast } from '../lib/toast'

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.08 } },
}

export default function PurchaseOrders() {
  const [orders, setOrders] = useState<PurchaseOrder[]>([])
  const [approving, setApproving] = useState<number | null>(null)
  const [justResolved, setJustResolved] = useState<{ id: number; kind: 'approved' | 'rejected' } | null>(null)
  const [rejectingId, setRejectingId] = useState<number | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const fetchOrders = async () => {
    try {
      const res = await fetch('/api/v1/po', { headers: { 'X-API-Key': 'demo-key-2024' } })
      if (res.ok) {
        const data = await res.json()
        setOrders(Array.isArray(data) ? data : [])
      }
    } catch { }
  }

  useEffect(() => { fetchOrders() }, [])

  const handleApprove = async (po: PurchaseOrder, e: React.FormEvent) => {
    e.preventDefault()
    setApproving(po.id)
    try {
      const form = e.target as HTMLFormElement
      const data = new FormData(form)
      const qty = data.get('quantity') ? Number(data.get('quantity')) : undefined
      await api.approvePO(po.id, qty)
      setJustResolved({ id: po.id, kind: 'approved' })
      setTimeout(() => setJustResolved(null), 900)
      showToast('PO approved')
      await fetchOrders()
    } catch (err: any) {
      showToast(err.message)
    } finally {
      setApproving(null)
    }
  }

  const handleReject = async (po: PurchaseOrder) => {
    setApproving(po.id)
    try {
      await api.rejectPO(po.id, rejectReason || undefined)
      setJustResolved({ id: po.id, kind: 'rejected' })
      setTimeout(() => setJustResolved(null), 900)
      setRejectingId(null)
      setRejectReason('')
      showToast('PO rejected')
      await fetchOrders()
    } catch (err: any) {
      showToast(err.message)
    } finally {
      setApproving(null)
    }
  }

  const pending = orders.filter(o => o.status === 'pending_approval')
  const history = orders.filter(o => o.status !== 'pending_approval')

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-medium">Purchase Orders</h2>
        <p className="mt-1 text-[13.5px] text-ink-muted">Nothing here goes to a supplier until you approve it.</p>
      </div>

      {pending.length > 0 && (
        <section>
          <h3 className="mb-3 text-[13px] font-medium text-ink-muted">Awaiting your decision · {pending.length}</h3>
          <motion.div variants={container} initial="hidden" animate="show" className="space-y-3">
            <AnimatePresence>
              {pending.map(po => (
                <motion.div
                  key={po.id}
                  layout
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.97, transition: { duration: 0.25 } }}
                  transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                  className="relative overflow-hidden rounded-lg border border-border bg-surface p-5"
                >
                  <AnimatePresence>
                    {justResolved?.id === po.id && (
                      <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className={cn(
                          'absolute inset-0 z-20 flex items-center justify-center gap-2 text-sm font-medium',
                          justResolved.kind === 'approved' ? 'bg-healthy-bg text-healthy' : 'bg-critical-bg text-critical',
                        )}
                      >
                        <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 400, damping: 15 }}>
                          {justResolved.kind === 'approved' ? <Check className="h-5 w-5" /> : <X className="h-5 w-5" />}
                        </motion.span>
                        {justResolved.kind === 'approved' ? 'Approved' : 'Rejected'}
                      </motion.div>
                    )}
                  </AnimatePresence>

                  <div className="mb-3 flex items-start justify-between">
                    <div>
                      <p className="font-medium">PO #{po.id}</p>
                      <p className="mt-0.5 text-[13px] text-ink-muted">Created {formatDate(po.created_at)}</p>
                    </div>
                    <span className={cn('rounded-full border px-2.5 py-0.5 text-xs font-medium', statusColor(po.status))}>
                      {po.status.replace('_', ' ')}
                    </span>
                  </div>

                  <div className="mb-3 grid grid-cols-2 gap-4 rounded-md bg-surface-sunken p-3">
                    <div>
                      <p className="text-[11px] text-ink-faint">Quantity</p>
                      <p className="tabular mt-0.5 text-[15px] font-medium">
                        {po.quantity} units
                        {po.original_quantity && po.edited_before_approval && (
                          <span className="ml-2 text-[12px] font-normal text-ink-faint">(originally {po.original_quantity})</span>
                        )}
                      </p>
                    </div>
                    <div>
                      <p className="text-[11px] text-ink-faint">Total</p>
                      <p className="tabular mt-0.5 text-[15px] font-medium">${po.total_cost.toFixed(2)}</p>
                    </div>
                  </div>

                  {po.reasoning_text && (
                    <div className="mb-4 rounded-md border border-border p-3">
                      <p className="mb-1 text-[11px] uppercase tracking-wide text-ink-faint">Why</p>
                      <p className="font-mono text-[12.5px] leading-relaxed text-ink-muted">{po.reasoning_text}</p>
                    </div>
                  )}

                  <div className="flex gap-2">
                    <form onSubmit={(e) => handleApprove(po, e)} className="flex items-center gap-2">
                      <input
                        name="quantity"
                        type="number"
                        defaultValue={po.quantity}
                        className="tabular h-8 w-20 rounded-md border border-border-strong bg-surface px-2 text-[13px]"
                      />
                      <motion.button
                        whileHover={{ scale: 1.04 }}
                        whileTap={{ scale: 0.96 }}
                        type="submit"
                        disabled={approving === po.id}
                        className="inline-flex h-8 items-center justify-center rounded-md bg-accent px-3 text-[13px] font-medium text-ink-on-accent transition-colors hover:bg-accent-hover disabled:pointer-events-none disabled:opacity-40"
                      >
                        {approving === po.id ? '…' : 'Approve'}
                      </motion.button>
                    </form>

                    {rejectingId === po.id ? (
                      <form
                        onSubmit={(e) => { e.preventDefault(); handleReject(po) }}
                        className="flex items-center gap-1.5"
                      >
                        <input
                          autoFocus
                          value={rejectReason}
                          onChange={e => setRejectReason(e.target.value)}
                          placeholder="Reason (optional)"
                          className="h-8 w-40 rounded-md border border-border-strong bg-surface px-2 text-[13px]"
                        />
                        <motion.button
                          whileHover={{ scale: 1.04 }}
                          whileTap={{ scale: 0.96 }}
                          type="submit"
                          disabled={approving === po.id}
                          className="inline-flex h-8 items-center justify-center rounded-md border border-critical/30 bg-surface px-3 text-[13px] font-medium text-critical transition-colors hover:bg-critical-bg disabled:pointer-events-none disabled:opacity-40"
                        >
                          {approving === po.id ? '…' : 'Confirm'}
                        </motion.button>
                        <motion.button
                          whileHover={{ scale: 1.04 }}
                          whileTap={{ scale: 0.96 }}
                          type="button"
                          onClick={() => { setRejectingId(null); setRejectReason('') }}
                          className="inline-flex h-8 items-center justify-center rounded-md border border-border bg-surface px-3 text-[13px] font-medium text-ink-muted transition-colors hover:text-ink"
                        >
                          Cancel
                        </motion.button>
                      </form>
                    ) : (
                      <motion.button
                        whileHover={{ scale: 1.04 }}
                        whileTap={{ scale: 0.96 }}
                        onClick={() => setRejectingId(po.id)}
                        disabled={approving === po.id}
                        className="inline-flex h-8 items-center justify-center rounded-md border border-critical/30 bg-surface px-3 text-[13px] font-medium text-critical transition-colors hover:bg-critical-bg disabled:pointer-events-none disabled:opacity-40"
                      >
                        Reject
                      </motion.button>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </motion.div>
        </section>
      )}

      <section>
        <h3 className="mb-3 text-[13px] font-medium text-ink-muted">History</h3>
        {history.length === 0 ? (
          <p className="text-[13px] text-ink-faint">No PO history yet</p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border bg-surface">
            <table className="w-full text-left text-[13.5px]">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wide text-ink-faint">
                  <th className="px-4 py-2.5 font-medium">PO</th>
                  <th className="px-4 py-2.5 text-right font-medium">Qty</th>
                  <th className="px-4 py-2.5 text-right font-medium">Total</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {history.map((po, i) => (
                  <motion.tr
                    key={po.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: i * 0.03 }}
                    className="border-b border-border last:border-0 hover:bg-surface-sunken/60"
                  >
                    <td className="px-4 py-3 font-medium">#{po.id}</td>
                    <td className="tabular px-4 py-3 text-right">{po.quantity}</td>
                    <td className="tabular px-4 py-3 text-right">${po.total_cost.toFixed(2)}</td>
                    <td className="px-4 py-3">
                      <span className={cn('rounded-full border px-2 py-0.5 text-xs font-medium', statusColor(po.status))}>
                        {po.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-ink-muted">{formatDate(po.created_at)}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

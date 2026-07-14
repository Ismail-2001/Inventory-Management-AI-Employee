import { Link, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { LayoutGrid, ClipboardCheck, Boxes, BarChart3, Settings as SettingsIcon } from 'lucide-react'
import { cn } from '../lib/utils'
import { onToast } from '../lib/toast'

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutGrid },
  { path: '/inventory', label: 'Inventory', icon: Boxes },
  { path: '/purchase-orders', label: 'Purchase Orders', icon: ClipboardCheck },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/settings', label: 'Settings', icon: SettingsIcon },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const [toasts, setToasts] = useState<{ id: number; msg: string }[]>([])

  useEffect(() => {
    return onToast(msg => {
      const id = Date.now()
      setToasts(prev => [...prev, { id, msg }])
      setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3000)
    })
  }, [])

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-surface">
        <div className="flex items-center gap-2 px-5 py-5">
          <motion.div
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', stiffness: 300, damping: 20 }}
            className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-accent to-accent-hover text-ink-on-accent shadow-[0_2px_10px_-2px_rgba(43,58,103,0.5)]"
          >
            <Boxes className="h-4 w-4" />
          </motion.div>
          <div>
            <p className="text-sm font-medium leading-none">Inventory</p>
            <p className="mt-1 text-[11px] leading-none text-ink-faint">Inventory Employee</p>
          </div>
        </div>
        <nav className="relative flex-1 space-y-0.5 px-3">
          {navItems.map(item => {
            const Icon = item.icon
            const active = location.pathname === item.path
            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  'relative flex items-center gap-2.5 rounded-md px-3 py-2 text-[13.5px] transition-colors',
                  active ? 'font-medium text-accent' : 'text-ink-muted hover:bg-surface-sunken hover:text-ink',
                )}
              >
                {active && (
                  <motion.div
                    layoutId="nav-active-pill"
                    className="absolute inset-0 rounded-md bg-accent-bg"
                    transition={{ type: 'spring', stiffness: 400, damping: 32 }}
                  />
                )}
                <Icon className="relative z-10 h-4 w-4" />
                <span className="relative z-10">{item.label}</span>
              </Link>
            )
          })}
        </nav>
        <div className="border-t border-border px-4 py-4">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-healthy/30 bg-healthy-bg px-2 py-0.5 font-mono text-[11px] font-medium text-healthy">
            <span className="h-1.5 w-1.5 rounded-full bg-healthy" />
            Connected
          </span>
        </div>
      </aside>
      <main className="flex-1 overflow-auto bg-paper p-6">
        {children}
      </main>

      {/* Toast container */}
      <div className="fixed right-4 top-4 z-50 flex flex-col gap-2">
        {toasts.map(t => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="rounded-lg border border-border bg-surface px-4 py-3 text-[13px] font-medium text-ink shadow-lg"
          >
            {t.msg}
          </motion.div>
        ))}
      </div>
    </div>
  )
}

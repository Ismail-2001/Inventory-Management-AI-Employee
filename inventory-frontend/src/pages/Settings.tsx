import { motion } from 'framer-motion'

export default function Settings() {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
      <div>
        <h2 className="text-xl font-medium">Settings</h2>
        <p className="mt-1 text-[13.5px] text-ink-muted">Configure the inventory agent</p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <motion.div whileHover={{ y: -2 }} className="rounded-lg border border-border bg-surface p-5 transition-shadow hover:shadow-md">
          <h3 className="mb-4 text-[13px] font-medium text-ink-muted">API Configuration</h3>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-[11px] text-ink-faint">API Key</label>
              <input
                type="password"
                defaultValue="********"
                readOnly
                className="h-9 w-full rounded-md border border-border-strong bg-surface-sunken px-3 text-[13px] text-ink-muted"
              />
            </div>
            <p className="font-mono text-[11px] text-ink-faint">
              Configure via <code className="rounded bg-surface-sunken px-1">X-API-Key</code> header or <code className="rounded bg-surface-sunken px-1">?api_key=</code> query param.
            </p>
          </div>
        </motion.div>

        <motion.div whileHover={{ y: -2 }} className="rounded-lg border border-border bg-surface p-5 transition-shadow hover:shadow-md">
          <h3 className="mb-4 text-[13px] font-medium text-ink-muted">Services</h3>
          <div className="space-y-2.5">
            <ServiceRow name="Shopify Sync" status="connected" />
            <ServiceRow name="Slack Notifications" status="configured" />
            <ServiceRow name="Postgres Database" status="connected" />
            <ServiceRow name="LangGraph Agent" status="active" />
          </div>
        </motion.div>

        <motion.div whileHover={{ y: -2 }} className="rounded-lg border border-border bg-surface p-5 transition-shadow hover:shadow-md">
          <h3 className="mb-4 text-[13px] font-medium text-ink-muted">Environment</h3>
          <div className="space-y-1.5 font-mono text-[12.5px] text-ink-muted">
            <p><span className="text-ink-faint">Backend:</span> FastAPI</p>
            <p><span className="text-ink-faint">Database:</span> PostgreSQL 16</p>
            <p><span className="text-ink-faint">Orchestrator:</span> LangGraph</p>
            <p><span className="text-ink-faint">Frontend:</span> React + Vite + Tailwind</p>
          </div>
        </motion.div>

        <motion.div whileHover={{ y: -2 }} className="rounded-lg border border-border bg-surface p-5 transition-shadow hover:shadow-md">
          <h3 className="mb-4 text-[13px] font-medium text-ink-muted">About</h3>
          <div className="space-y-2 text-[13px] text-ink-muted">
            <p>AI Inventory Employee #2 — a robust, testable agent for inventory management.</p>
            <p className="text-[11px] text-ink-faint">v1.0.0 · Phase 1–3 Complete</p>
          </div>
        </motion.div>
      </div>
    </motion.div>
  )
}

function ServiceRow({ name, status }: { name: string; status: string }) {
  const dotColor =
    status === 'connected' ? 'bg-healthy' :
    status === 'active' ? 'bg-accent' :
    'bg-warning'
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[13px]">{name}</span>
      <span className="flex items-center gap-1.5 font-mono text-[11px] text-ink-faint">
        <motion.span animate={{ opacity: [1, 0.4, 1] }} transition={{ repeat: Infinity, duration: 2 }} className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
        {status}
      </span>
    </div>
  )
}

export default function Settings() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-gray-900">Settings</h2>
        <p className="text-sm text-gray-500 mt-1">Configure the inventory agent</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">API Configuration</h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1">API Key</label>
              <input
                type="password"
                defaultValue="********"
                readOnly
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg bg-gray-50 text-gray-500"
              />
            </div>
            <p className="text-xs text-gray-400">
              Configure via <code className="bg-gray-100 px-1 rounded">X-API-Key</code> header or <code className="bg-gray-100 px-1 rounded">?api_key=</code> query param.
            </p>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Services</h3>
          <div className="space-y-3">
            <ServiceRow name="Shopify Sync" status="connected" />
            <ServiceRow name="Slack Notifications" status="configured" />
            <ServiceRow name="Postgres Database" status="connected" />
            <ServiceRow name="LangGraph Agent" status="active" />
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Environment</h3>
          <div className="space-y-2 text-sm text-gray-600">
            <p><span className="text-gray-400">Backend:</span> FastAPI</p>
            <p><span className="text-gray-400">Database:</span> PostgreSQL 16</p>
            <p><span className="text-gray-400">Orchestrator:</span> LangGraph</p>
            <p><span className="text-gray-400">Frontend:</span> React + Vite + Tailwind</p>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">About</h3>
          <div className="space-y-2 text-sm text-gray-600">
            <p>AI Inventory Employee #2 — a robust, testable agent for inventory management.</p>
            <p className="text-xs text-gray-400 mt-2">v1.0.0 &middot; Phase 1-3 Complete</p>
          </div>
        </div>
      </div>
    </div>
  )
}

function ServiceRow({ name, status }: { name: string; status: string }) {
  const dotColor =
    status === 'connected' ? 'bg-green-400' :
    status === 'active' ? 'bg-blue-400' :
    'bg-amber-400'
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-sm text-gray-700">{name}</span>
      <span className="flex items-center gap-1.5 text-xs text-gray-500">
        <span className={`w-2 h-2 rounded-full ${dotColor}`} />
        {status}
      </span>
    </div>
  )
}

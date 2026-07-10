import { Link, useLocation } from 'react-router-dom'
import { cn } from '../lib/utils'

const navItems = [
  { path: '/', label: 'Dashboard', icon: '◉' },
  { path: '/inventory', label: 'Inventory', icon: '▤' },
  { path: '/purchase-orders', label: 'Purchase Orders', icon: '📋' },
  { path: '/analytics', label: 'Analytics', icon: '📊' },
  { path: '/settings', label: 'Settings', icon: '⚙' },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()

  return (
    <div className="flex h-screen bg-gray-50">
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-5 border-b border-gray-100">
          <h1 className="text-lg font-bold text-gray-900">Inventory Agent</h1>
          <p className="text-xs text-gray-500 mt-0.5">AI Employee #2</p>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(item => (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                location.pathname === item.path
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-gray-600 hover:bg-gray-100',
              )}
            >
              <span className="text-lg">{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="p-4 border-t border-gray-100 text-xs text-gray-400">
          v1.0.0
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-6">
        {children}
      </main>
    </div>
  )
}

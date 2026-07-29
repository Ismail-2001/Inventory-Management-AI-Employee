export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ')
}

export function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })
}

export function statusColor(status: string): string {
  switch (status) {
    case 'approved': return 'text-healthy bg-healthy-bg border-healthy/20'
    case 'rejected': return 'text-critical bg-critical-bg border-critical/20'
    case 'pending_approval': return 'text-warning bg-warning-bg border-warning/20'
    case 'draft': return 'text-ink-muted bg-surface-sunken border-border-strong'
    default: return 'text-ink-muted bg-surface-sunken border-border-strong'
  }
}

export function riskColor(level: string): string {
  switch (level) {
    case 'critical': return 'text-critical bg-critical-bg'
    case 'warning': return 'text-warning bg-warning-bg'
    default: return 'text-healthy bg-healthy-bg'
  }
}

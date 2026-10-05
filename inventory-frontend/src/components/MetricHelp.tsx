import { useEffect, useRef, useState } from 'react'
import { Info } from 'lucide-react'

export function MetricHelp({ text, label }: { text: string; label?: string }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        aria-label={label ?? 'How this is calculated'}
        aria-expanded={open}
        onClick={() => setOpen(o => !o)}
        className="flex h-5 w-5 items-center justify-center rounded-full text-ink-faint transition-colors hover:bg-surface-sunken hover:text-ink"
      >
        <Info className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div
          role="tooltip"
          className="absolute right-0 top-6 z-40 w-64 rounded-md border border-border bg-surface p-3 text-[12px] leading-relaxed text-ink-muted shadow-lg"
        >
          {text}
        </div>
      )}
    </div>
  )
}

import { describe, it, expect } from 'vitest'
import { cn, formatDate, statusColor, riskColor } from './utils'

describe('cn', () => {
  it('joins class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })

  it('filters falsy values', () => {
    expect(cn('foo', false, null, undefined, '', 'bar')).toBe('foo bar')
  })

  it('returns empty string for no truthy values', () => {
    expect(cn(false, null, undefined, '')).toBe('')
  })
})

describe('formatDate', () => {
  it('returns em dash for null', () => {
    expect(formatDate(null)).toBe('\u2014')
  })

  it('formats ISO date string', () => {
    const result = formatDate('2025-03-15T10:30:00Z')
    expect(result).toContain('Mar')
    expect(result).toContain('15')
    expect(result).toContain('2025')
  })
})

describe('statusColor', () => {
  it('returns healthy classes for approved', () => {
    const result = statusColor('approved')
    expect(result).toContain('text-healthy')
    expect(result).toContain('bg-healthy-bg')
  })

  it('returns critical classes for rejected', () => {
    const result = statusColor('rejected')
    expect(result).toContain('text-critical')
    expect(result).toContain('bg-critical-bg')
  })

  it('returns warning classes for pending_approval', () => {
    const result = statusColor('pending_approval')
    expect(result).toContain('text-warning')
    expect(result).toContain('bg-warning-bg')
  })

  it('returns muted classes for draft', () => {
    const result = statusColor('draft')
    expect(result).toContain('text-ink-muted')
  })

  it('returns default for unknown status', () => {
    const result = statusColor('unknown')
    expect(result).toContain('text-ink-muted')
  })
})

describe('riskColor', () => {
  it('returns critical for critical', () => {
    expect(riskColor('critical')).toContain('text-critical')
  })

  it('returns warning for warning', () => {
    expect(riskColor('warning')).toContain('text-warning')
  })

  it('returns healthy for other levels', () => {
    expect(riskColor('low')).toContain('text-healthy')
  })
})

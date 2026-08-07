import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Analytics from './Analytics'

const mockGetMetrics = vi.fn()
const mockTriggerWeekly = vi.fn()
const mockTriggerOutcomeEval = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    getMetrics: (...args: any[]) => mockGetMetrics(...args),
    triggerWeekly: (...args: any[]) => mockTriggerWeekly(...args),
    triggerOutcomeEval: (...args: any[]) => mockTriggerOutcomeEval(...args),
  },
}))

vi.mock('../lib/toast', () => ({
  showToast: vi.fn(),
}))

beforeEach(() => {
  mockGetMetrics.mockReset()
  mockTriggerWeekly.mockReset()
  mockTriggerOutcomeEval.mockReset()
  mockGetMetrics.mockResolvedValue({
    acceptance: {
      total: 20,
      accepted_as_is: 10,
      accepted_as_is_pct: 50,
      edited_then_approved: 6,
      edited_then_approved_pct: 30,
      rejected: 4,
      rejected_pct: 20,
    },
    forecast_error: {
      count: 15,
      mean_error_pct: 8.2,
      min_error_pct: 1.0,
      max_error_pct: 22.5,
      stockout_rate: 3.0,
    },
  })
})

describe('Analytics', () => {
  it('renders the analytics title', () => {
    render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    )
    expect(screen.getByText('Analytics')).toBeInTheDocument()
    expect(screen.getByText('Agent performance and forecast accuracy')).toBeInTheDocument()
  })

  it('renders action buttons', () => {
    render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    )
    expect(screen.getByText('Evaluate Outcomes')).toBeInTheDocument()
    expect(screen.getByText('Run Weekly Report')).toBeInTheDocument()
  })

  it('displays chart sections after loading', async () => {
    render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('PO Acceptance Rates')).toBeInTheDocument()
    })
    expect(screen.getByText('Forecast Error Distribution')).toBeInTheDocument()
  })

  it('shows empty state when no data', async () => {
    mockGetMetrics.mockResolvedValue({
      acceptance: null,
      forecast_error: null,
    })
    render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('No PO data yet')).toBeInTheDocument()
    })
  })

  it('calls getMetrics on mount', () => {
    render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    )
    expect(mockGetMetrics).toHaveBeenCalledWith(30)
  })
})

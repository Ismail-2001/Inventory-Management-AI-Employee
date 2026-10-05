import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import Dashboard from './Dashboard'
import type { RoiResponse } from '../lib/api'

const mockGetRoi = vi.fn()
const mockRunSync = vi.fn()
const mockShowToast = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    getRoi: (...args: any[]) => mockGetRoi(...args),
    runSync: (...args: any[]) => mockRunSync(...args),
  },
}))

vi.mock('../lib/toast', () => ({
  showToast: (...args: any[]) => mockShowToast(...args),
}))

function makeRoi(): RoiResponse {
  return {
    period: { start: '2026-09-05T00:00:00', end: '2026-10-05T00:00:00', days: 31 },
    operational: {
      stockouts_avoided: { events: 4, units: 120, revenue_protected_usd: 4800 },
      excess_reduction: { units: 45, capital_freed_usd: 1350, trimmed_pos: 3, rejected_pos: 2 },
      forecast_accuracy: {
        ensemble_wmape_pct: 15.2,
        ensemble_bias_pct: -1.1,
        ensemble_count: 42,
        baseline_wmape_pct: 40.5,
        baseline_bias_pct: 4.4,
        baseline_count: 40,
        wmape_improvement_pct: 62.5,
        outcome_mape_pct: 12.5,
        outcome_count: 4,
        series: [
          { date: '2026-10-01', ensemble_wmape_pct: 14.0, baseline_wmape_pct: 38.0 },
          { date: '2026-10-02', ensemble_wmape_pct: 16.5, baseline_wmape_pct: 41.0 },
        ],
      },
      po_decisions: {
        decided: 10,
        accepted: 8,
        rejected: 2,
        accepted_as_is: 5,
        edited_then_approved: 3,
        acceptance_rate_pct: 80,
        avg_hours_to_decision: 4.5,
        decisions_with_timestamp: 6,
        excess_reduction: { units: 45, capital_freed_usd: 1350, trimmed_pos: 3, rejected_pos: 2 },
      },
    },
    efficiency: {
      hours_saved: 2,
      hours_saved_basis: { decided_pos: 10, minutes_per_po: 12 },
      llm: {
        cost_usd: 1.23,
        pipeline_cost_usd: 1.0,
        chat_cost_usd: 0.23,
        calls: 40,
        tokens_in: 12000,
        tokens_out: 3400,
        cost_per_decision_usd: 0.123,
      },
      value_generated_usd: 6150,
      roi_multiple: 5000.4,
      assumptions: { revenue_multiplier: 2, minutes_per_po: 12 },
    },
    health: {
      at_risk: {
        total: 2,
        critical: 1,
        warning: 1,
        skus: [
          { sku_id: 1, sku_code: 'SKU-1', risk_level: 'critical', reason: 'stockout in 3 days' },
          { sku_id: 2, sku_code: 'SKU-2', risk_level: 'warning', reason: 'declining sales' },
        ],
      },
      forecast_confidence: {
        total_forecasts: 50,
        with_intervals: 45,
        coverage_pct: 90,
        distribution: [
          { bucket: 'tight', count: 10 },
          { bucket: 'typical', count: 30 },
          { bucket: 'wide', count: 5 },
        ],
      },
      engine: {
        total_forecasts: 50,
        fallbacks: 5,
        fallback_rate_pct: 10,
        distribution: [
          { model: 'ensemble_v2', count: 45 },
          { model: 'exp_smoothing_v1', count: 5 },
        ],
      },
    },
  }
}

function makeEmptyRoi(): RoiResponse {
  const roi = makeRoi()
  roi.operational.stockouts_avoided = { events: 0, units: 0, revenue_protected_usd: 0 }
  roi.operational.excess_reduction = { units: 0, capital_freed_usd: 0, trimmed_pos: 0, rejected_pos: 0 }
  roi.operational.forecast_accuracy = {
    ensemble_wmape_pct: null,
    ensemble_bias_pct: null,
    ensemble_count: 0,
    baseline_wmape_pct: null,
    baseline_bias_pct: null,
    baseline_count: 0,
    wmape_improvement_pct: null,
    outcome_mape_pct: null,
    outcome_count: 0,
    series: [],
  }
  roi.operational.po_decisions = {
    ...roi.operational.po_decisions,
    decided: 0,
    accepted: 0,
    rejected: 0,
    accepted_as_is: 0,
    edited_then_approved: 0,
    acceptance_rate_pct: 0,
    avg_hours_to_decision: null,
    decisions_with_timestamp: 0,
  }
  roi.efficiency.hours_saved = 0
  roi.efficiency.roi_multiple = null
  roi.efficiency.llm = {
    cost_usd: 0,
    pipeline_cost_usd: 0,
    chat_cost_usd: 0,
    calls: 0,
    tokens_in: 0,
    tokens_out: 0,
    cost_per_decision_usd: null,
  }
  roi.health.at_risk = { total: 0, critical: 0, warning: 0, skus: [] }
  roi.health.forecast_confidence = {
    total_forecasts: 0,
    with_intervals: 0,
    coverage_pct: 0,
    distribution: [
      { bucket: 'tight', count: 0 },
      { bucket: 'typical', count: 0 },
      { bucket: 'wide', count: 0 },
    ],
  }
  roi.health.engine = { total_forecasts: 0, fallbacks: 0, fallback_rate_pct: 0, distribution: [] }
  return roi
}

beforeEach(() => {
  mockGetRoi.mockReset()
  mockRunSync.mockReset()
  mockShowToast.mockReset()
  mockGetRoi.mockResolvedValue(makeRoi())
  mockRunSync.mockResolvedValue({ synced_products: 12, synced_sales: 340, risk_alerts: 3, purchase_orders: 5 })
})

describe('Dashboard', () => {
  it('renders the dashboard heading and subtitle', async () => {
    render(<Dashboard />)
    expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(
      screen.getByText('ROI & performance — see whether the AI Employee is paying for itself.'),
    ).toBeInTheDocument()
  })

  it('renders the Run Sync button', () => {
    render(<Dashboard />)
    expect(screen.getByRole('button', { name: /Run Sync/ })).toBeInTheDocument()
  })

  it('calls getRoi on mount with the default 30-day window', async () => {
    render(<Dashboard />)
    expect(mockGetRoi).toHaveBeenCalledWith({ days: 30 })
    await screen.findByText('Value generated')
  })

  it('shows metric rows after loading', async () => {
    render(<Dashboard />)
    expect(await screen.findByText('Accepted (as-is)')).toBeInTheDocument()
    expect(screen.getByText('Edited then Approved')).toBeInTheDocument()
    expect(screen.getByText('Rejected')).toBeInTheDocument()
    expect(screen.getByText('Forecast Error')).toBeInTheDocument()
    expect(screen.getByText('Forecast Accuracy')).toBeInTheDocument()
    expect(screen.getByText('Recent Sync')).toBeInTheDocument()
    expect(screen.getByText('Run a sync to see results')).toBeInTheDocument()
    expect(screen.getByText('Stockouts avoided')).toBeInTheDocument()
    expect(screen.getByText('At-risk SKUs')).toBeInTheDocument()
    expect(screen.getByText('Engine health')).toBeInTheDocument()
  })

  it('shows computed values from the payload', async () => {
    render(<Dashboard />)
    expect(await screen.findByText('120 units')).toBeInTheDocument()
    expect(screen.getByText('$6,150')).toBeInTheDocument()
    expect(screen.getByText('$1.23')).toBeInTheDocument()
    expect(screen.getByText('5,000.4x')).toBeInTheDocument()
    expect(screen.getAllByText('80%').length).toBeGreaterThan(0)
  })

  it('refetches when a preset range is selected', async () => {
    render(<Dashboard />)
    await screen.findByText('Value generated')
    fireEvent.click(screen.getByRole('button', { name: '7d' }))
    expect(mockGetRoi).toHaveBeenLastCalledWith({ days: 7 })
    await waitFor(() => expect(mockGetRoi).toHaveBeenCalledTimes(2))
  })

  it('refetches when a custom range is applied', async () => {
    render(<Dashboard />)
    await screen.findByText('Value generated')
    fireEvent.click(screen.getByRole('button', { name: 'Custom' }))
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-01-01' } })
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-01-31' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    await waitFor(() => expect(mockGetRoi).toHaveBeenLastCalledWith({ start: '2026-01-01', end: '2026-01-31' }))
  })

  it('opens a methodology popover from a metric help button', async () => {
    render(<Dashboard />)
    await screen.findByText('Value generated')
    const helpButtons = screen.getAllByRole('button', { name: 'How this is calculated' })
    fireEvent.click(helpButtons[0])
    expect(await screen.findByText(/Stockout revenue protected/)).toBeInTheDocument()
  })

  it('runs a sync and shows the result', async () => {
    render(<Dashboard />)
    await screen.findByText('Value generated')
    fireEvent.click(screen.getByRole('button', { name: /Run Sync/ }))
    expect(await screen.findByText(/Synced 12 products, 340 sales/)).toBeInTheDocument()
    expect(mockRunSync).toHaveBeenCalled()
    expect(mockShowToast).toHaveBeenCalledWith('Sync complete — 12 products, 340 sales')
    await waitFor(() => expect(mockGetRoi).toHaveBeenCalledTimes(2))
  })

  it('shows empty states when the window has no activity', async () => {
    mockGetRoi.mockResolvedValue(makeEmptyRoi())
    render(<Dashboard />)
    expect(await screen.findByText('No PO decisions yet')).toBeInTheDocument()
    expect(screen.getByText('Not enough forecast data yet')).toBeInTheDocument()
    expect(screen.getByText('All clear — no SKUs at risk')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('surfaces fetch failures as a toast', async () => {
    mockGetRoi.mockRejectedValue(new Error('boom'))
    render(<Dashboard />)
    await waitFor(() => expect(mockShowToast).toHaveBeenCalledWith('boom'))
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from './Dashboard'

const mockGetMetrics = vi.fn()
const mockRunSync = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    getMetrics: (...args: any[]) => mockGetMetrics(...args),
    runSync: (...args: any[]) => mockRunSync(...args),
  },
}))

vi.mock('../lib/toast', () => ({
  showToast: vi.fn(),
}))

beforeEach(() => {
  mockGetMetrics.mockReset()
  mockRunSync.mockReset()
  mockGetMetrics.mockResolvedValue({
    acceptance: {
      total: 10,
      accepted_as_is: 5,
      accepted_as_is_pct: 50,
      edited_then_approved: 3,
      edited_then_approved_pct: 30,
      rejected: 2,
      rejected_pct: 20,
    },
    forecast_error: {
      count: 8,
      mean_error_pct: 12.5,
      min_error_pct: 2.1,
      max_error_pct: 30.0,
      stockout_rate: 5.0,
    },
  })
})

describe('Dashboard', () => {
  it('renders the dashboard title', () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    )
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Inventory overview and key metrics')).toBeInTheDocument()
  })

  it('renders Run Sync button', () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    )
    expect(screen.getByText('Run Sync')).toBeInTheDocument()
  })

  it('displays metric cards after loading', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('Accepted (as-is)')).toBeInTheDocument()
    })
    expect(screen.getByText('Edited then Approved')).toBeInTheDocument()
    expect(screen.getByText('Rejected')).toBeInTheDocument()
    expect(screen.getByText('Forecast Error')).toBeInTheDocument()
  })

  it('calls getMetrics on mount', () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    )
    expect(mockGetMetrics).toHaveBeenCalledWith(7)
  })

  it('shows "Run a sync to see results" before sync', async () => {
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('Run a sync to see results')).toBeInTheDocument()
    })
  })
})

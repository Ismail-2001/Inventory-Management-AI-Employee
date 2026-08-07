import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PurchaseOrders from './PurchaseOrders'

const mockGet = vi.fn()
const mockApprovePO = vi.fn()
const mockRejectPO = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    approvePO: (...args: any[]) => mockApprovePO(...args),
    rejectPO: (...args: any[]) => mockRejectPO(...args),
  },
}))

vi.mock('../lib/toast', () => ({
  showToast: vi.fn(),
}))

beforeEach(() => {
  mockGet.mockReset()
  mockApprovePO.mockReset()
  mockRejectPO.mockReset()
})

describe('PurchaseOrders', () => {
  it('renders the purchase orders title', () => {
    mockGet.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
    render(
      <MemoryRouter>
        <PurchaseOrders />
      </MemoryRouter>
    )
    expect(screen.getByText('Purchase Orders')).toBeInTheDocument()
    expect(screen.getByText(/Nothing here goes to a supplier/)).toBeInTheDocument()
  })

  it('shows empty history when no orders', async () => {
    mockGet.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 })
    render(
      <MemoryRouter>
        <PurchaseOrders />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('No PO history yet')).toBeInTheDocument()
    })
  })

  it('displays pending orders in awaiting section', async () => {
    mockGet.mockResolvedValue({
      items: [
        { id: 1, sku_id: 10, status: 'pending_approval', quantity: 50, unit_cost: 10, total_cost: 500, reasoning_text: 'Need stock', approved_by: null, approved_at: null, rejected_reason: null, created_at: '2025-01-15T10:00:00Z', edited_before_approval: false, original_quantity: null },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
    render(
      <MemoryRouter>
        <PurchaseOrders />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText(/Awaiting your decision/)).toBeInTheDocument()
    })
    expect(screen.getByText('PO #1')).toBeInTheDocument()
    expect(screen.getByText('50 units')).toBeInTheDocument()
  })

  it('displays approved orders in history', async () => {
    mockGet.mockResolvedValue({
      items: [
        { id: 2, sku_id: 11, status: 'approved', quantity: 30, unit_cost: 15, total_cost: 450, reasoning_text: null, approved_by: 'admin', approved_at: '2025-01-16T10:00:00Z', rejected_reason: null, created_at: '2025-01-14T10:00:00Z', edited_before_approval: false, original_quantity: null },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    })
    render(
      <MemoryRouter>
        <PurchaseOrders />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('History')).toBeInTheDocument()
    })
    expect(screen.getByText('#2')).toBeInTheDocument()
  })
})

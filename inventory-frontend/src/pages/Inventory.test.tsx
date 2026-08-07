import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mockGetSkus = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    getSkus: (...args: any[]) => mockGetSkus(...args),
  },
}))

import Inventory from './Inventory'

beforeEach(() => {
  mockGetSkus.mockReset()
})

describe('Inventory', () => {
  it('renders the inventory title', () => {
    mockGetSkus.mockResolvedValue([])
    render(
      <MemoryRouter>
        <Inventory />
      </MemoryRouter>
    )
    expect(screen.getByText('Inventory')).toBeInTheDocument()
    expect(screen.getByText('All SKUs and stock levels')).toBeInTheDocument()
  })

  it('shows empty state when no SKUs', async () => {
    mockGetSkus.mockResolvedValue([])
    render(
      <MemoryRouter>
        <Inventory />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('No SKUs found — run a sync first.')).toBeInTheDocument()
    })
  })

  it('renders SKU table headers', () => {
    mockGetSkus.mockResolvedValue([])
    render(
      <MemoryRouter>
        <Inventory />
      </MemoryRouter>
    )
    expect(screen.getByText('SKU')).toBeInTheDocument()
    expect(screen.getByText('Title')).toBeInTheDocument()
    expect(screen.getByText('Stock')).toBeInTheDocument()
    expect(screen.getByText('Location')).toBeInTheDocument()
  })

  it('renders SKU rows when data is available', async () => {
    mockGetSkus.mockResolvedValue([
      { id: 1, shopify_variant_id: 'v1', sku_code: 'SKU-001', title: 'Widget', current_stock: 42, location_id: 'WH-A' },
      { id: 2, shopify_variant_id: 'v2', sku_code: 'SKU-002', title: 'Gadget', current_stock: 0, location_id: null },
    ])
    render(
      <MemoryRouter>
        <Inventory />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByText('Widget')).toBeInTheDocument()
    })
    expect(screen.getByText('Gadget')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('WH-A')).toBeInTheDocument()
  })
})

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Layout from './Layout'

vi.mock('../lib/toast', () => ({
  onToast: () => () => {},
}))

describe('Layout', () => {
  it('renders the app title', () => {
    render(
      <MemoryRouter>
        <Layout><div /></Layout>
      </MemoryRouter>
    )
    expect(screen.getByText('Inventory Employee')).toBeInTheDocument()
  })

  it('renders all navigation items', () => {
    render(
      <MemoryRouter>
        <Layout><div /></Layout>
      </MemoryRouter>
    )
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getAllByText('Inventory').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Purchase Orders')).toBeInTheDocument()
    expect(screen.getByText('Analytics')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('renders children inside main', () => {
    render(
      <MemoryRouter>
        <Layout><div>Page content</div></Layout>
      </MemoryRouter>
    )
    expect(screen.getByText('Page content')).toBeInTheDocument()
  })

  it('highlights active nav item based on current route', () => {
    render(
      <MemoryRouter initialEntries={['/inventory']}>
        <Layout><div /></Layout>
      </MemoryRouter>
    )
    const links = screen.getAllByText('Inventory')
    const navLink = links.find(el => el.closest('a'))
    expect(navLink?.closest('a')).toHaveClass('text-accent')
  })
})

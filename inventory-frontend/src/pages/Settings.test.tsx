import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Settings from './Settings'

describe('Settings', () => {
  it('renders the settings title', () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    )
    expect(screen.getByText('Settings')).toBeInTheDocument()
    expect(screen.getByText('Configure the inventory agent')).toBeInTheDocument()
  })

  it('renders API configuration section', () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    )
    expect(screen.getByText('API Configuration')).toBeInTheDocument()
    expect(screen.getByText(/X-API-Key/)).toBeInTheDocument()
  })

  it('renders services section', () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    )
    expect(screen.getByText('Services')).toBeInTheDocument()
    expect(screen.getByText('Shopify Sync')).toBeInTheDocument()
    expect(screen.getByText('Slack Notifications')).toBeInTheDocument()
    expect(screen.getByText('Postgres Database')).toBeInTheDocument()
    expect(screen.getByText('LangGraph Agent')).toBeInTheDocument()
  })

  it('renders environment section', () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    )
    expect(screen.getByText('Environment')).toBeInTheDocument()
    expect(screen.getByText('FastAPI')).toBeInTheDocument()
    expect(screen.getByText('PostgreSQL 16')).toBeInTheDocument()
  })

  it('renders about section', () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    )
    expect(screen.getByText('About')).toBeInTheDocument()
    expect(screen.getByText(/AI Inventory Employee #2/)).toBeInTheDocument()
  })
})

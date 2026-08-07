import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ErrorBoundary from './ErrorBoundary'

function ThrowingComponent() {
  throw new Error('Test error')
}

function GoodComponent() {
  return <div>All good</div>
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <GoodComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('All good')).toBeInTheDocument()
  })

  it('renders default fallback on error', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('Test error')).toBeInTheDocument()
    consoleSpy.mockRestore()
  })

  it('renders custom fallback when provided', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary fallback={<div>Custom error UI</div>}>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('Custom error UI')).toBeInTheDocument()
    consoleSpy.mockRestore()
  })

  it('shows try again button that resets error state', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { userEvent } = await import('@testing-library/user-event')
    const user = userEvent.setup()

    let shouldThrow = true
    function ConditionalThrower() {
      if (shouldThrow) throw new Error('boom')
      return <div>recovered</div>
    }

    const { unmount } = render(
      <ErrorBoundary>
        <ConditionalThrower />
      </ErrorBoundary>
    )

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()

    shouldThrow = false
    await user.click(screen.getByText('Try again'))

    expect(screen.getByText('recovered')).toBeInTheDocument()
    consoleSpy.mockRestore()
    unmount()
  })
})

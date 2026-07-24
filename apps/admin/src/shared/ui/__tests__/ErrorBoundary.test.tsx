import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '../../../test/utils'
import { ErrorBoundary } from '../ErrorBoundary'

vi.mock('../../lib/errorLogger', () => ({
  errorLogger: { capture: vi.fn() },
}))

function ThrowingChild({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error('Test crash')
  return <div>Child content</div>
}

function renderBoundary(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('ErrorBoundary', () => {
  const originalError = console.error
  beforeEach(() => {
    console.error = vi.fn()
  })
  afterEach(() => {
    console.error = originalError
  })

  it('renders children when no error', () => {
    renderBoundary(
      <ErrorBoundary level="route">
        <div>Hello</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })

  it('renders ErrorFallback on child crash', () => {
    renderBoundary(
      <ErrorBoundary level="route">
        <ThrowingChild shouldThrow />
      </ErrorBoundary>
    )
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
  })

  it('shows try again button for route level', () => {
    renderBoundary(
      <ErrorBoundary level="route">
        <ThrowingChild shouldThrow />
      </ErrorBoundary>
    )
    expect(
      screen.getByRole('button', { name: /try again/i })
    ).toBeInTheDocument()
  })

  it('shows reload button for app level', () => {
    renderBoundary(
      <ErrorBoundary level="app">
        <ThrowingChild shouldThrow />
      </ErrorBoundary>
    )
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument()
  })

  it('shows compact section fallback for section level', () => {
    renderBoundary(
      <ErrorBoundary level="section" context="test-section">
        <ThrowingChild shouldThrow />
      </ErrorBoundary>
    )
    expect(
      screen.getByText(/this section encountered an error/i)
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /try again/i })
    ).toBeInTheDocument()
  })

  it('recovers from section error on retry', () => {
    const { rerender } = renderBoundary(
      <ErrorBoundary level="section" context="test-section">
        <ThrowingChild shouldThrow />
      </ErrorBoundary>
    )
    expect(
      screen.getByText(/this section encountered an error/i)
    ).toBeInTheDocument()

    screen.getByRole('button', { name: /try again/i }).click()

    rerender(
      <MemoryRouter>
        <ErrorBoundary level="section" context="test-section">
          <ThrowingChild shouldThrow={false} />
        </ErrorBoundary>
      </MemoryRouter>
    )
    expect(screen.getByText('Child content')).toBeInTheDocument()
  })
})

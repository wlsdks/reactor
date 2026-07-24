import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '../../../test/utils'
import { SectionErrorBoundary } from '../SectionErrorBoundary'
import { errorLogger } from '../../lib/errorLogger'

vi.mock('../../lib/errorLogger', () => ({
  errorLogger: { capture: vi.fn() },
}))

function ThrowingChild({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error('Section crash')
  return <div>Section content</div>
}

function renderBoundary(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('SectionErrorBoundary', () => {
  const originalError = console.error
  beforeEach(() => {
    console.error = vi.fn()
    vi.mocked(errorLogger.capture).mockClear()
  })
  afterEach(() => {
    console.error = originalError
  })

  it('renders children when no error', () => {
    renderBoundary(
      <SectionErrorBoundary name="test-section">
        <div>Working content</div>
      </SectionErrorBoundary>
    )
    expect(screen.getByText('Working content')).toBeInTheDocument()
  })

  it('shows compact section fallback on crash', () => {
    renderBoundary(
      <SectionErrorBoundary name="dashboard">
        <ThrowingChild shouldThrow />
      </SectionErrorBoundary>
    )
    expect(
      screen.getByText(/this section encountered an error/i)
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /try again/i })
    ).toBeInTheDocument()
  })

  it('does not crash the parent when child crashes', () => {
    renderBoundary(
      <div>
        <div>Parent stays alive</div>
        <SectionErrorBoundary name="failing-section">
          <ThrowingChild shouldThrow />
        </SectionErrorBoundary>
      </div>
    )
    expect(screen.getByText('Parent stays alive')).toBeInTheDocument()
    expect(
      screen.getByText(/this section encountered an error/i)
    ).toBeInTheDocument()
  })

  it('forwards the section name to the error logger', () => {
    renderBoundary(
      <SectionErrorBoundary name="rag-cache-tab-cache">
        <ThrowingChild shouldThrow />
      </SectionErrorBoundary>
    )
    expect(errorLogger.capture).toHaveBeenCalledWith(
      expect.any(Error),
      expect.objectContaining({ section: 'rag-cache-tab-cache' })
    )
  })

  it('renders fallback with role="alert" + aria-live for assistive tech', () => {
    const { container } = renderBoundary(
      <SectionErrorBoundary name="dashboard">
        <ThrowingChild shouldThrow />
      </SectionErrorBoundary>
    )
    const alert = container.querySelector('[role="alert"]')
    expect(alert).toBeInTheDocument()
    expect(alert).toHaveAttribute('aria-live', 'assertive')
  })

  it('moves focus to the retry button when fallback mounts', () => {
    renderBoundary(
      <SectionErrorBoundary name="dashboard">
        <ThrowingChild shouldThrow />
      </SectionErrorBoundary>
    )
    expect(screen.getByRole('button', { name: /try again/i })).toHaveFocus()
  })

  it('clicking retry resets boundary state and re-renders children', () => {
    const { rerender } = renderBoundary(
      <SectionErrorBoundary name="dashboard">
        <ThrowingChild shouldThrow />
      </SectionErrorBoundary>
    )
    expect(
      screen.getByText(/this section encountered an error/i)
    ).toBeInTheDocument()

    screen.getByRole('button', { name: /try again/i }).click()

    rerender(
      <MemoryRouter>
        <SectionErrorBoundary name="dashboard">
          <ThrowingChild shouldThrow={false} />
        </SectionErrorBoundary>
      </MemoryRouter>
    )
    expect(screen.getByText('Section content')).toBeInTheDocument()
  })
})

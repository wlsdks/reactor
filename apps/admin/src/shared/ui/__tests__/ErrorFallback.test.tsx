import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '../../../test/utils'
import { ErrorFallback } from '../ErrorFallback'

function renderFallback(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('ErrorFallback', () => {
  it('shows crash title', () => {
    renderFallback(<ErrorFallback level="route" />)
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
  })

  it('shows try again button for route level', () => {
    const onReset = vi.fn()
    renderFallback(<ErrorFallback level="route" onReset={onReset} />)
    const btn = screen.getByRole('button', { name: /try again/i })
    btn.click()
    expect(onReset).toHaveBeenCalled()
  })

  it('shows reload button for app level', () => {
    renderFallback(<ErrorFallback level="app" />)
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument()
  })

  it('shows compact inline error for section level', () => {
    renderFallback(<ErrorFallback level="section" />)
    expect(
      screen.getByText(/this section encountered an error/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/please try again or refresh/i)).toBeInTheDocument()
  })

  it('shows retry button for section level', () => {
    const onReset = vi.fn()
    renderFallback(<ErrorFallback level="section" onReset={onReset} />)
    const btn = screen.getByRole('button', { name: /try again/i })
    btn.click()
    expect(onReset).toHaveBeenCalled()
  })

  it('hides retry button for section level when no onReset', () => {
    renderFallback(<ErrorFallback level="section" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('does not show try again button for route level when no onReset', () => {
    renderFallback(<ErrorFallback level="route" />)
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /try again/i })
    ).not.toBeInTheDocument()
  })

  it('does not show try again button for app level even with onReset', () => {
    const onReset = vi.fn()
    renderFallback(<ErrorFallback level="app" onReset={onReset} />)
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /try again/i })
    ).not.toBeInTheDocument()
  })

  it('reload button calls window.location.reload for app level', () => {
    const reloadMock = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { ...window.location, reload: reloadMock },
      writable: true,
      configurable: true,
    })

    renderFallback(<ErrorFallback level="app" />)
    screen.getByRole('button', { name: /reload/i }).click()
    expect(reloadMock).toHaveBeenCalled()
  })

  it('shows crash description for non-section levels', () => {
    renderFallback(<ErrorFallback level="route" />)
    expect(
      screen.getByText(/try again or move to another page/i)
    ).toBeInTheDocument()
  })

  it('shows report hint for non-section levels', () => {
    renderFallback(<ErrorFallback level="route" />)
    expect(
      screen.getByText(/if the problem persists, contact an administrator/i)
    ).toBeInTheDocument()
  })

  it('renders section-level inline error icon', () => {
    const { container } = renderFallback(<ErrorFallback level="section" />)
    expect(
      container.querySelector('.error-fallback-section-icon')
    ).toBeInTheDocument()
  })

  it('renders non-section level error icon', () => {
    const { container } = renderFallback(<ErrorFallback level="app" />)
    expect(container.querySelector('.error-fallback-icon')).toBeInTheDocument()
  })

  it('exposes role="alert" with aria-live for section level', () => {
    const { container } = renderFallback(<ErrorFallback level="section" />)
    const alert = container.querySelector('[role="alert"]')
    expect(alert).toBeInTheDocument()
    expect(alert).toHaveAttribute('aria-live', 'assertive')
  })

  it('exposes role="alert" with aria-live for route level', () => {
    const { container } = renderFallback(<ErrorFallback level="route" />)
    const alert = container.querySelector('[role="alert"]')
    expect(alert).toBeInTheDocument()
    expect(alert).toHaveAttribute('aria-live', 'assertive')
  })

  it('moves focus to the primary recovery button on mount (route level)', () => {
    const onReset = vi.fn()
    renderFallback(<ErrorFallback level="route" onReset={onReset} />)
    const btn = screen.getByRole('button', { name: /try again/i })
    expect(btn).toHaveFocus()
  })

  it('moves focus to the retry button on mount (section level)', () => {
    const onReset = vi.fn()
    renderFallback(<ErrorFallback level="section" onReset={onReset} />)
    const btn = screen.getByRole('button', { name: /try again/i })
    expect(btn).toHaveFocus()
  })

  it('renders a "go home" link to root for route level', () => {
    renderFallback(<ErrorFallback level="route" onReset={vi.fn()} />)
    const link = screen.getByRole('link', { name: /go home/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute('href', '/')
  })

  it('renders a "go home" link to root for app level', () => {
    renderFallback(<ErrorFallback level="app" />)
    const link = screen.getByRole('link', { name: /go home/i })
    expect(link).toHaveAttribute('href', '/')
  })

  it('does not render a "go home" link for section level', () => {
    renderFallback(<ErrorFallback level="section" onReset={vi.fn()} />)
    expect(
      screen.queryByRole('link', { name: /go home/i })
    ).not.toBeInTheDocument()
  })
})

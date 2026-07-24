import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { StatusBadge as SB } from '../StatusBadge'

describe('StatusBadge', () => {
  it('renders status text', () => {
    render(<SB status="ACTIVE" />)
    expect(screen.getByText('ACTIVE')).toBeInTheDocument()
  })

  it('applies green badge class for ACTIVE', () => {
    const { container } = render(<SB status="ACTIVE" />)
    expect(container.querySelector('.badge-green')).toBeInTheDocument()
  })

  it('applies green badge class for CONNECTED', () => {
    const { container } = render(<SB status="CONNECTED" />)
    expect(container.querySelector('.badge-green')).toBeInTheDocument()
  })

  it('applies green badge class for APPROVED', () => {
    const { container } = render(<SB status="APPROVED" />)
    expect(container.querySelector('.badge-green')).toBeInTheDocument()
  })

  it('applies pending badge class for PENDING (F-9 semantic)', () => {
    const { container } = render(<SB status="PENDING" />)
    expect(container.querySelector('.badge-pending')).toBeInTheDocument()
  })

  it('applies yellow badge class for RUNNING', () => {
    const { container } = render(<SB status="RUNNING" />)
    expect(container.querySelector('.badge-yellow')).toBeInTheDocument()
  })

  it('applies success badge class for SUCCESS (F-9 semantic)', () => {
    const { container } = render(<SB status="SUCCESS" />)
    expect(container.querySelector('.badge-success')).toBeInTheDocument()
  })

  it('applies error badge class for ERROR (F-9 semantic)', () => {
    const { container } = render(<SB status="ERROR" />)
    expect(container.querySelector('.badge-error')).toBeInTheDocument()
  })

  it('applies red badge class for FAILED', () => {
    const { container } = render(<SB status="FAILED" />)
    expect(container.querySelector('.badge-red')).toBeInTheDocument()
  })

  it('applies red badge class for REJECTED', () => {
    const { container } = render(<SB status="REJECTED" />)
    expect(container.querySelector('.badge-red')).toBeInTheDocument()
  })

  it('applies red badge class for TIMED_OUT', () => {
    const { container } = render(<SB status="TIMED_OUT" />)
    expect(container.querySelector('.badge-red')).toBeInTheDocument()
  })

  it('applies gray badge class for DISCONNECTED', () => {
    const { container } = render(<SB status="DISCONNECTED" />)
    expect(container.querySelector('.badge-gray')).toBeInTheDocument()
  })

  it('applies gray badge class for unknown status', () => {
    const { container } = render(<SB status="UNKNOWN_STATUS" />)
    expect(container.querySelector('.badge-gray')).toBeInTheDocument()
  })

  it('is case-insensitive for status matching', () => {
    const { container } = render(<SB status="active" />)
    expect(container.querySelector('.badge-green')).toBeInTheDocument()
  })

  // ── Colorblind-safe icon prefix ──────────────────────────────────────────
  describe('icon prefix (WCAG 1.4.1)', () => {
    it('renders an SVG icon by default alongside the label', () => {
      const { container } = render(<SB status="SUCCESS" />)
      expect(container.querySelector('.badge svg')).toBeInTheDocument()
      expect(screen.getByText('SUCCESS')).toBeInTheDocument()
    })

    it('maps each intent status to a distinct icon shape via data-intent', () => {
      const cases: Array<[string, string]> = [
        ['SUCCESS', 'success'],
        ['WARN', 'warning'],
        ['ERROR', 'error'],
        ['FAILED', 'error'],
        ['PENDING', 'pending'],
        ['RUNNING', 'processing'],
        ['DISCONNECTED', 'neutral'],
      ]
      for (const [status, intent] of cases) {
        const { container, unmount } = render(<SB status={status} />)
        const badge = container.querySelector('.badge')
        expect(badge?.getAttribute('data-intent')).toBe(intent)
        expect(badge?.querySelector('svg')).toBeInTheDocument()
        unmount()
      }
    })

    it('falls back to the neutral dot icon for unknown statuses', () => {
      const { container } = render(<SB status="WHATEVER" />)
      const badge = container.querySelector('.badge')
      expect(badge?.getAttribute('data-intent')).toBe('neutral')
      expect(badge?.querySelector('svg')).toBeInTheDocument()
    })
  })

  describe('hideIcon prop', () => {
    it('renders text only when hideIcon is true', () => {
      const { container } = render(<SB status="SUCCESS" hideIcon />)
      expect(container.querySelector('.badge svg')).not.toBeInTheDocument()
      expect(screen.getByText('SUCCESS')).toBeInTheDocument()
    })
  })

  describe('iconOnly prop', () => {
    it('hides the visible label but exposes it via aria-label', () => {
      const { container } = render(<SB status="SUCCESS" iconOnly />)
      expect(container.querySelector('.badge-icon-only')).toBeInTheDocument()
      expect(container.querySelector('.badge svg')).toBeInTheDocument()
      expect(screen.queryByText('SUCCESS')).not.toBeInTheDocument()
      expect(screen.getByLabelText('SUCCESS')).toBeInTheDocument()
    })

    it('uses the override label for the aria-label when provided', () => {
      render(<SB status="SUCCESS" label="Completed" iconOnly />)
      expect(screen.getByLabelText('Completed')).toBeInTheDocument()
    })
  })
})

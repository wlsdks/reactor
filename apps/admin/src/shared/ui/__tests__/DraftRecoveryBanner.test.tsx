import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import '../../i18n/config'
import { DraftRecoveryBanner } from '../DraftRecoveryBanner'

describe('DraftRecoveryBanner', () => {
  it('renders nothing when open is false', () => {
    const { container } = render(
      <DraftRecoveryBanner
        open={false}
        onAccept={vi.fn()}
        onDismiss={vi.fn()}
      />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders the recovery affordance when open', () => {
    render(
      <DraftRecoveryBanner
        open={true}
        onAccept={vi.fn()}
        onDismiss={vi.fn()}
      />,
    )
    expect(screen.getByTestId('draft-recovery-banner')).toBeInTheDocument()
    expect(screen.getByTestId('draft-recovery-accept')).toBeInTheDocument()
    expect(screen.getByTestId('draft-recovery-dismiss')).toBeInTheDocument()
  })

  it('invokes onAccept when the accept button is clicked', () => {
    const onAccept = vi.fn()
    render(
      <DraftRecoveryBanner
        open={true}
        onAccept={onAccept}
        onDismiss={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('draft-recovery-accept'))
    expect(onAccept).toHaveBeenCalledOnce()
  })

  it('invokes onDismiss when the dismiss button is clicked', () => {
    const onDismiss = vi.fn()
    render(
      <DraftRecoveryBanner
        open={true}
        onAccept={vi.fn()}
        onDismiss={onDismiss}
      />,
    )
    fireEvent.click(screen.getByTestId('draft-recovery-dismiss'))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('uses role="status" with aria-live polite for non-blocking announcement', () => {
    render(
      <DraftRecoveryBanner
        open={true}
        onAccept={vi.fn()}
        onDismiss={vi.fn()}
      />,
    )
    const banner = screen.getByTestId('draft-recovery-banner')
    expect(banner).toHaveAttribute('role', 'status')
    expect(banner).toHaveAttribute('aria-live', 'polite')
  })

  it('renders without a saved-at hint when savedAt is omitted', () => {
    render(
      <DraftRecoveryBanner
        open={true}
        onAccept={vi.fn()}
        onDismiss={vi.fn()}
      />,
    )
    // The savedRelative i18n key contains "전 임시저장됨" / "saved" — when
    // savedAt is omitted, that snippet is not rendered.
    const banner = screen.getByTestId('draft-recovery-banner')
    expect(banner.textContent ?? '').not.toMatch(/saved/i)
  })

  it('renders a relative-time hint when savedAt is provided', () => {
    // 2 hours ago — formatRelativeTimeKo emits "2시간 전".
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString()
    render(
      <DraftRecoveryBanner
        open={true}
        savedAt={twoHoursAgo}
        onAccept={vi.fn()}
        onDismiss={vi.fn()}
      />,
    )
    const banner = screen.getByTestId('draft-recovery-banner')
    // The component now consumes the Korean-localized helper, which reads
    // from the global i18next singleton (initialized via the import above).
    expect(banner.textContent ?? '').toContain('2시간 전')
  })
})

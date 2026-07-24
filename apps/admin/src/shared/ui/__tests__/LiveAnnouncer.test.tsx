import { useEffect } from 'react'
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { LiveAnnouncerProvider, useAnnouncer } from '../LiveAnnouncer'

// Expose the announce function to each test via a module-level ref we
// overwrite inside an effect (so we do not mutate during render).
type AnnounceFn = ReturnType<typeof useAnnouncer>['announce']
const captured: { announce: AnnounceFn | null } = { announce: null }

function AnnouncerBridge() {
  const { announce } = useAnnouncer()
  useEffect(() => {
    captured.announce = announce
    return () => {
      captured.announce = null
    }
  }, [announce])
  return null
}

beforeEach(() => {
  captured.announce = null
})

describe('LiveAnnouncer', () => {
  it('renders polite and assertive aria-live regions inside the provider', () => {
    render(
      <LiveAnnouncerProvider>
        <div>child</div>
      </LiveAnnouncerProvider>,
    )

    const polite = screen.getByTestId('live-announcer-polite')
    const assertive = screen.getByTestId('live-announcer-assertive')

    expect(polite).toHaveAttribute('aria-live', 'polite')
    expect(polite).toHaveAttribute('aria-atomic', 'true')
    expect(polite).toHaveClass('sr-only')

    expect(assertive).toHaveAttribute('aria-live', 'assertive')
    expect(assertive).toHaveAttribute('aria-atomic', 'true')
    expect(assertive).toHaveClass('sr-only')

    // Default content is empty until announce() is called.
    expect(polite.textContent ?? '').toBe('')
    expect(assertive.textContent ?? '').toBe('')
  })

  it('announce() updates the polite region by default', () => {
    render(
      <LiveAnnouncerProvider>
        <AnnouncerBridge />
      </LiveAnnouncerProvider>,
    )

    expect(captured.announce).toBeTypeOf('function')
    act(() => {
      captured.announce?.('Filter applied: 3 of 10 items')
    })

    const polite = screen.getByTestId('live-announcer-polite')
    expect(polite.textContent?.trim()).toBe('Filter applied: 3 of 10 items')

    // Assertive region stays empty.
    const assertive = screen.getByTestId('live-announcer-assertive')
    expect(assertive.textContent?.trim()).toBe('')
  })

  it('announce() with priority: "assertive" updates the assertive region', () => {
    render(
      <LiveAnnouncerProvider>
        <AnnouncerBridge />
      </LiveAnnouncerProvider>,
    )

    act(() => {
      captured.announce?.('Bulk action failed', { priority: 'assertive' })
    })

    const assertive = screen.getByTestId('live-announcer-assertive')
    expect(assertive.textContent?.trim()).toBe('Bulk action failed')

    // Polite region stays empty.
    const polite = screen.getByTestId('live-announcer-polite')
    expect(polite.textContent?.trim()).toBe('')
  })

  it('calling announce twice with the same message still updates the DOM', () => {
    render(
      <LiveAnnouncerProvider>
        <AnnouncerBridge />
      </LiveAnnouncerProvider>,
    )

    act(() => {
      captured.announce?.('Persona deleted')
    })
    const polite = screen.getByTestId('live-announcer-polite')
    const first = polite.textContent
    act(() => {
      captured.announce?.('Persona deleted')
    })
    const second = polite.textContent
    // The counter toggle means text differs by trailing whitespace even when
    // callers pass the same message — this is what forces re-announcement.
    expect(first).not.toBe(second)
    expect(second?.trim()).toBe('Persona deleted')
  })

  it('no-op announce() outside a provider does not throw', () => {
    render(<AnnouncerBridge />)
    expect(captured.announce).toBeTypeOf('function')
    expect(() => captured.announce?.('no provider mounted')).not.toThrow()
  })

  it('empty / whitespace messages are ignored', () => {
    render(
      <LiveAnnouncerProvider>
        <AnnouncerBridge />
      </LiveAnnouncerProvider>,
    )

    act(() => {
      captured.announce?.('   ')
    })
    const polite = screen.getByTestId('live-announcer-polite')
    expect(polite.textContent?.trim()).toBe('')
  })
})

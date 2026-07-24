import { createContext, useContext, useRef, useState } from 'react'
import type { ReactNode } from 'react'

/**
 * Priority for aria-live announcements.
 *  - polite: waits for the screen reader to finish its current utterance.
 *  - assertive: interrupts — use only for errors / critical partial failures.
 */
export type AnnouncePriority = 'polite' | 'assertive'

export interface AnnounceOptions {
  priority?: AnnouncePriority
}

interface AnnouncerContextValue {
  announce: (message: string, options?: AnnounceOptions) => void
}

const AnnouncerContext = createContext<AnnouncerContextValue | null>(null)

/**
 * Provider that mounts two visually-hidden aria-live regions (polite +
 * assertive) and exposes an imperative `announce` function via context.
 *
 * Should be mounted once near the root of the application, inside any
 * <I18nextProvider> so announcements can be pre-translated by the caller.
 *
 * Each call replaces the region contents — even if the new message is the
 * same string, we toggle a hidden counter so screen readers re-announce it.
 */
export function LiveAnnouncerProvider({ children }: { children: ReactNode }) {
  const [politeMessage, setPoliteMessage] = useState('')
  const [assertiveMessage, setAssertiveMessage] = useState('')
  // Bumped every announce() call so identical repeat messages still trigger
  // a DOM mutation and a fresh AT announcement.
  const politeCounterRef = useRef(0)
  const assertiveCounterRef = useRef(0)

  const announce: AnnouncerContextValue['announce'] = (message, options) => {
    const trimmed = message?.trim()
    if (!trimmed) return
    const priority = options?.priority ?? 'polite'
    if (priority === 'assertive') {
      assertiveCounterRef.current += 1
      // Force AT re-read of duplicate messages by alternating a zero-width suffix.
      const suffix = assertiveCounterRef.current % 2 === 0 ? '' : ' '
      setAssertiveMessage(trimmed + suffix)
    } else {
      politeCounterRef.current += 1
      const suffix = politeCounterRef.current % 2 === 0 ? '' : ' '
      setPoliteMessage(trimmed + suffix)
    }
  }

  return (
    <AnnouncerContext.Provider value={{ announce }}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
        data-testid="live-announcer-polite"
      >
        {politeMessage}
      </div>
      <div
        aria-live="assertive"
        aria-atomic="true"
        className="sr-only"
        data-testid="live-announcer-assertive"
      >
        {assertiveMessage}
      </div>
    </AnnouncerContext.Provider>
  )
}

/**
 * Hook returning { announce(message, options?) }.
 *
 * Safe to call from components rendered outside the provider — in that case
 * announce() is a no-op so shared components (e.g. DataTable) can call it
 * unconditionally from tests or stories that skip the provider.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useAnnouncer(): AnnouncerContextValue {
  const ctx = useContext(AnnouncerContext)
  if (!ctx) {
    return { announce: () => {} }
  }
  return ctx
}

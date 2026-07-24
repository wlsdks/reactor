import { useEffect, useState } from 'react'

/**
 * Subscribes to a CSS media query and returns whether it currently matches.
 *
 * Mirrors the behaviour previously inlined in SideNav as `useViewportMatchesBelow`:
 * - SSR-safe: returns `false` when `window` is unavailable.
 * - Initialises from `window.innerWidth` synchronously to avoid a layout flash
 *   before the first effect runs.
 * - Falls back to the legacy `addListener` / `removeListener` API for browsers
 *   that have not adopted `addEventListener` on `MediaQueryList`.
 *
 * @param query A CSS media query string, e.g. `(max-width: 1024px)`.
 */
export function useViewportMatch(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    const mql = window.matchMedia(query)
    const update = () => setMatches(mql.matches)
    update()
    if (typeof mql.addEventListener === 'function') {
      mql.addEventListener('change', update)
      return () => mql.removeEventListener('change', update)
    }
    mql.addListener(update)
    return () => mql.removeListener(update)
  }, [query])

  return matches
}

import { useEffect } from 'react'

/**
 * Suffix appended after the page-specific title to keep brand identity
 * visible in the browser tab. Centralised so both manual callers and
 * the PageHeader-driven path stay in sync.
 */
const TITLE_SUFFIX = 'Reactor Admin'

/**
 * Sets `document.title` while the calling component is mounted and
 * restores the previous title on unmount.
 *
 * Usage:
 *
 * ```tsx
 * useDocumentTitle('대시보드')
 * // → document.title = '대시보드 · Reactor Admin'
 *
 * useDocumentTitle(undefined)
 * // → document.title = 'Reactor Admin'
 * ```
 *
 * Per BX audit P1-2: gives every browser tab a distinct, brand-correct
 * title so multiple admin tabs are distinguishable at a glance.
 *
 * Wired into {@link import('../ui/PageHeader').PageHeader} so any page
 * using that primitive auto-updates without per-page wiring. Pages
 * without a PageHeader (Dashboard, Login, *Detail) call this hook
 * directly from their top-level component.
 */
export function useDocumentTitle(
  pageTitle: string | undefined | null,
  enabled = true,
): void {
  useEffect(() => {
    if (!enabled) return undefined
    const previous = document.title
    const trimmed = pageTitle?.trim()
    document.title = trimmed ? `${trimmed} · ${TITLE_SUFFIX}` : TITLE_SUFFIX
    return () => {
      document.title = previous
    }
  }, [enabled, pageTitle])
}

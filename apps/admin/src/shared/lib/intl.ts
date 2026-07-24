/**
 * Shared Intl helpers — single source of truth for locale-aware formatting.
 *
 * The product is Korean-only, so all helpers default to `ko-KR` to keep
 * thousands separators, dates, and time strings consistent across browsers
 * (the browser default would otherwise depend on the viewer's OS language).
 *
 * NOTE: The K/M-abbreviated `formatNumber` and the compact ISO-style
 * `formatDateTime` / `formatDateCompact` / `formatDateTimeCompact` helpers
 * in `formatters.ts` intentionally use `'en-US'` / `'en-CA'` to produce
 * stable abbreviations and ISO-like `YYYY-MM-DD` output. Those are kept
 * separate from this module by design.
 */

/** Single source of truth for the product's display locale. */
export const KO_LOCALE = 'ko-KR'

/**
 * Format a number with Korean locale thousands separators (e.g. `1,234,567`).
 *
 * Returns `'—'` (em dash) for null / undefined / non-finite values so callers
 * can drop the result straight into JSX without conditional guards.
 */
export function formatLocaleNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toLocaleString(KO_LOCALE)
}

/**
 * Format a `Date` as a 24-hour time string in the Korean locale
 * (e.g. `'오후 5:44:12'` is suppressed by `hour12: false` → `'17:44:12'`).
 */
export function formatLocaleTime(date: Date): string {
  return date.toLocaleTimeString(KO_LOCALE, { hour12: false })
}

/**
 * Format a date-like input as a localized datetime string in `ko-KR`.
 *
 * Accepts `Date`, ISO string, or epoch ms. Returns `'—'` for invalid inputs
 * so the helper can be used directly in JSX without conditional guards.
 *
 * For compact ISO-style output (`'2026-04-25 17:44'`) prefer
 * `formatDateTimeCompact` from `formatters.ts` — that helper is locale-stable
 * and is the right choice for tables, audit logs, and monospace columns.
 */
export function formatLocaleDateTime(input: Date | string | number | null | undefined): string {
  if (input === null || input === undefined || input === '') return '—'
  const date = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString(KO_LOCALE)
}

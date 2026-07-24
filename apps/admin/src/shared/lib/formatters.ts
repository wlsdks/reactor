import { downloadFile } from './downloadFile'
import { KO_LOCALE } from './intl'

/**
 * Coerce a variety of date-like inputs (epoch ms, ISO string, Date) into a
 * valid Date, or return null when the input cannot be parsed.
 *
 * Returns null for null/undefined, empty strings, invalid dates, and
 * unparseable values. Callers should treat a null return as "render empty".
 */
function coerceDate(input: string | number | Date | null | undefined): Date | null {
  if (input === null || input === undefined) return null
  if (input === '') return null
  const date = input instanceof Date ? input : new Date(input)
  return Number.isNaN(date.getTime()) ? null : date
}

/**
 * Optional timezone for the compact date/time formatters.
 *
 * - `'local'` (default): use the viewer's resolved IANA zone via Intl.
 * - `'utc'`: render in UTC.
 * - any other string is forwarded as the IANA `timeZone` option (e.g. `'Asia/Seoul'`).
 *
 * Invalid IANA strings cause `Intl.DateTimeFormat` to throw; the formatters
 * catch and fall back to local time so a bad timezone never breaks the UI.
 */
export type TimezoneOption = 'local' | 'utc' | string

interface DateTimeFormatOptions {
  timezone?: TimezoneOption
}

/**
 * Resolve the user-facing `TimezoneOption` to the value Intl expects:
 * `'local'` → undefined (Intl uses the resolved system zone),
 * `'utc'` → `'UTC'`, otherwise the string is passed through unchanged.
 */
function resolveTimeZone(timezone: TimezoneOption | undefined): string | undefined {
  if (!timezone || timezone === 'local') return undefined
  if (timezone === 'utc') return 'UTC'
  return timezone
}

/**
 * Compact ISO-like datetime format: "2026-04-20 17:44".
 *
 * Uses the `en-CA` locale with `hour12: false` to produce a stable
 * "YYYY-MM-DD, HH:MM" output across browsers, then normalises the comma to
 * a single space. Values are rendered in the viewer's local time zone by
 * default; pass `{ timezone: 'utc' }` or an IANA string to override.
 *
 * Returns an empty string for null/undefined/invalid inputs so callers can
 * use it directly in JSX without conditional logic.
 */
export function formatDateTimeCompact(
  input: string | number | Date | null | undefined,
  opts: DateTimeFormatOptions = {},
): string {
  const date = coerceDate(input)
  if (!date) return ''
  const timeZone = resolveTimeZone(opts.timezone)
  let formatted: string
  try {
    formatted = new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      ...(timeZone ? { timeZone } : {}),
    }).format(date)
  } catch {
    // Fall back to local time when an invalid IANA zone is supplied.
    formatted = new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(date)
  }
  // en-CA emits "YYYY-MM-DD, HH:MM" — normalise to a single space.
  return formatted.replace(', ', ' ')
}

/**
 * Compact ISO-like date format: "2026-04-20". Defaults to local time zone;
 * pass `{ timezone: 'utc' }` or an IANA string to override.
 * Returns empty string for null/undefined/invalid inputs.
 */
export function formatDateCompact(
  input: string | number | Date | null | undefined,
  opts: DateTimeFormatOptions = {},
): string {
  const date = coerceDate(input)
  if (!date) return ''
  const timeZone = resolveTimeZone(opts.timezone)
  try {
    return new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      ...(timeZone ? { timeZone } : {}),
    }).format(date)
  } catch {
    return new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(date)
  }
}

/**
 * Format an epoch millisecond timestamp as a compact ISO-like string
 * ("YYYY-MM-DD HH:MM"). See formatDateTimeCompact.
 */
export function formatDateTime(epochMs: number): string {
  return formatDateTimeCompact(epochMs)
}

/**
 * Format an ISO-8601 date string as a compact ISO-like string
 * ("YYYY-MM-DD HH:MM"). See formatDateTimeCompact.
 */
export function formatISODate(iso: string): string {
  return formatDateTimeCompact(iso)
}

/**
 * Format a duration in milliseconds as a human-readable string.
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const mins = Math.floor(ms / 60_000)
  const secs = Math.round((ms % 60_000) / 1000)
  return `${mins}m ${secs}s`
}

/**
 * Truncate a string to maxLen characters, appending '...' if truncated.
 */
export function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen) + '...'
}

/**
 * Format a large number with K/M suffixes for chart axis labels and tooltips.
 * null / undefined / NaN 은 '0' 으로 방어 (admin 테이블에서 백엔드 누락 시 크래시 방지).
 */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '0'
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  // Pin to ko-KR so the small-value branch does not depend on the viewer's
  // browser locale. Latin digits + comma grouping is identical to en-US for
  // this range, but the explicit locale keeps output deterministic.
  return value.toLocaleString(KO_LOCALE)
}

// ── Unified numeric formatters ────────────────────────────────────────────
//
// These helpers consolidate the scattered `.toFixed()` / `.toLocaleString()`
// patterns used across feature dashboards. They are pure functions with no
// i18n dependency: thousands separators come from `Intl.NumberFormat('en-US')`
// so output is stable across locales and easy to assert in tests.
//
// All four return `'-'` for null / undefined / NaN inputs so call sites can
// drop them straight into JSX without conditional guards.

/**
 * Format a 0..1 ratio as a percentage with one decimal by default.
 *
 * Examples: `formatPercent(0.123)` → `"12.3%"`, `formatPercent(null)` → `"-"`.
 * Pass `decimals` to override precision (e.g. block rate uses 2 dp).
 */
export function formatPercent(
  ratio: number | null | undefined,
  decimals = 1,
): string {
  if (ratio === null || ratio === undefined || Number.isNaN(ratio)) return '-'
  return `${(ratio * 100).toFixed(decimals)}%`
}

/**
 * Format a metric count for KPI cards / table cells.
 *
 * - `>= 1_000_000_000` → `"1.2B"`
 * - `>= 1_000_000` → `"360.1M"`
 * - `>= 10_000` → `"12.3K"`
 * - else → integer with thousands separators (e.g. `"9,999"`)
 *
 * Uses a 10K threshold for the K suffix so numbers like 1,234 stay readable
 * with their thousands separator instead of collapsing to `"1.2K"`.
 */
export function formatMetricValue(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  const abs = Math.abs(value)
  if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (abs >= 10_000) return `${(value / 1_000).toFixed(1)}K`
  return new Intl.NumberFormat('en-US').format(Math.trunc(value))
}

interface FormatCurrencyOptions {
  currency?: 'USD' | 'KRW'
  /** Override the minimum fraction digits for non-sub-cent USD values. */
  minDecimals?: number
}

const USD_DEFAULT_FORMATTER = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const USD_SUB_CENT_FORMATTER = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
})
const KRW_CURRENCY_FORMATTER = new Intl.NumberFormat('ko-KR', {
  maximumFractionDigits: 0,
})

/**
 * Format a monetary amount with thousands separators.
 *
 * - USD (default): `< 1` → 4 decimal places (sub-cent precision); else 2 dp.
 *   `formatCurrency(0.0034)` → `"$0.0034"`, `formatCurrency(1234.5)` → `"$1,234.50"`.
 * - KRW: integer with `'₩'` prefix and Korean grouping, `formatCurrency(12000, { currency: 'KRW' })` → `"₩12,000"`.
 *
 * Pass `minDecimals` to force a specific precision for USD (e.g. session-level
 * cost cards that always want 2 dp regardless of magnitude).
 */
export function formatCurrency(
  value: number | null | undefined,
  opts: FormatCurrencyOptions = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  const currency = opts.currency ?? 'USD'
  if (currency === 'KRW') {
    return `₩${KRW_CURRENCY_FORMATTER.format(Math.round(value))}`
  }
  // USD path
  if (opts.minDecimals !== undefined) {
    const formatter = new Intl.NumberFormat('en-US', {
      minimumFractionDigits: opts.minDecimals,
      maximumFractionDigits: opts.minDecimals,
    })
    return `$${formatter.format(value)}`
  }
  // Sub-cent precision keeps tiny token-cost figures (e.g. $0.0034) readable.
  if (value !== 0 && Math.abs(value) < 1) {
    return `$${USD_SUB_CENT_FORMATTER.format(value)}`
  }
  return `$${USD_DEFAULT_FORMATTER.format(value)}`
}

/**
 * Format a millisecond latency value.
 *
 * - `< 1000` → integer ms (e.g. `"125ms"`)
 * - `< 60_000` → seconds with one decimal (e.g. `"2.5s"`)
 * - else → minutes + seconds (e.g. `"2m 5s"`)
 *
 * Mirrors the existing `formatDuration` helper, but accepts null / undefined /
 * NaN safely (returns `'-'`) so it can be used directly on optional API fields.
 */
export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const mins = Math.floor(ms / 60_000)
  const secs = Math.round((ms % 60_000) / 1000)
  return `${mins}m ${secs}s`
}

// ── Record-safe extractors ────────────────────────────────────────────────

/** Safely extract a numeric value from Record<string, unknown>. */
export function numFromRecord(data: Record<string, unknown>, key: string): number {
  const v = data[key]
  return typeof v === 'number' ? v : 0
}

/** Safely extract a string value from Record<string, unknown>. */
export function strFromRecord(data: Record<string, unknown>, key: string, fallback = '-'): string {
  const v = data[key]
  if (typeof v === 'string') return v
  if (typeof v === 'number') return String(v)
  return fallback
}

/** Format a numeric value for display (round to 2 decimals if float). */
export function fmtValue(value: number): string {
  if (Number.isInteger(value)) return String(value)
  return value.toFixed(2)
}

/** Format a percentage value (0-100 or 0-1 range). */
export function pctFromRecord(data: Record<string, unknown>, key: string): string {
  const v = data[key]
  if (typeof v !== 'number') return '-'
  // If the value is between 0 and 1 (exclusive), treat as fraction
  if (v > 0 && v < 1) return `${(v * 100).toFixed(1)}%`
  return `${v.toFixed(1)}%`
}

/** Safely extract an array from a record. */
export function arrFromRecord(data: Record<string, unknown>, key: string): Array<Record<string, unknown>> {
  const v = data[key]
  if (Array.isArray(v)) return v as Array<Record<string, unknown>>
  return []
}

/**
 * Format a user ID for display. Shows email if available, otherwise
 * truncates the UUID to the first 8 characters with an ellipsis.
 */
export function formatUserId(userId: string, email?: string | null): string {
  if (email) return email
  if (userId.length > 8) return userId.slice(0, 8) + '\u2026'
  return userId
}

/** Parse a datetime-local string to epoch ms, or undefined if invalid. */
export function toEpochMs(value: string): number | undefined {
  if (!value) return undefined
  const parsed = new Date(value).getTime()
  return Number.isFinite(parsed) ? parsed : undefined
}

/**
 * Trigger a CSV file download in the browser.
 *
 * Server-rendered CSV bodies (e.g. tenant-admin executions/tools exports) are
 * streamed directly through here. For in-memory rows derived from a DataTable,
 * prefer `useTableExport` from `shared/lib/useTableExport.ts` — it handles
 * BOM, RFC 4180 escaping, and JSON output as a paired format.
 *
 * Internally delegates to the shared `downloadFile` helper so all blob
 * downloads share one DOM-touch surface.
 */
export function downloadCsv(filename: string, content: string): void {
  // The text/csv MIME with BOM-prefixed content lets Excel KO open the file
  // in UTF-8 by default. Server payloads already include the BOM where
  // required, so we do not prepend one here.
  downloadFile(content, filename, 'text/csv;charset=utf-8;')
}

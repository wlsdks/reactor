import { useEffect, useState } from 'react'
import { formatRelativeTimeKo } from './formatRelativeTimeKo'

/**
 * Adaptive refresh cadence in milliseconds.
 *
 * Sub-minute timestamps tick every 5 seconds so the rendered "방금 전" snaps
 * to "1분 전" as soon as the boundary is crossed, the next hour ticks every
 * 30 seconds (cheap enough for any visible row count), and timestamps older
 * than an hour fall back to a 5-minute beat since the rendered string only
 * changes once per hour anyway.
 */
function adaptiveTickMs(diffMs: number): number {
  if (diffMs < 60_000) return 5_000
  if (diffMs < 3_600_000) return 30_000
  return 300_000
}

interface UseRelativeTimeOptions {
  /**
   * Override the adaptive cadence with a fixed refresh interval (seconds).
   * Useful for virtualized tables or low-priority cells where the default
   * 5s sub-minute beat is more re-render than necessary.
   */
  tickSeconds?: number
  /**
   * Custom formatter — defaults to {@link formatRelativeTimeKo}. Receives a
   * coerced Date so callers can plug in alternative i18n-aware variants
   * without touching the input parsing path.
   */
  formatFn?: (date: Date) => string
}

function defaultFormat(date: Date): string {
  return formatRelativeTimeKo(date)
}

/**
 * Coerce flexible date-like inputs to a valid Date or null. Kept private so
 * this module has no implicit cross-file dependency on the formatters helper.
 */
function toValidDate(input: string | number | Date | null | undefined): Date | null {
  if (input === null || input === undefined || input === '') return null
  const date = input instanceof Date ? input : new Date(input)
  return Number.isNaN(date.getTime()) ? null : date
}

/**
 * Returns a Korean-localized relative time string ("3분 전", "2시간 전") that
 * auto-refreshes.
 *
 * - Returns an empty string for null / undefined / unparseable inputs and
 *   skips scheduling an interval in that case.
 * - Uses {@link adaptiveTickMs} by default; pass `tickSeconds` to force a
 *   fixed cadence (e.g. virtualized lists where many cells share a tick).
 * - Cleans up the interval on unmount and whenever the input timestamp or
 *   cadence changes.
 *
 * The state stores only an opaque "tick" counter; the rendered string is
 * derived from the input on every render. This keeps the effect side-effect
 * only (no setState in effect body) and lets the React Compiler memoize the
 * formatted output naturally.
 */
export function useRelativeTime(
  input: string | number | Date | null | undefined,
  options: UseRelativeTimeOptions = {},
): string {
  const { tickSeconds, formatFn = defaultFormat } = options

  // Tick counter — incrementing it forces a re-render and thus a fresh format.
  const [, setTick] = useState(0)

  useEffect(() => {
    const date = toValidDate(input)
    if (!date) return

    const intervalMs = tickSeconds !== undefined
      ? Math.max(1, tickSeconds) * 1000
      : adaptiveTickMs(Date.now() - date.getTime())

    const id = setInterval(() => {
      setTick((n) => n + 1)
    }, intervalMs)

    return () => clearInterval(id)
  }, [input, tickSeconds])

  const date = toValidDate(input)
  if (!date) return ''
  return formatFn(date)
}

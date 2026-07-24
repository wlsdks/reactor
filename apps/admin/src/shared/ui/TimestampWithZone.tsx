import { useTranslation } from 'react-i18next'
import {
  formatDateTimeCompact,
  formatDateCompact,
} from '../lib/formatters'
import { formatRelativeTimeKo } from '../lib/formatRelativeTimeKo'

export type TimestampZone = 'local' | 'utc'
export type TimestampFormat = 'compact' | 'date' | 'relative'

export interface TimestampWithZoneProps {
  value: string | number | Date | null | undefined
  format?: TimestampFormat
  timezone?: TimestampZone
  showZone?: boolean
  /** Optional override for the surrounding wrapper class. */
  className?: string
}

interface ZoneLabel {
  /** Short label rendered next to the timestamp (e.g. "KST", "UTC"). */
  short: string
  /** Tooltip body shown on hover (full IANA + offset or human description). */
  tooltip: string
}

/**
 * Map common IANA timezone identifiers to a 3-4 letter abbreviation.
 *
 * `Intl.DateTimeFormat(..., { timeZoneName: 'short' })` already emits an
 * abbreviation, but the result varies by locale and browser (e.g. "GMT+9",
 * "한국 표준시"). This deterministic table is used first; anything not in the
 * table falls back to the IANA short timezone name from the en-US formatter,
 * and then to a numeric offset like "UTC+9".
 */
const IANA_TO_SHORT: Record<string, string> = {
  'Asia/Seoul': 'KST',
  'Asia/Tokyo': 'JST',
  'Asia/Shanghai': 'CST',
  'Asia/Hong_Kong': 'HKT',
  'Asia/Singapore': 'SGT',
  'Asia/Kolkata': 'IST',
  'Europe/London': 'GMT',
  'Europe/Paris': 'CET',
  'Europe/Berlin': 'CET',
  'America/New_York': 'EST',
  'America/Chicago': 'CST',
  'America/Denver': 'MST',
  'America/Los_Angeles': 'PST',
  UTC: 'UTC',
}

/**
 * Format the local UTC offset as `"UTC±HH:MM"` for the supplied date.
 *
 * `Date#getTimezoneOffset()` returns the offset *behind* UTC in minutes
 * (KST is `-540`), so we negate the sign before formatting.
 */
function formatOffset(date: Date): string {
  const offsetMinutes = -date.getTimezoneOffset()
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const abs = Math.abs(offsetMinutes)
  const hours = String(Math.floor(abs / 60)).padStart(2, '0')
  const minutes = String(abs % 60).padStart(2, '0')
  return `UTC${sign}${hours}:${minutes}`
}

/**
 * Best-effort short label for a timezone:
 * `IANA_TO_SHORT` table → `Intl` short name (en-US) → numeric offset fallback.
 */
function shortLabelFor(ianaName: string, date: Date): string {
  if (IANA_TO_SHORT[ianaName]) return IANA_TO_SHORT[ianaName]
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: ianaName,
      timeZoneName: 'short',
    }).formatToParts(date)
    const tzPart = parts.find((p) => p.type === 'timeZoneName')?.value
    if (tzPart && /^[A-Z]{2,5}$/.test(tzPart)) return tzPart
  } catch {
    // ignored — fall through to offset.
  }
  return formatOffset(date)
}

/**
 * Resolve the zone label + tooltip for a given timezone preference, anchored
 * to a specific date so the offset reflects DST at that point in time.
 */
function resolveZoneLabel(
  zone: TimestampZone,
  date: Date,
  t: (key: string, opts?: Record<string, unknown>) => string,
): ZoneLabel {
  if (zone === 'utc') {
    return {
      short: t('common.timezone.utc'),
      tooltip: t('common.timezone.tooltipUtc'),
    }
  }
  // 'local'
  let ianaName: string
  try {
    ianaName = new Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    ianaName = 'UTC'
  }
  const short = shortLabelFor(ianaName, date)
  const tooltip = t('common.timezone.tooltipLocal', {
    offset: formatOffset(date),
    name: ianaName,
  })
  return { short, tooltip }
}

/**
 * Render a timestamp with a small dim timezone label.
 *
 * The numeric portion uses the `data-mono` class (IBM Plex Mono per
 * `DESIGN.md`), and the zone suffix is rendered as `<small>` in the
 * `--text-dim` token. The tooltip carries the full IANA name + offset.
 *
 * Renders `"-"` for null/undefined/invalid inputs, matching other Admin
 * fallbacks (e.g. `formatPercent`, `formatCurrency`).
 */
export function TimestampWithZone({
  value,
  format = 'compact',
  timezone = 'local',
  showZone = true,
  className,
}: TimestampWithZoneProps) {
  const { t } = useTranslation()

  const date = coerceForLabel(value)
  if (!date) {
    return <span className={className}>-</span>
  }

  let body: string
  if (format === 'relative') {
    // Relative time is always "now-anchored" — timezone is meaningless, so
    // we ignore the prop here while keeping the API symmetric with the other
    // formats. The zone label still shows the viewer's local zone for
    // consistency with adjacent absolute timestamps.
    body = formatRelativeTimeKo(value)
  } else if (format === 'date') {
    body = formatDateCompact(value, { timezone })
  } else {
    body = formatDateTimeCompact(value, { timezone })
  }

  if (!showZone) {
    return (
      <span className={className ?? 'data-mono'}>{body}</span>
    )
  }

  const zone = resolveZoneLabel(timezone, date, t)
  return (
    <span className={className ?? 'timestamp-with-zone'} title={zone.tooltip}>
      <span className="data-mono">{body}</span>
      <small
        className="timestamp-with-zone__zone"
        aria-label={zone.tooltip}
      >
        {zone.short}
      </small>
    </span>
  )
}

/**
 * Local copy of the `coerceDate` logic — `formatters.ts` keeps its version
 * private so we re-derive the Date here for the tooltip / offset calculation.
 */
function coerceForLabel(input: string | number | Date | null | undefined): Date | null {
  if (input === null || input === undefined) return null
  if (input === '') return null
  const date = input instanceof Date ? input : new Date(input)
  return Number.isNaN(date.getTime()) ? null : date
}

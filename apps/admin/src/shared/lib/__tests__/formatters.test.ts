import { describe, it, expect, vi } from 'vitest'
import {
  formatDateTime,
  formatISODate,
  formatDateTimeCompact,
  formatDateCompact,
  formatDuration,
  truncate,
  formatNumber,
  formatUserId,
  numFromRecord,
  strFromRecord,
  fmtValue,
  pctFromRecord,
  arrFromRecord,
  toEpochMs,
  downloadCsv,
  formatPercent,
  formatMetricValue,
  formatCurrency,
  formatLatency,
} from '../formatters'

// Matches "YYYY-MM-DD HH:MM" exactly.
const COMPACT_DATETIME_RE = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/
// Matches "YYYY-MM-DD" exactly.
const COMPACT_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

describe('formatDateTime', () => {
  it('formats epoch milliseconds as a compact ISO-like string', () => {
    const epoch = new Date('2024-01-15T10:30:00Z').getTime()
    const result = formatDateTime(epoch)
    expect(result).toMatch(COMPACT_DATETIME_RE)
  })

  it('handles epoch 0', () => {
    const result = formatDateTime(0)
    expect(result).toMatch(COMPACT_DATETIME_RE)
    // Epoch 0 is 1969-12-31 in negative UTC offsets and 1970-01-01 in non-negative.
    // Assert the year is one of those two.
    const year = result.slice(0, 4)
    expect(['1969', '1970']).toContain(year)
  })
})

describe('formatISODate', () => {
  it('formats ISO string as a compact ISO-like datetime', () => {
    const result = formatISODate('2024-06-01T12:00:00Z')
    expect(result).toMatch(COMPACT_DATETIME_RE)
  })

  it('returns a string containing the year', () => {
    const result = formatISODate('2023-07-15T12:00:00Z')
    expect(result).toContain('2023')
  })
})

describe('formatDateTimeCompact', () => {
  it('formats ISO string as "YYYY-MM-DD HH:MM" in local time', () => {
    const result = formatDateTimeCompact('2026-04-20T17:44:01Z')
    expect(result).toMatch(COMPACT_DATETIME_RE)
    expect(result.startsWith('2026-04-')).toBe(true)
  })

  it('formats epoch ms input', () => {
    const epoch = new Date('2024-01-15T10:30:00Z').getTime()
    const result = formatDateTimeCompact(epoch)
    expect(result).toMatch(COMPACT_DATETIME_RE)
  })

  it('formats Date instance input', () => {
    const result = formatDateTimeCompact(new Date('2026-04-20T17:44:01Z'))
    expect(result).toMatch(COMPACT_DATETIME_RE)
  })

  it('renders a known UTC value correctly in UTC environments', () => {
    // Test is timezone-aware: only runs the strict equality when CI is in UTC.
    const offsetMinutes = new Date('2026-04-20T17:44:01Z').getTimezoneOffset()
    if (offsetMinutes === 0) {
      expect(formatDateTimeCompact('2026-04-20T17:44:01Z')).toBe('2026-04-20 17:44')
    } else {
      // In non-UTC zones, at least verify the date portion and mono-friendly format.
      expect(formatDateTimeCompact('2026-04-20T17:44:01Z')).toMatch(COMPACT_DATETIME_RE)
    }
  })

  it('returns empty string for null/undefined/empty input', () => {
    expect(formatDateTimeCompact(null)).toBe('')
    expect(formatDateTimeCompact(undefined)).toBe('')
    expect(formatDateTimeCompact('')).toBe('')
  })

  it('returns empty string for invalid input', () => {
    expect(formatDateTimeCompact('not-a-date')).toBe('')
    expect(formatDateTimeCompact(Number.NaN)).toBe('')
  })

  it('does not contain locale-specific AM/PM markers or Korean characters', () => {
    const result = formatDateTimeCompact('2026-04-20T17:44:01Z')
    expect(result).not.toMatch(/오전|오후|AM|PM/)
  })

  it('renders the supplied UTC instant verbatim when timezone="utc"', () => {
    expect(formatDateTimeCompact('2026-04-20T17:44:01Z', { timezone: 'utc' })).toBe(
      '2026-04-20 17:44',
    )
  })

  it('renders Asia/Seoul (KST = UTC+9) when explicit IANA zone is supplied', () => {
    expect(formatDateTimeCompact('2026-04-20T17:44:01Z', { timezone: 'Asia/Seoul' })).toBe(
      '2026-04-21 02:44',
    )
  })

  it('falls back to local time when timezone is an invalid IANA string', () => {
    const result = formatDateTimeCompact('2026-04-20T17:44:01Z', { timezone: 'Not/A_Zone' })
    expect(result).toMatch(COMPACT_DATETIME_RE)
  })
})

describe('formatDateCompact', () => {
  it('formats input as "YYYY-MM-DD"', () => {
    const result = formatDateCompact('2026-04-20T17:44:01Z')
    expect(result).toMatch(COMPACT_DATE_RE)
  })

  it('returns empty string for null/undefined', () => {
    expect(formatDateCompact(null)).toBe('')
    expect(formatDateCompact(undefined)).toBe('')
  })

  it('returns empty string for invalid input', () => {
    expect(formatDateCompact('nope')).toBe('')
  })

  it('renders the UTC date when timezone="utc" pushes the day forward', () => {
    expect(formatDateCompact('2026-04-20T23:30:00Z', { timezone: 'utc' })).toBe('2026-04-20')
  })

  it('rolls the date forward in Asia/Seoul (UTC+9) for late-evening UTC', () => {
    expect(formatDateCompact('2026-04-20T23:30:00Z', { timezone: 'Asia/Seoul' })).toBe(
      '2026-04-21',
    )
  })
})

describe('formatDuration', () => {
  it('formats sub-second durations as ms', () => {
    expect(formatDuration(0)).toBe('0ms')
    expect(formatDuration(500)).toBe('500ms')
    expect(formatDuration(999)).toBe('999ms')
  })

  it('formats durations under 60s with one decimal', () => {
    expect(formatDuration(1000)).toBe('1.0s')
    expect(formatDuration(1500)).toBe('1.5s')
    expect(formatDuration(59999)).toBe('60.0s')
  })

  it('formats durations over 60s as minutes and seconds', () => {
    expect(formatDuration(60000)).toBe('1m 0s')
    expect(formatDuration(90000)).toBe('1m 30s')
    expect(formatDuration(3661000)).toBe('61m 1s')
  })
})

describe('truncate', () => {
  it('returns string unchanged when within limit', () => {
    expect(truncate('hello', 10)).toBe('hello')
    expect(truncate('hello', 5)).toBe('hello')
  })

  it('truncates and appends ellipsis when over limit', () => {
    expect(truncate('hello world', 5)).toBe('hello...')
    expect(truncate('abcdefgh', 3)).toBe('abc...')
  })

  it('handles empty string', () => {
    expect(truncate('', 5)).toBe('')
  })

  it('handles limit of 0', () => {
    expect(truncate('hello', 0)).toBe('...')
  })
})

describe('formatUserId', () => {
  it('returns email when provided', () => {
    expect(formatUserId('2a2bcb17-8dee-4445-8abb-e6d27598ec2e', 'user@example.com')).toBe('user@example.com')
  })

  it('truncates UUID to first 8 chars with ellipsis', () => {
    expect(formatUserId('2a2bcb17-8dee-4445-8abb-e6d27598ec2e')).toBe('2a2bcb17\u2026')
  })

  it('returns short userId unchanged', () => {
    expect(formatUserId('abcd1234')).toBe('abcd1234')
    expect(formatUserId('short')).toBe('short')
  })

  it('ignores null email and truncates', () => {
    expect(formatUserId('2a2bcb17-8dee-4445-8abb-e6d27598ec2e', null)).toBe('2a2bcb17\u2026')
  })

  it('ignores empty string email and truncates', () => {
    expect(formatUserId('2a2bcb17-8dee-4445-8abb-e6d27598ec2e', '')).toBe('2a2bcb17\u2026')
  })
})

describe('formatNumber', () => {
  it('formats millions with M suffix', () => {
    expect(formatNumber(1_000_000)).toBe('1.0M')
    expect(formatNumber(2_500_000)).toBe('2.5M')
    expect(formatNumber(10_300_000)).toBe('10.3M')
  })

  it('formats thousands with K suffix', () => {
    expect(formatNumber(1_000)).toBe('1.0K')
    expect(formatNumber(1_500)).toBe('1.5K')
    expect(formatNumber(999_999)).toBe('1000.0K')
  })

  it('formats small numbers with locale string', () => {
    expect(formatNumber(0)).toBe('0')
    expect(formatNumber(999)).toBe('999')
    expect(formatNumber(42)).toBe('42')
  })
})

describe('numFromRecord', () => {
  it('extracts numeric value from a record', () => {
    const data: Record<string, unknown> = { count: 42 }
    expect(numFromRecord(data, 'count')).toBe(42)
  })

  it('returns 0 for non-numeric values', () => {
    const data: Record<string, unknown> = { count: 'not-a-number' }
    expect(numFromRecord(data, 'count')).toBe(0)
  })

  it('returns 0 for missing keys', () => {
    const data: Record<string, unknown> = {}
    expect(numFromRecord(data, 'missing')).toBe(0)
  })

  it('returns 0 for null/undefined values', () => {
    const data: Record<string, unknown> = { a: null, b: undefined }
    expect(numFromRecord(data, 'a')).toBe(0)
    expect(numFromRecord(data, 'b')).toBe(0)
  })
})

describe('strFromRecord', () => {
  it('extracts string value from a record', () => {
    const data: Record<string, unknown> = { name: 'hello' }
    expect(strFromRecord(data, 'name')).toBe('hello')
  })

  it('converts numeric value to string', () => {
    const data: Record<string, unknown> = { value: 123 }
    expect(strFromRecord(data, 'value')).toBe('123')
  })

  it('returns fallback for non-string, non-number values', () => {
    const data: Record<string, unknown> = { flag: true }
    expect(strFromRecord(data, 'flag')).toBe('-')
  })

  it('returns custom fallback', () => {
    const data: Record<string, unknown> = { flag: null }
    expect(strFromRecord(data, 'flag', 'N/A')).toBe('N/A')
  })

  it('returns fallback for missing keys', () => {
    const data: Record<string, unknown> = {}
    expect(strFromRecord(data, 'missing')).toBe('-')
  })
})

describe('fmtValue', () => {
  it('formats integers without decimals', () => {
    expect(fmtValue(42)).toBe('42')
    expect(fmtValue(0)).toBe('0')
    expect(fmtValue(-5)).toBe('-5')
  })

  it('formats floats to 2 decimal places', () => {
    expect(fmtValue(3.14159)).toBe('3.14')
    expect(fmtValue(0.1)).toBe('0.10')
    expect(fmtValue(100.999)).toBe('101.00')
  })
})

describe('pctFromRecord', () => {
  it('returns dash for non-numeric values', () => {
    const data: Record<string, unknown> = { pct: 'hello' }
    expect(pctFromRecord(data, 'pct')).toBe('-')
  })

  it('returns dash for missing keys', () => {
    const data: Record<string, unknown> = {}
    expect(pctFromRecord(data, 'missing')).toBe('-')
  })

  it('treats values between 0 and 1 as fractions', () => {
    const data: Record<string, unknown> = { rate: 0.75 }
    expect(pctFromRecord(data, 'rate')).toBe('75.0%')
  })

  it('treats values >= 1 as raw percentages', () => {
    const data: Record<string, unknown> = { pct: 42.5 }
    expect(pctFromRecord(data, 'pct')).toBe('42.5%')
  })

  it('treats 0 as raw percentage', () => {
    const data: Record<string, unknown> = { pct: 0 }
    expect(pctFromRecord(data, 'pct')).toBe('0.0%')
  })

  it('treats 1 as raw percentage (boundary)', () => {
    const data: Record<string, unknown> = { pct: 1 }
    expect(pctFromRecord(data, 'pct')).toBe('1.0%')
  })
})

describe('arrFromRecord', () => {
  it('extracts an array from a record', () => {
    const data: Record<string, unknown> = { items: [{ id: 1 }, { id: 2 }] }
    expect(arrFromRecord(data, 'items')).toEqual([{ id: 1 }, { id: 2 }])
  })

  it('returns empty array for non-array values', () => {
    const data: Record<string, unknown> = { items: 'not-array' }
    expect(arrFromRecord(data, 'items')).toEqual([])
  })

  it('returns empty array for missing keys', () => {
    const data: Record<string, unknown> = {}
    expect(arrFromRecord(data, 'missing')).toEqual([])
  })

  it('returns empty array for null', () => {
    const data: Record<string, unknown> = { items: null }
    expect(arrFromRecord(data, 'items')).toEqual([])
  })
})

describe('toEpochMs', () => {
  it('parses valid datetime string to epoch ms', () => {
    const result = toEpochMs('2024-01-15T10:30:00Z')
    expect(result).toBe(new Date('2024-01-15T10:30:00Z').getTime())
  })

  it('returns undefined for empty string', () => {
    expect(toEpochMs('')).toBeUndefined()
  })

  it('returns undefined for invalid date string', () => {
    expect(toEpochMs('not-a-date')).toBeUndefined()
  })

  it('parses datetime-local format', () => {
    const result = toEpochMs('2024-06-15T14:30')
    expect(result).toBeTypeOf('number')
    expect(Number.isFinite(result)).toBe(true)
  })
})

describe('downloadCsv', () => {
  it('creates a link, clicks it, and cleans up', async () => {
    const createObjectURLSpy = vi.fn(() => 'blob:mock-url')
    const revokeObjectURLSpy = vi.fn()
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: createObjectURLSpy,
      revokeObjectURL: revokeObjectURLSpy,
    })

    const clickSpy = vi.fn()

    // Mock createElement to track the anchor. The shared `downloadFile`
    // helper no longer mounts the anchor to the DOM (modern browsers fire
    // `click()` on detached anchors), so we only assert createObjectURL +
    // click + revokeObjectURL — not appendChild / removeChild.
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag)
      if (tag === 'a') {
        vi.spyOn(el, 'click').mockImplementation(clickSpy)
      }
      return el
    })

    downloadCsv('report.csv', 'col1,col2\n1,2')

    expect(createObjectURLSpy).toHaveBeenCalledOnce()
    expect(clickSpy).toHaveBeenCalledOnce()
    // revokeObjectURL is queued via queueMicrotask; flush microtasks before
    // asserting.
    await Promise.resolve()
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:mock-url')

    vi.restoreAllMocks()
  })
})

describe('formatPercent', () => {
  it('formats a 0..1 ratio with one decimal by default', () => {
    expect(formatPercent(0.123)).toBe('12.3%')
    expect(formatPercent(0.825)).toBe('82.5%')
    expect(formatPercent(1)).toBe('100.0%')
    expect(formatPercent(0)).toBe('0.0%')
  })

  it('returns "-" for null / undefined / NaN', () => {
    expect(formatPercent(null)).toBe('-')
    expect(formatPercent(undefined)).toBe('-')
    expect(formatPercent(Number.NaN)).toBe('-')
  })

  it('honours a custom decimals override', () => {
    expect(formatPercent(0.12345, 2)).toBe('12.35%')
    expect(formatPercent(0.5, 0)).toBe('50%')
    expect(formatPercent(0.243, 1)).toBe('24.3%')
  })
})

describe('formatMetricValue', () => {
  it('formats values >= 1B with a B suffix', () => {
    expect(formatMetricValue(1_200_000_000)).toBe('1.2B')
    expect(formatMetricValue(2_500_000_000)).toBe('2.5B')
  })

  it('formats values >= 1M with an M suffix', () => {
    expect(formatMetricValue(360_100_000)).toBe('360.1M')
    expect(formatMetricValue(1_000_000)).toBe('1.0M')
  })

  it('formats values >= 10K with a K suffix', () => {
    expect(formatMetricValue(12_345)).toBe('12.3K')
    expect(formatMetricValue(99_999)).toBe('100.0K')
  })

  it('keeps values under 10K as integers with thousands separators', () => {
    expect(formatMetricValue(9_999)).toBe('9,999')
    expect(formatMetricValue(1_234)).toBe('1,234')
    expect(formatMetricValue(42)).toBe('42')
    expect(formatMetricValue(0)).toBe('0')
  })

  it('returns "-" for null / undefined / NaN', () => {
    expect(formatMetricValue(null)).toBe('-')
    expect(formatMetricValue(undefined)).toBe('-')
    expect(formatMetricValue(Number.NaN)).toBe('-')
  })

  it('handles negative values symmetrically', () => {
    expect(formatMetricValue(-12_500)).toBe('-12.5K')
    expect(formatMetricValue(-500)).toBe('-500')
  })
})

describe('formatCurrency', () => {
  it('formats sub-cent USD with 4 decimal places', () => {
    expect(formatCurrency(0.0034)).toBe('$0.0034')
    expect(formatCurrency(0.5)).toBe('$0.5000')
  })

  it('formats USD with 2 decimal places + thousands separators by default', () => {
    expect(formatCurrency(1)).toBe('$1.00')
    expect(formatCurrency(1234.5)).toBe('$1,234.50')
    expect(formatCurrency(1_000_000)).toBe('$1,000,000.00')
    expect(formatCurrency(0)).toBe('$0.00')
  })

  it('honours minDecimals override for USD', () => {
    expect(formatCurrency(0.5, { minDecimals: 2 })).toBe('$0.50')
    expect(formatCurrency(12.3456, { minDecimals: 4 })).toBe('$12.3456')
  })

  it('formats KRW as integer with ₩ prefix', () => {
    expect(formatCurrency(12000, { currency: 'KRW' })).toBe('₩12,000')
    expect(formatCurrency(1234.7, { currency: 'KRW' })).toBe('₩1,235')
    expect(formatCurrency(0, { currency: 'KRW' })).toBe('₩0')
  })

  it('returns "-" for null / undefined / NaN', () => {
    expect(formatCurrency(null)).toBe('-')
    expect(formatCurrency(undefined)).toBe('-')
    expect(formatCurrency(Number.NaN)).toBe('-')
    expect(formatCurrency(null, { currency: 'KRW' })).toBe('-')
  })
})

describe('formatLatency', () => {
  it('formats sub-second values as integer ms', () => {
    expect(formatLatency(0)).toBe('0ms')
    expect(formatLatency(125)).toBe('125ms')
    expect(formatLatency(999)).toBe('999ms')
  })

  it('rounds non-integer ms to the nearest integer', () => {
    expect(formatLatency(125.7)).toBe('126ms')
    expect(formatLatency(125.2)).toBe('125ms')
  })

  it('formats values under one minute as seconds with one decimal', () => {
    expect(formatLatency(1000)).toBe('1.0s')
    expect(formatLatency(2500)).toBe('2.5s')
    expect(formatLatency(59999)).toBe('60.0s')
  })

  it('formats values >= 1m as minutes + seconds', () => {
    expect(formatLatency(60000)).toBe('1m 0s')
    expect(formatLatency(125000)).toBe('2m 5s')
    expect(formatLatency(3661000)).toBe('61m 1s')
  })

  it('returns "-" for null / undefined / NaN', () => {
    expect(formatLatency(null)).toBe('-')
    expect(formatLatency(undefined)).toBe('-')
    expect(formatLatency(Number.NaN)).toBe('-')
  })
})

import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from 'vitest'
import '../../i18n/config'
import { formatRelativeTimeKo } from '../formatRelativeTimeKo'

// Pinning a fixed wall-clock keeps the assertions deterministic regardless of
// when the suite runs. The chosen instant is well clear of DST boundaries so
// the relative arithmetic stays stable across CI environments.
const NOW = new Date('2026-04-26T12:00:00Z').getTime()

describe('formatRelativeTimeKo', () => {
  beforeAll(() => {
    // The helper relies on i18n already being initialized; the import above
    // takes care of that synchronously.
  })

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns empty string for null / undefined / empty input', () => {
    expect(formatRelativeTimeKo(null)).toBe('')
    expect(formatRelativeTimeKo(undefined)).toBe('')
    expect(formatRelativeTimeKo('')).toBe('')
  })

  it('returns empty string for unparseable inputs', () => {
    expect(formatRelativeTimeKo('not-a-date')).toBe('')
    expect(formatRelativeTimeKo(Number.NaN)).toBe('')
  })

  it('returns "방금 전" for sub-minute and future timestamps', () => {
    expect(formatRelativeTimeKo(NOW)).toBe('방금 전')
    expect(formatRelativeTimeKo(NOW - 30_000)).toBe('방금 전')
    expect(formatRelativeTimeKo(NOW + 5_000)).toBe('방금 전')
  })

  it('returns "{n}분 전" for minute-scale durations', () => {
    expect(formatRelativeTimeKo(NOW - 60_000)).toBe('1분 전')
    expect(formatRelativeTimeKo(NOW - 24 * 60_000)).toBe('24분 전')
    expect(formatRelativeTimeKo(NOW - 59 * 60_000)).toBe('59분 전')
  })

  it('returns "{n}시간 전" for hour-scale durations', () => {
    expect(formatRelativeTimeKo(NOW - 60 * 60_000)).toBe('1시간 전')
    expect(formatRelativeTimeKo(NOW - 3 * 3_600_000)).toBe('3시간 전')
    expect(formatRelativeTimeKo(NOW - 23 * 3_600_000)).toBe('23시간 전')
  })

  it('returns "{n}일 전" for day-scale durations', () => {
    expect(formatRelativeTimeKo(NOW - 24 * 3_600_000)).toBe('1일 전')
    expect(formatRelativeTimeKo(NOW - 3 * 86_400_000)).toBe('3일 전')
    expect(formatRelativeTimeKo(NOW - 29 * 86_400_000)).toBe('29일 전')
  })

  it('returns "{n}개월 전" for month-scale durations', () => {
    expect(formatRelativeTimeKo(NOW - 30 * 86_400_000)).toBe('1개월 전')
    expect(formatRelativeTimeKo(NOW - 6 * 30 * 86_400_000)).toBe('6개월 전')
  })

  it('returns "{n}년 전" for year-scale durations', () => {
    expect(formatRelativeTimeKo(NOW - 365 * 86_400_000)).toBe('1년 전')
    expect(formatRelativeTimeKo(NOW - 2 * 365 * 86_400_000)).toBe('2년 전')
  })

  it('accepts ISO string and Date inputs', () => {
    const fiveMinutesAgoIso = new Date(NOW - 5 * 60_000).toISOString()
    expect(formatRelativeTimeKo(fiveMinutesAgoIso)).toBe('5분 전')

    const twoHoursAgo = new Date(NOW - 2 * 3_600_000)
    expect(formatRelativeTimeKo(twoHoursAgo)).toBe('2시간 전')
  })
})

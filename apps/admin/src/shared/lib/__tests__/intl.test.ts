import { describe, it, expect } from 'vitest'
import {
  KO_LOCALE,
  formatLocaleNumber,
  formatLocaleTime,
  formatLocaleDateTime,
} from '../intl'

describe('intl helpers', () => {
  describe('KO_LOCALE', () => {
    it('is the canonical ko-KR string', () => {
      expect(KO_LOCALE).toBe('ko-KR')
    })
  })

  describe('formatLocaleNumber', () => {
    it('inserts thousands separators for large integers', () => {
      // ko-KR uses the same comma grouping as en-US for arabic digits.
      expect(formatLocaleNumber(1_234_567)).toBe('1,234,567')
    })

    it('handles small numbers without separators', () => {
      expect(formatLocaleNumber(0)).toBe('0')
      expect(formatLocaleNumber(42)).toBe('42')
    })

    it('formats negative numbers', () => {
      expect(formatLocaleNumber(-1234)).toBe('-1,234')
    })

    it('returns em dash for null / undefined', () => {
      expect(formatLocaleNumber(null)).toBe('—')
      expect(formatLocaleNumber(undefined)).toBe('—')
    })

    it('returns em dash for NaN and Infinity', () => {
      expect(formatLocaleNumber(NaN)).toBe('—')
      expect(formatLocaleNumber(Infinity)).toBe('—')
      expect(formatLocaleNumber(-Infinity)).toBe('—')
    })
  })

  describe('formatLocaleTime', () => {
    it('returns a 24-hour Korean-locale clock string with no AM/PM marker', () => {
      const date = new Date(2026, 3, 25, 17, 44, 12)
      const out = formatLocaleTime(date)
      // ko-KR Intl output uses Korean unit suffixes (e.g. '17시 44분 12초').
      // We assert on the digit pattern + absence of an AM/PM marker so this
      // test stays robust if Intl's formatting tweaks the separator.
      expect(out).toMatch(/17/)
      expect(out).toMatch(/44/)
      expect(out).not.toMatch(/AM|PM|오전|오후/)
    })
  })

  describe('formatLocaleDateTime', () => {
    it('formats a Date instance', () => {
      const date = new Date('2026-04-25T17:44:00Z')
      const out = formatLocaleDateTime(date)
      expect(out).not.toBe('—')
      expect(out.length).toBeGreaterThan(0)
    })

    it('formats an ISO string', () => {
      const out = formatLocaleDateTime('2026-04-25T17:44:00Z')
      expect(out).not.toBe('—')
      expect(out.length).toBeGreaterThan(0)
    })

    it('formats an epoch ms number', () => {
      const out = formatLocaleDateTime(1745603040000)
      expect(out).not.toBe('—')
      expect(out.length).toBeGreaterThan(0)
    })

    it('returns em dash for null / undefined / empty string', () => {
      expect(formatLocaleDateTime(null)).toBe('—')
      expect(formatLocaleDateTime(undefined)).toBe('—')
      expect(formatLocaleDateTime('')).toBe('—')
    })

    it('returns em dash for invalid date input', () => {
      expect(formatLocaleDateTime('not-a-date')).toBe('—')
      expect(formatLocaleDateTime(NaN)).toBe('—')
    })
  })
})

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import '../../i18n/config'
import { useRelativeTime } from '../useRelativeTime'

describe('useRelativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns initial relative value for an epoch input', () => {
    const fiveMinAgo = Date.now() - 5 * 60_000
    const { result } = renderHook(() => useRelativeTime(fiveMinAgo))
    expect(result.current).toBe('5분 전')
  })

  it('returns empty string for null / undefined input', () => {
    const { result: nullResult } = renderHook(() => useRelativeTime(null))
    expect(nullResult.current).toBe('')

    const { result: undefResult } = renderHook(() => useRelativeTime(undefined))
    expect(undefResult.current).toBe('')
  })

  it('returns empty string for unparseable input', () => {
    const { result } = renderHook(() => useRelativeTime('not-a-date'))
    expect(result.current).toBe('')
  })

  it('updates the rendered value as wall-clock time advances', () => {
    // formatRelativeTimeKo collapses anything <60s to "방금 전", so we anchor
    // the test on a minute-scale timestamp and tick across a minute boundary
    // to verify the auto-refresh.
    const start = Date.now() - 1 * 60_000 // 1 minute ago
    const { result } = renderHook(() => useRelativeTime(start))
    expect(result.current).toBe('1분 전')

    // Adaptive cadence for sub-hour timestamps is 30s — vitest fake timers
    // advance both Date.now() and the scheduler in lock-step.
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(result.current).toBe('2분 전')
  })

  it('respects an explicit tickSeconds override', () => {
    const start = Date.now() - 1 * 60_000
    const { result } = renderHook(() => useRelativeTime(start, { tickSeconds: 120 }))
    expect(result.current).toBe('1분 전')

    // 30s adaptive default would have ticked already, but we forced 120s so the
    // value should still be the original render even after 60s of advance.
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(result.current).toBe('1분 전')

    // After another 60s the 120s interval fires; total elapsed = 3 minutes.
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(result.current).toBe('3분 전')
  })

  it('uses a custom formatFn when provided', () => {
    const formatFn = vi.fn(() => 'custom-output')
    const { result } = renderHook(() => useRelativeTime(Date.now() - 1000, { formatFn }))
    expect(result.current).toBe('custom-output')
    expect(formatFn).toHaveBeenCalled()
  })

  it('does not schedule an interval for null input', () => {
    const setIntervalSpy = vi.spyOn(global, 'setInterval')
    renderHook(() => useRelativeTime(null))
    expect(setIntervalSpy).not.toHaveBeenCalled()
    setIntervalSpy.mockRestore()
  })

  it('does not schedule an interval for invalid input', () => {
    const setIntervalSpy = vi.spyOn(global, 'setInterval')
    renderHook(() => useRelativeTime('not-a-date'))
    expect(setIntervalSpy).not.toHaveBeenCalled()
    setIntervalSpy.mockRestore()
  })

  it('cleans up interval on unmount', () => {
    const clearIntervalSpy = vi.spyOn(global, 'clearInterval')
    const { unmount } = renderHook(() => useRelativeTime(Date.now() - 1000))
    unmount()
    expect(clearIntervalSpy).toHaveBeenCalled()
    clearIntervalSpy.mockRestore()
  })

  it('uses adaptive 30s cadence for timestamps under one hour', () => {
    const start = Date.now() - 5 * 60_000 // 5 minutes ago — falls in the 30s bucket
    const { result } = renderHook(() => useRelativeTime(start))
    expect(result.current).toBe('5분 전')

    // 5s of advance does not cross a minute boundary — string still 5분 전.
    act(() => {
      vi.advanceTimersByTime(5_000)
    })
    expect(result.current).toBe('5분 전')

    // After 60s total elapsed the rendered string updates to 6분 전.
    act(() => {
      vi.advanceTimersByTime(55_000)
    })
    expect(result.current).toBe('6분 전')
  })

  it('uses adaptive 5min cadence for timestamps older than one hour', () => {
    const setIntervalSpy = vi.spyOn(global, 'setInterval')
    const start = Date.now() - 2 * 3_600_000 // 2 hours ago
    renderHook(() => useRelativeTime(start))
    // Last setInterval call should have been with 300_000 ms
    const lastCall = setIntervalSpy.mock.calls.at(-1)
    expect(lastCall?.[1]).toBe(300_000)
    setIntervalSpy.mockRestore()
  })
})

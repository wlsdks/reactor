import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useClockDisplay } from '../useClockDisplay'

describe('useClockDisplay', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns time and date strings', () => {
    vi.setSystemTime(new Date('2026-03-26T14:30:00'))
    const { result } = renderHook(() => useClockDisplay())
    expect(result.current.time).toBeTruthy()
    expect(result.current.date).toBeTruthy()
  })

  it('updates every second', () => {
    vi.setSystemTime(new Date('2026-03-26T14:30:00'))
    const { result } = renderHook(() => useClockDisplay())
    const initialTime = result.current.time

    vi.setSystemTime(new Date('2026-03-26T14:30:05'))
    act(() => { vi.advanceTimersByTime(5000) })

    expect(result.current.time).not.toBe(initialTime)
  })

  it('cleans up interval on unmount', () => {
    const clearIntervalSpy = vi.spyOn(global, 'clearInterval')
    const { unmount } = renderHook(() => useClockDisplay())
    unmount()
    expect(clearIntervalSpy).toHaveBeenCalled()
    clearIntervalSpy.mockRestore()
  })
})

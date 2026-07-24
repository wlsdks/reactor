import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useDebouncedValue } from '../useDebouncedValue'

describe('useDebouncedValue', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns the initial value immediately', () => {
    const { result } = renderHook(() => useDebouncedValue('hello', 250))
    expect(result.current).toBe('hello')
  })

  it('debounces updates by the specified delay (250ms default)', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 250),
      { initialProps: { value: 'a' } },
    )
    expect(result.current).toBe('a')

    rerender({ value: 'ab' })
    // Not yet — still within debounce window
    expect(result.current).toBe('a')

    act(() => { vi.advanceTimersByTime(249) })
    expect(result.current).toBe('a')

    act(() => { vi.advanceTimersByTime(1) })
    expect(result.current).toBe('ab')
  })

  it('resets the timer on rapid changes', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 250),
      { initialProps: { value: '' } },
    )

    rerender({ value: 'h' })
    act(() => { vi.advanceTimersByTime(100) })
    rerender({ value: 'he' })
    act(() => { vi.advanceTimersByTime(100) })
    rerender({ value: 'hel' })
    // Still showing initial value, since each change reset the timer
    expect(result.current).toBe('')

    act(() => { vi.advanceTimersByTime(250) })
    expect(result.current).toBe('hel')
  })
})

import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useFormDraft } from '../useFormDraft'

const STORAGE_PREFIX = 'reactor-admin-draft:'

describe('useFormDraft', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    window.localStorage.clear()
  })

  it('returns null recoveredDraft when storage is empty', () => {
    const { result } = renderHook(() =>
      useFormDraft({ storageKey: 'test:create', values: { name: '' } }),
    )
    expect(result.current.recoveredDraft).toBeNull()
    expect(result.current.recoveredAt).toBeNull()
  })

  it('debounces writes to localStorage by 1500ms by default', () => {
    const { rerender } = renderHook(
      ({ values }) => useFormDraft({ storageKey: 'test:debounce', values }),
      { initialProps: { values: { name: '' } } },
    )

    // No write yet (initial render schedules a write but timer hasn't fired).
    expect(window.localStorage.getItem(`${STORAGE_PREFIX}test:debounce`)).toBeNull()

    rerender({ values: { name: 'a' } })
    rerender({ values: { name: 'ab' } })

    // Within debounce window — still nothing persisted.
    act(() => { vi.advanceTimersByTime(1499) })
    expect(window.localStorage.getItem(`${STORAGE_PREFIX}test:debounce`)).toBeNull()

    act(() => { vi.advanceTimersByTime(1) })
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}test:debounce`)
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!) as { values: { name: string }; savedAt: string }
    expect(parsed.values).toEqual({ name: 'ab' })
    expect(typeof parsed.savedAt).toBe('string')
  })

  it('honors a custom debounceMs value', () => {
    const { rerender } = renderHook(
      ({ values }) => useFormDraft({ storageKey: 'test:custom-ms', values, debounceMs: 50 }),
      { initialProps: { values: { name: '' } } },
    )

    rerender({ values: { name: 'fast' } })
    act(() => { vi.advanceTimersByTime(49) })
    expect(window.localStorage.getItem(`${STORAGE_PREFIX}test:custom-ms`)).toBeNull()

    act(() => { vi.advanceTimersByTime(1) })
    expect(window.localStorage.getItem(`${STORAGE_PREFIX}test:custom-ms`)).not.toBeNull()
  })

  it('exposes the persisted draft to the next mount as recoveredDraft', () => {
    // Seed storage as if a prior session had written a draft.
    window.localStorage.setItem(
      `${STORAGE_PREFIX}test:recover`,
      JSON.stringify({ values: { name: 'restored' }, savedAt: '2026-04-24T00:00:00.000Z' }),
    )

    const { result } = renderHook(() =>
      useFormDraft<{ name: string }>({ storageKey: 'test:recover', values: { name: '' } }),
    )

    expect(result.current.recoveredDraft).toEqual({ name: 'restored' })
    expect(result.current.recoveredAt).toBe('2026-04-24T00:00:00.000Z')
  })

  it('clearDraft removes the storage entry and resets state', () => {
    window.localStorage.setItem(
      `${STORAGE_PREFIX}test:clear`,
      JSON.stringify({ values: { name: 'x' }, savedAt: '2026-04-24T00:00:00.000Z' }),
    )

    const { result } = renderHook(() =>
      useFormDraft<{ name: string }>({ storageKey: 'test:clear', values: { name: '' } }),
    )
    expect(result.current.recoveredDraft).toEqual({ name: 'x' })

    act(() => { result.current.clearDraft() })

    expect(window.localStorage.getItem(`${STORAGE_PREFIX}test:clear`)).toBeNull()
    expect(result.current.recoveredDraft).toBeNull()
    expect(result.current.recoveredAt).toBeNull()
    expect(result.current.isDirtyPending).toBe(false)
  })

  it('dismissRecovery removes the storage entry and resets recovered state', () => {
    window.localStorage.setItem(
      `${STORAGE_PREFIX}test:dismiss`,
      JSON.stringify({ values: { name: 'y' }, savedAt: '2026-04-24T00:00:00.000Z' }),
    )

    const { result } = renderHook(() =>
      useFormDraft<{ name: string }>({ storageKey: 'test:dismiss', values: { name: '' } }),
    )

    act(() => { result.current.dismissRecovery() })

    expect(window.localStorage.getItem(`${STORAGE_PREFIX}test:dismiss`)).toBeNull()
    expect(result.current.recoveredDraft).toBeNull()
  })

  it('acceptRecovery clears recoveredDraft state without touching storage', () => {
    window.localStorage.setItem(
      `${STORAGE_PREFIX}test:accept`,
      JSON.stringify({ values: { name: 'z' }, savedAt: '2026-04-24T00:00:00.000Z' }),
    )

    const { result } = renderHook(() =>
      useFormDraft<{ name: string }>({ storageKey: 'test:accept', values: { name: '' } }),
    )

    act(() => { result.current.acceptRecovery() })

    // The caller is expected to keep typing (which will rewrite storage). The
    // hook does not erase the entry on accept — the next debounced write does.
    expect(result.current.recoveredDraft).toBeNull()
  })

  it('does nothing when enabled is false', () => {
    window.localStorage.setItem(
      `${STORAGE_PREFIX}test:disabled`,
      JSON.stringify({ values: { name: 'persisted' }, savedAt: '2026-04-24T00:00:00.000Z' }),
    )

    const { result, rerender } = renderHook(
      ({ values, enabled }) =>
        useFormDraft<{ name: string }>({
          storageKey: 'test:disabled',
          values,
          enabled,
        }),
      { initialProps: { values: { name: 'changed' }, enabled: false } },
    )

    expect(result.current.recoveredDraft).toBeNull()
    rerender({ values: { name: 'changed-again' }, enabled: false })

    act(() => { vi.advanceTimersByTime(2000) })

    // Storage should still hold the prior payload — nothing was written.
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}test:disabled`)
    expect(raw).not.toBeNull()
    expect(JSON.parse(raw!).values).toEqual({ name: 'persisted' })
  })

  it('refreshes recovered draft when storageKey changes (e.g. switching record id)', () => {
    window.localStorage.setItem(
      `${STORAGE_PREFIX}edit:1`,
      JSON.stringify({ values: { name: 'one' }, savedAt: '2026-04-24T00:00:00.000Z' }),
    )
    window.localStorage.setItem(
      `${STORAGE_PREFIX}edit:2`,
      JSON.stringify({ values: { name: 'two' }, savedAt: '2026-04-24T00:00:00.000Z' }),
    )

    const { result, rerender } = renderHook(
      ({ key }) =>
        useFormDraft<{ name: string }>({ storageKey: key, values: { name: '' } }),
      { initialProps: { key: 'edit:1' } },
    )

    expect(result.current.recoveredDraft).toEqual({ name: 'one' })

    rerender({ key: 'edit:2' })
    expect(result.current.recoveredDraft).toEqual({ name: 'two' })
  })

  it('isDirtyPending is true while a write is queued and false after it lands', () => {
    const { result, rerender } = renderHook(
      ({ values }) => useFormDraft({ storageKey: 'test:dirty', values }),
      { initialProps: { values: { name: '' } } },
    )

    rerender({ values: { name: 'pending' } })
    expect(result.current.isDirtyPending).toBe(true)

    act(() => { vi.advanceTimersByTime(1500) })
    expect(result.current.isDirtyPending).toBe(false)
  })
})

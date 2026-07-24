import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { useInlineEdit } from '../useInlineEdit'

describe('useInlineEdit', () => {
  it('starts in idle state with the initial value', () => {
    const { result } = renderHook(() =>
      useInlineEdit({ initial: 'hello', onCommit: vi.fn() }),
    )
    expect(result.current.isEditing).toBe(false)
    expect(result.current.value).toBe('hello')
    expect(result.current.status).toBe('idle')
    expect(result.current.error).toBeNull()
  })

  it('start() enters editing mode and seeds the draft from initial', () => {
    const { result, rerender } = renderHook(
      ({ initial }: { initial: string }) =>
        useInlineEdit({ initial, onCommit: vi.fn() }),
      { initialProps: { initial: 'hello' } },
    )

    rerender({ initial: 'world' })
    act(() => result.current.start())

    expect(result.current.isEditing).toBe(true)
    expect(result.current.status).toBe('editing')
    expect(result.current.value).toBe('world')
  })

  it('setValue updates the draft and clears stale errors when valid', () => {
    const validate = vi.fn((next: string) => (next.length === 0 ? 'required' : null))
    const { result } = renderHook(() =>
      useInlineEdit({ initial: 'a', validate, onCommit: vi.fn() }),
    )

    act(() => result.current.start())

    act(() => result.current.setValue(''))
    expect(result.current.error).toBe('required')
    expect(result.current.status).toBe('error')

    act(() => result.current.setValue('ok'))
    expect(result.current.error).toBeNull()
    expect(result.current.status).toBe('editing')
  })

  it('commit() runs the validator and skips onCommit when invalid', async () => {
    const onCommit = vi.fn()
    const validate = vi.fn((next: string) => (next === '' ? 'required' : null))
    const { result } = renderHook(() =>
      useInlineEdit({ initial: '', validate, onCommit }),
    )

    act(() => result.current.start())
    await act(async () => {
      await result.current.commit()
    })

    expect(onCommit).not.toHaveBeenCalled()
    expect(result.current.status).toBe('error')
    expect(result.current.error).toBe('required')
    // Editor stays mounted so the user can fix the value.
    expect(result.current.isEditing).toBe(true)
  })

  it('commit() awaits the async handler, transitions through submitting → idle', async () => {
    let resolve: (() => void) | undefined
    const onCommit = vi.fn(
      () =>
        new Promise<void>((res) => {
          resolve = res
        }),
    )
    const { result } = renderHook(() =>
      useInlineEdit({ initial: 'a', onCommit }),
    )

    act(() => result.current.start())
    act(() => result.current.setValue('b'))

    let commitPromise!: Promise<void>
    act(() => {
      commitPromise = result.current.commit()
    })
    expect(result.current.status).toBe('submitting')

    await act(async () => {
      resolve!()
      await commitPromise
    })

    expect(onCommit).toHaveBeenCalledWith('b')
    expect(result.current.status).toBe('idle')
    expect(result.current.isEditing).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('commit() captures async errors into local error state and stays editing', async () => {
    const onCommit = vi.fn(() => Promise.reject(new Error('boom')))
    const { result } = renderHook(() =>
      useInlineEdit({ initial: 'a', onCommit }),
    )

    act(() => result.current.start())
    act(() => result.current.setValue('b'))

    await act(async () => {
      await result.current.commit()
    })

    expect(result.current.status).toBe('error')
    expect(result.current.error).toBe('boom')
    expect(result.current.isEditing).toBe(true)
  })

  it('cancel() restores initial value, exits edit mode, fires onCancel', () => {
    const onCancel = vi.fn()
    const { result } = renderHook(() =>
      useInlineEdit({ initial: 'a', onCommit: vi.fn(), onCancel }),
    )

    act(() => result.current.start())
    act(() => result.current.setValue('z'))
    expect(result.current.value).toBe('z')

    act(() => result.current.cancel())

    expect(result.current.value).toBe('a')
    expect(result.current.isEditing).toBe(false)
    expect(result.current.status).toBe('idle')
    expect(result.current.error).toBeNull()
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('blocks re-entrant commits while a submission is in flight', async () => {
    let resolve: (() => void) | undefined
    const onCommit = vi.fn(
      () =>
        new Promise<void>((res) => {
          resolve = res
        }),
    )
    const { result } = renderHook(() => useInlineEdit({ initial: 'a', onCommit }))

    act(() => result.current.start())
    act(() => result.current.setValue('b'))

    let firstPromise!: Promise<void>
    act(() => {
      firstPromise = result.current.commit()
    })
    // A second commit during submitting should be a no-op.
    await act(async () => {
      await result.current.commit()
    })
    expect(onCommit).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolve!()
      await firstPromise
    })

    await waitFor(() => expect(result.current.status).toBe('idle'))
  })
})

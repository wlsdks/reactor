import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { scheduleUndoableDelete } from '../scheduleUndoableDelete'
import { useToastStore } from '../../store/toast.store'

function clearToasts() {
  useToastStore.setState({ toasts: [] })
}

describe('scheduleUndoableDelete', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    clearToasts()
  })

  afterEach(() => {
    vi.useRealTimers()
    clearToasts()
  })

  it('runs the optimistic mutation immediately and shows a success toast with an undo action', () => {
    const optimistic = vi.fn()
    const restore = vi.fn()
    const commit = vi.fn().mockResolvedValue(undefined)

    scheduleUndoableDelete({
      message: 'Deleted item',
      undoLabel: 'Undo',
      undoneMessage: 'Restored',
      optimistic,
      restore,
      commit,
    })

    expect(optimistic).toHaveBeenCalledTimes(1)

    const toasts = useToastStore.getState().toasts
    expect(toasts).toHaveLength(1)
    expect(toasts[0].message).toBe('Deleted item')
    expect(toasts[0].type).toBe('success')
    expect(toasts[0].action?.label).toBe('Undo')
    // commit must not run before the grace window elapses
    expect(commit).not.toHaveBeenCalled()
    expect(restore).not.toHaveBeenCalled()
  })

  it('commits the deletion automatically once the grace window elapses', async () => {
    const optimistic = vi.fn()
    const restore = vi.fn()
    const commit = vi.fn().mockResolvedValue(undefined)
    const onSuccess = vi.fn()

    scheduleUndoableDelete({
      message: 'Deleted item',
      undoLabel: 'Undo',
      undoneMessage: 'Restored',
      optimistic,
      restore,
      commit,
      onSuccess,
      graceMs: 5000,
    })

    expect(commit).not.toHaveBeenCalled()
    vi.advanceTimersByTime(4999)
    expect(commit).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(commit).toHaveBeenCalledTimes(1)
    expect(restore).not.toHaveBeenCalled()

    // Drain the resolved commit promise so onSuccess fires before assertions.
    await vi.runAllTimersAsync()
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  it('clicking the undo action cancels the pending commit and runs restore', () => {
    const optimistic = vi.fn()
    const restore = vi.fn()
    const commit = vi.fn().mockResolvedValue(undefined)

    scheduleUndoableDelete({
      message: 'Deleted item',
      undoLabel: 'Undo',
      undoneMessage: 'Restored',
      optimistic,
      restore,
      commit,
    })

    // Trigger the toast action.
    const toast = useToastStore.getState().toasts[0]
    expect(toast.action).toBeDefined()
    toast.action!.onAction()

    expect(restore).toHaveBeenCalledTimes(1)

    // Inspect the "undone" confirmation toast immediately, before any timers
    // fire (the info toast has its own ~4s auto-dismiss).
    const toasts = useToastStore.getState().toasts
    const undoneToast = toasts.find((t) => t.message === 'Restored')
    expect(undoneToast?.type).toBe('info')

    // Even after the grace window, commit must never fire.
    vi.advanceTimersByTime(10000)
    expect(commit).not.toHaveBeenCalled()
  })

  it('forwards commit errors to onError', async () => {
    const error = new Error('boom')
    const onError = vi.fn()

    scheduleUndoableDelete({
      message: 'Deleted item',
      undoLabel: 'Undo',
      undoneMessage: 'Restored',
      optimistic: vi.fn(),
      restore: vi.fn(),
      commit: vi.fn().mockRejectedValue(error),
      onError,
    })

    vi.advanceTimersByTime(5000)
    await vi.runAllTimersAsync()

    expect(onError).toHaveBeenCalledWith(error)
  })

  it('cancel() stops both the timer and any future undo handling', () => {
    const restore = vi.fn()
    const commit = vi.fn().mockResolvedValue(undefined)

    const handle = scheduleUndoableDelete({
      message: 'Deleted item',
      undoLabel: 'Undo',
      undoneMessage: 'Restored',
      optimistic: vi.fn(),
      restore,
      commit,
    })

    handle.cancel()
    vi.advanceTimersByTime(10000)
    expect(commit).not.toHaveBeenCalled()
    expect(restore).not.toHaveBeenCalled()
  })

  it('respects a custom graceMs override (used by tests / one-offs)', () => {
    const commit = vi.fn().mockResolvedValue(undefined)
    scheduleUndoableDelete({
      message: 'Deleted item',
      undoLabel: 'Undo',
      undoneMessage: 'Restored',
      optimistic: vi.fn(),
      restore: vi.fn(),
      commit,
      graceMs: 500,
    })

    vi.advanceTimersByTime(499)
    expect(commit).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(commit).toHaveBeenCalledTimes(1)
  })
})

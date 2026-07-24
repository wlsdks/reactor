import { useCallback, useState } from 'react'

export type InlineEditStatus = 'idle' | 'editing' | 'submitting' | 'error'

export interface UseInlineEditOptions<T> {
  /**
   * The committed source value. The editor snaps back to this whenever
   * `cancel()` runs or the editor reopens after a previous successful commit.
   */
  initial: T
  /**
   * Synchronous validator. Returns an error message when the value is not
   * acceptable, or `null` when the value is acceptable. Validation runs at
   * `commit` time and also on every `setValue` call so the consumer can
   * disable Enter/blur commits as the user types.
   */
  validate?: (next: T) => string | null
  /**
   * Persist the next value. May return a Promise; while it pends the hook
   * exposes a `submitting` status. Errors thrown from `onCommit` are caught
   * and surfaced via the local `error` state — the hook never re-throws so
   * callers do not need a try/catch around `commit()`.
   */
  onCommit: (next: T) => Promise<void> | void
  /**
   * Optional hook for the consumer to react when the editor is dismissed
   * without committing (Escape, outside-click cancel, explicit cancel button).
   */
  onCancel?: () => void
}

export interface InlineEditApi<T> {
  /** True while the editor is mounted (after `start`, before `commit`/`cancel`). */
  isEditing: boolean
  /** Current draft value held by the editor. */
  value: T
  /** Update the draft value (also re-runs `validate`). */
  setValue: (next: T) => void
  /** Enter edit mode. Resets the draft to the latest `initial`. */
  start: () => void
  /**
   * Persist the draft. Awaits `onCommit`; on success exits edit mode, on
   * failure leaves the editor mounted with `status: 'error'` and a populated
   * `error` message so the consumer can re-edit and retry.
   */
  commit: () => Promise<void>
  /** Discard the draft, restore `initial`, exit edit mode. */
  cancel: () => void
  status: InlineEditStatus
  /** Latest validation or commit-time error message; `null` when none. */
  error: string | null
}

/**
 * Headless state machine for a single inline-edit cell.
 *
 * Lifecycle:
 *   idle → editing → submitting → idle (success)
 *                              ↘ error (commit failure, stays editing)
 *   editing → idle (cancel)
 *
 * The hook is intentionally headless (no DOM, no input refs) so the same
 * primitive can drive an `<input>`, a `<select>`, a textarea, or any future
 * custom editor (date picker, tag chip, etc.).
 */
export function useInlineEdit<T>(options: UseInlineEditOptions<T>): InlineEditApi<T> {
  const { initial, validate, onCommit, onCancel } = options

  const [isEditing, setIsEditing] = useState(false)
  const [value, setValueState] = useState<T>(initial)
  const [status, setStatus] = useState<InlineEditStatus>('idle')
  const [error, setError] = useState<string | null>(null)

  const setValue = useCallback(
    (next: T) => {
      setValueState(next)
      // Re-run validation eagerly so the consumer can render an inline error
      // and disable a Save button before the user presses Enter.
      const validationError = validate ? validate(next) : null
      if (validationError) {
        setError(validationError)
        setStatus('error')
      } else {
        setError(null)
        // Only reset back to "editing" when we are not mid-submit. Submitting
        // status must be preserved until `onCommit` settles.
        setStatus(prev => (prev === 'submitting' ? prev : 'editing'))
      }
    },
    [validate],
  )

  const start = useCallback(() => {
    setValueState(initial)
    setError(null)
    setStatus('editing')
    setIsEditing(true)
  }, [initial])

  const cancel = useCallback(() => {
    setValueState(initial)
    setError(null)
    setStatus('idle')
    setIsEditing(false)
    onCancel?.()
  }, [initial, onCancel])

  const commit = useCallback(async () => {
    // Block commits while a previous commit is still in flight to prevent
    // double-submit races (Enter mash, blur+Enter combos, etc.).
    if (status === 'submitting') return

    const validationError = validate ? validate(value) : null
    if (validationError) {
      setError(validationError)
      setStatus('error')
      return
    }

    setStatus('submitting')
    setError(null)
    try {
      await onCommit(value)
      setStatus('idle')
      setIsEditing(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(message || 'Commit failed')
      setStatus('error')
      // Stay in editing mode so the user can fix the value and retry without
      // losing their draft.
    }
  }, [onCommit, status, validate, value])

  return {
    isEditing,
    value,
    setValue,
    start,
    commit,
    cancel,
    status,
    error,
  }
}

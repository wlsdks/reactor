import { useToastStore } from '../store/toast.store'

/**
 * Default grace period during which the user can hit "undo" before the actual
 * delete API call fires. Toast `duration` mirrors this so the toast disappears
 * exactly when the commit runs.
 */
export const UNDOABLE_DELETE_GRACE_MS = 5000

export interface ScheduleUndoableDeleteOptions {
  /**
   * Friendly success-style toast message shown immediately, e.g.
   *   `"\"Sales Bot\" 페르소나를 삭제했어요"`
   * The "실행 취소" action button is appended automatically.
   */
  message: string
  /** Localized label for the undo action button (e.g. `t('common.undo')`). */
  undoLabel: string
  /** Toast shown when the user clicks undo. */
  undoneMessage: string
  /**
   * Apply the optimistic UI removal (remove row from list, clear detail
   * selection, etc.). Runs synchronously before the toast appears.
   */
  optimistic: () => void
  /**
   * Restore the optimistic mutation when the user undoes. Runs synchronously
   * before the secondary "undo confirmed" toast appears.
   */
  restore: () => void
  /**
   * The actual API mutation. Runs after the grace period elapses without an
   * undo. Errors are forwarded to `onError`; the optimistic UI is **not**
   * automatically restored — callers control whether the row reappears via
   * an explicit `restore()` call inside `onError`.
   */
  commit: () => Promise<unknown>
  /** Invoked after `commit` resolves successfully. */
  onSuccess?: () => void
  /** Invoked when `commit` rejects. */
  onError?: (error: unknown) => void
  /** Override the grace period for tests / one-off flows. Defaults to 5s. */
  graceMs?: number
}

/**
 * Schedule an "optimistic delete + undo grace" flow.
 *
 * The optimistic UI mutation runs immediately so the row disappears with no
 * latency. A success-style toast is shown with an "실행 취소" action; if the
 * user clicks it inside the grace window the timer is cleared, the optimistic
 * mutation is reverted via `restore()`, and the API call never fires. If the
 * grace period elapses untouched, `commit()` runs and the deletion is final.
 *
 * Returns the timer handle so callers can cancel it explicitly if the
 * surrounding component unmounts mid-flight (rare but documented for safety).
 */
export function scheduleUndoableDelete(opts: ScheduleUndoableDeleteOptions): {
  cancel: () => void
} {
  const graceMs = opts.graceMs ?? UNDOABLE_DELETE_GRACE_MS
  let undone = false
  let committed = false

  // 1. Apply optimistic mutation immediately.
  opts.optimistic()

  // 2. Schedule the actual API call.
  const timer = setTimeout(() => {
    if (undone) return
    committed = true
    opts.commit().then(
      () => opts.onSuccess?.(),
      (err) => opts.onError?.(err),
    )
  }, graceMs)

  // 3. Show toast with undo action.
  useToastStore.getState().addToast({
    type: 'success',
    message: opts.message,
    duration: graceMs,
    action: {
      label: opts.undoLabel,
      onAction: () => {
        // Race guard: if the user reaches for undo just as the commit fires,
        // we still cancel the timer but the network call may already be
        // in-flight. We still restore the UI so the row is visible again, and
        // the next list refetch / cache invalidate will reconcile. The
        // `committed` flag is checked so we don't show the "undone" toast
        // when the work has already been performed.
        if (committed || undone) return
        undone = true
        clearTimeout(timer)
        opts.restore()
        useToastStore.getState().addToast({
          type: 'info',
          message: opts.undoneMessage,
        })
      },
    },
  })

  return {
    cancel: () => {
      undone = true
      clearTimeout(timer)
    },
  }
}

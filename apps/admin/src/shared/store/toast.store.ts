import { create } from 'zustand'

type ToastType = 'success' | 'error' | 'info' | 'warning'

export interface ToastAction {
  label: string
  onAction: () => void
  /** Whether to close the toast after invoking onAction. Defaults to true. */
  closeOnAction?: boolean
}

export interface Toast {
  id: string
  type: ToastType
  message: string
  /** Optional action button rendered on the right of the toast. */
  action?: ToastAction
  /** Auto-dismiss duration in ms. When omitted, duration is derived from type
   *  (info/success: 4000, warning: 6000, error: 8000) plus +2000ms when an
   *  action is present. */
  duration?: number
  /** Monotonic insertion order, used as a tie-breaker for priority sort.
   *  Optional so that pre-existing call sites and test fixtures that manually
   *  build toasts without a counter still type-check. */
  createdAt?: number
}

export interface AddToastInput {
  type: ToastType
  message: string
  action?: ToastAction
  duration?: number
}

interface ToastStore {
  toasts: Toast[]
  /** Whether the overflow queue is expanded (renders all toasts when true). */
  expandQueue: boolean
  addToast: (toast: AddToastInput) => void
  removeToast: (id: string) => void
  /** Pause the auto-dismiss timer for a toast (e.g., on hover). */
  pauseToast: (id: string) => void
  /** Resume the auto-dismiss timer for a toast (e.g., on mouse leave). */
  resumeToast: (id: string) => void
  /** Toggle / set the overflow expanded state. */
  setExpandQueue: (open: boolean) => void
}

interface TimerState {
  timeoutId: ReturnType<typeof setTimeout>
  /** ms remaining when the timer was last (re)started. */
  remaining: number
  /** Wall-clock time when the timer was last (re)started. */
  startedAt: number
}

let toastCounter = 0
const timers = new Map<string, TimerState>()

const BASE_DURATIONS: Record<ToastType, number> = {
  info: 4000,
  success: 4000,
  warning: 6000,
  error: 8000,
}

const ACTION_BONUS_MS = 2000

/** Maximum number of toasts rendered at once before the overflow pill appears. */
export const MAX_VISIBLE_TOASTS = 5

/** Priority weight used when sorting visible toasts (higher = more urgent). */
const TYPE_PRIORITY: Record<ToastType, number> = {
  error: 4,
  warning: 3,
  info: 2,
  success: 1,
}

export function getDefaultDuration(type: ToastType, hasAction: boolean): number {
  return BASE_DURATIONS[type] + (hasAction ? ACTION_BONUS_MS : 0)
}

/**
 * Sort toasts by priority (error > warning > info > success). Within the same
 * priority bucket, the newest toast wins so freshly added items surface first.
 */
function sortByPriority(toasts: readonly Toast[]): Toast[] {
  return [...toasts].sort((a, b) => {
    const priorityDelta = TYPE_PRIORITY[b.type] - TYPE_PRIORITY[a.type]
    if (priorityDelta !== 0) return priorityDelta
    return (b.createdAt ?? 0) - (a.createdAt ?? 0)
  })
}

/** Selector: first MAX_VISIBLE_TOASTS toasts ranked by priority + recency. */
export function selectVisibleToasts(state: Pick<ToastStore, 'toasts'>): Toast[] {
  return sortByPriority(state.toasts).slice(0, MAX_VISIBLE_TOASTS)
}

/** Selector: count of toasts hidden behind the overflow pill. */
export function selectOverflowCount(state: Pick<ToastStore, 'toasts'>): number {
  return Math.max(0, state.toasts.length - MAX_VISIBLE_TOASTS)
}

/** Selector: full priority-sorted toast list (used when expanded). */
export function selectAllToastsSorted(state: Pick<ToastStore, 'toasts'>): Toast[] {
  return sortByPriority(state.toasts)
}

function scheduleDismiss(id: string, ms: number, dismiss: (id: string) => void) {
  const timeoutId = setTimeout(() => {
    timers.delete(id)
    dismiss(id)
  }, ms)
  timers.set(id, { timeoutId, remaining: ms, startedAt: Date.now() })
}

export const useToastStore = create<ToastStore>((set) => {
  const dismiss = (id: string) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }))

  return {
    toasts: [],
    expandQueue: false,
    addToast: ({ type, message, action, duration }) => {
      const id = `toast-${++toastCounter}-${Date.now()}`
      const ms = duration ?? getDefaultDuration(type, Boolean(action))
      set((state) => ({
        toasts: [
          ...state.toasts,
          { id, type, message, action, duration, createdAt: toastCounter },
        ],
      }))
      scheduleDismiss(id, ms, dismiss)
    },
    removeToast: (id) => {
      const t = timers.get(id)
      if (t) {
        clearTimeout(t.timeoutId)
        timers.delete(id)
      }
      dismiss(id)
    },
    pauseToast: (id) => {
      const t = timers.get(id)
      if (!t) return
      clearTimeout(t.timeoutId)
      const elapsed = Date.now() - t.startedAt
      const remaining = Math.max(0, t.remaining - elapsed)
      // Keep the entry but mark as paused via remaining; clear stored timeout id by replacing.
      timers.set(id, {
        timeoutId: 0 as unknown as ReturnType<typeof setTimeout>,
        remaining,
        startedAt: Date.now(),
      })
    },
    resumeToast: (id) => {
      const t = timers.get(id)
      if (!t) return
      // If the timeoutId is the sentinel (paused state), restart with remaining.
      // We detect the paused state by checking that timeoutId looks falsy (0).
      // Note: in JSDOM/Node setTimeout returns an object/number; 0 is our paused sentinel.
      if ((t.timeoutId as unknown as number) === 0) {
        scheduleDismiss(id, t.remaining, dismiss)
      }
    },
    setExpandQueue: (open) => set({ expandQueue: open }),
  }
})

import { useToastStore, type ToastAction } from '../store/toast.store'
import { resolveApiError, type ResolvedApiError } from './getErrorMessage'

interface ShowApiErrorToastOptions {
  /** Wired into recovery action when type === 'retry'. */
  onRetry?: () => void
  /** Wired into recovery action when type === 'login'. */
  onLogin?: () => void
}

/**
 * Surface an unknown error as a toast with a localized message and an
 * optional recovery action button.
 *
 * Behaviour:
 * - For `retry` / `login` recovery types the caller-supplied callbacks are
 *   invoked when the action is clicked. If the corresponding callback is not
 *   provided, the action button is omitted (no dead buttons).
 * - For `docs` / `contact` recovery types, the helper opens `recovery.href`
 *   in a new tab when present, otherwise the action is omitted.
 * - The hint, when present, is appended to the message on a new line so the
 *   single-line toast surface still carries the guidance.
 */
export function showApiErrorToast(
  error: unknown,
  opts: ShowApiErrorToastOptions = {},
): ResolvedApiError {
  const resolved = resolveApiError(error)
  const action = buildToastAction(resolved, opts)
  const fullMessage = resolved.hint
    ? `${resolved.message}\n${resolved.hint}`
    : resolved.message

  useToastStore.getState().addToast({
    type: 'error',
    message: fullMessage,
    action,
  })

  return resolved
}

function buildToastAction(
  resolved: ResolvedApiError,
  opts: ShowApiErrorToastOptions,
): ToastAction | undefined {
  const recovery = resolved.recovery
  if (!recovery) return undefined

  if (recovery.type === 'retry') {
    if (!opts.onRetry) return undefined
    return { label: recovery.label, onAction: opts.onRetry }
  }

  if (recovery.type === 'login') {
    if (!opts.onLogin) return undefined
    return { label: recovery.label, onAction: opts.onLogin }
  }

  if (recovery.type === 'docs' || recovery.type === 'contact') {
    if (!recovery.href) return undefined
    const href = recovery.href
    return {
      label: recovery.label,
      onAction: () => {
        try {
          window.open(href, '_blank', 'noopener,noreferrer')
        } catch {
          // window.open may fail in non-browser environments — drop silently.
        }
      },
    }
  }

  return undefined
}

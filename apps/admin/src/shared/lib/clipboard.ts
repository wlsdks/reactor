import i18n from 'i18next'
import { useToastStore } from '../store/toast.store'

export interface CopyOptions {
  /** Optional label used in success toast: "{label} 복사됨". Default: "내용". */
  label?: string
  /** Override toast type for the success message. Default: `'success'`. */
  toastType?: 'success' | 'info'
  /** Suppress the toast entirely (rare; use when caller emits its own). */
  silent?: boolean
  /**
   * Legacy compat hook fired after a successful copy.
   * Retained so existing call sites that passed `{ onSuccess }` keep working
   * while the new built-in toast supersedes the manual pattern.
   */
  onSuccess?: () => void
}

/** Translate with a hardcoded fallback for environments where i18next is not
 *  initialized yet (test fixtures, very early bootstrap). */
function tr(key: string, fallback: string, vars?: Record<string, string>): string {
  if (!i18n.isInitialized) {
    if (!vars) return fallback
    return Object.entries(vars).reduce(
      (acc, [k, v]) => acc.replaceAll(`{{${k}}}`, v),
      fallback,
    )
  }
  const result = i18n.t(key, vars)
  return typeof result === 'string' && result !== key && result.length > 0
    ? result
    : Object.entries(vars ?? {}).reduce(
        (acc, [k, v]) => acc.replaceAll(`{{${k}}}`, v),
        fallback,
      )
}

async function writeWithFallback(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Legacy execCommand fallback — required for non-secure contexts and
    // browsers that block the async Clipboard API.
    try {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      textarea.style.pointerEvents = 'none'
      document.body.appendChild(textarea)
      textarea.select()
      const ok = document.execCommand('copy')
      document.body.removeChild(textarea)
      return ok === true
    } catch {
      return false
    }
  }
}

/**
 * Copy `text` to the clipboard with a built-in success/failure toast.
 *
 * - Uses `navigator.clipboard.writeText` with a legacy `document.execCommand`
 *   fallback for non-secure contexts.
 * - On success, emits a `{label} 복사됨` toast (default 4s) unless `silent`.
 * - On failure, emits a single localized error toast and returns `false`.
 * - Existing callers that passed only `{ onSuccess }` keep working — the
 *   callback still fires and the new built-in toast eliminates the duplicate
 *   manual `addToast` they used to issue.
 */
export async function copyToClipboard(
  text: string,
  options?: CopyOptions,
): Promise<boolean> {
  const ok = await writeWithFallback(text)
  const silent = options?.silent === true

  if (ok) {
    const label = options?.label ?? tr('common.copy.defaultLabel', '내용')
    if (!silent) {
      useToastStore.getState().addToast({
        type: options?.toastType ?? 'success',
        message: tr('common.copy.success', '{{label}} 복사됨', { label }),
      })
    }
    options?.onSuccess?.()
    return true
  }

  if (!silent) {
    useToastStore.getState().addToast({
      type: 'error',
      message: tr('common.copy.failure', '복사 실패 — 권한을 확인해 주세요'),
    })
  }
  return false
}

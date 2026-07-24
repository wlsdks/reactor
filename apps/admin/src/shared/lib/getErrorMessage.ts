import i18n from 'i18next'
import { ApiError, NetworkError } from '../api/errors'

/**
 * Safely extract an error message from an unknown thrown value.
 * Avoids the unsafe `(e as Error).message` pattern.
 *
 * Prefer {@link resolveApiError} (or {@link showApiErrorToast}) for
 * surface-level UX where you want a translated message + recovery hint.
 */
export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  return 'Unknown error'
}

/**
 * Type-safe check for AbortError, replacing `(e as Error).name !== 'AbortError'`.
 */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

// ─────────────────────────────────────────────────────────────────────────────
// Localized resolution + recovery hints
// ─────────────────────────────────────────────────────────────────────────────

export type RecoveryType = 'retry' | 'contact' | 'docs' | 'login'

export interface ResolvedRecovery {
  /** Recovery class — drives icon + behaviour at the call site. */
  type: RecoveryType
  /** Localized button label. */
  label: string
  /** External link (only meaningful for `docs` / `contact`). */
  href?: string
  /** Optional callback. Caller (e.g. {@link showApiErrorToast}) injects this
   *  for `retry` / `login` so the recovery action wires up to real app state. */
  action?: () => void
}

export interface ResolvedApiError {
  /** Localized, user-friendly message. */
  message: string
  /** Optional 1-line guidance shown alongside the message. */
  hint?: string
  /** Optional recovery affordance (rendered as a Toast action button). */
  recovery?: ResolvedRecovery
  /** Raw detail for logging / debugging. Never rendered. */
  raw?: { status?: number; code?: string }
}

/** Translate with a hardcoded fallback for environments where i18next is not
 *  initialized yet (test fixtures, very early bootstrap). */
function tr(key: string, fallback: string): string {
  if (!i18n.isInitialized) return fallback
  const result = i18n.t(key)
  return typeof result === 'string' && result !== key && result.length > 0
    ? result
    : fallback
}

const KEY = {
  sessionExpired:    'common.errors.sessionExpired',
  forbidden:         'common.errors.forbidden',
  forbiddenHint:     'common.errors.forbiddenHint',
  notFound:          'common.errors.notFound',
  conflict:          'common.errors.conflict',
  tooManyRequests:   'common.errors.tooManyRequests',
  tooManyHint:       'common.errors.tooManyHint',
  serverError:       'common.errors.serverError',
  authUnavailable:   'common.errors.authUnavailable',
  authUnavailableHint: 'common.errors.authUnavailableHint',
  networkError:      'common.errors.networkError',
  unknownError:      'common.errors.unknownError',
  retry:             'common.errors.recovery.retry',
  login:             'common.errors.recovery.login',
  contactAdmin:      'common.errors.recovery.contactAdmin',
  viewDocs:          'common.errors.recovery.viewDocs',
} as const

/**
 * Map an unknown thrown value (typically from a ky/TanStack Query error) to a
 * localized, user-facing payload with optional recovery hint.
 *
 * Status code map:
 *   401 → sessionExpired   + recovery: login
 *   403 → forbidden        + hint forbiddenHint + recovery: contact
 *   404 → notFound         (no recovery — caller already lost the resource)
 *   409 → conflict         + recovery: retry
 *   429 → tooManyRequests  + hint tooManyHint + recovery: retry
 *   5xx → serverError      + recovery: retry
 *   network failure        → networkError + recovery: retry
 *   anything else          → ApiError.message or unknownError fallback
 */
export function resolveApiError(error: unknown): ResolvedApiError {
  // 1) NetworkError thrown by the ky beforeError hook on connect failure.
  if (error instanceof NetworkError) {
    return {
      message: tr(KEY.networkError, '네트워크 연결을 확인해 주세요'),
      recovery: { type: 'retry', label: tr(KEY.retry, '다시 시도') },
      raw: {},
    }
  }

  // 2) ApiError carries the HTTP status.
  if (error instanceof ApiError) {
    const status = error.status
    const code = error.code

    if (status === 401) {
      return {
        message: tr(KEY.sessionExpired, '세션이 만료됐어요'),
        recovery: { type: 'login', label: tr(KEY.login, '다시 로그인') },
        raw: { status, code },
      }
    }
    if (status === 403) {
      return {
        message: tr(KEY.forbidden, '권한이 없어요'),
        hint: tr(KEY.forbiddenHint, '이 작업은 ADMIN 권한이 필요해요'),
        recovery: { type: 'contact', label: tr(KEY.contactAdmin, '관리자 문의') },
        raw: { status, code },
      }
    }
    if (status === 404) {
      return {
        message: tr(KEY.notFound, '리소스를 찾을 수 없어요'),
        raw: { status, code },
      }
    }
    if (status === 409) {
      return {
        message: tr(
          KEY.conflict,
          '충돌이 발생했어요. 다른 사용자가 같은 자원을 변경했을 수 있어요',
        ),
        recovery: { type: 'retry', label: tr(KEY.retry, '다시 시도') },
        raw: { status, code },
      }
    }
    if (status === 429) {
      return {
        message: tr(KEY.tooManyRequests, '요청이 너무 많아요'),
        hint: tr(KEY.tooManyHint, '잠시 후 다시 시도해 주세요'),
        recovery: { type: 'retry', label: tr(KEY.retry, '다시 시도') },
        raw: { status, code },
      }
    }
    if (
      status === 503
      && /JWT authentication is not configured|token revocation persistence is not configured/i.test(
        error.serverMessage ?? '',
      )
    ) {
      return {
        message: tr(KEY.authUnavailable, '관리자 로그인 연결을 확인해 주세요'),
        hint: tr(KEY.authUnavailableHint, '현재 로그인 정보와 서버 인증 설정이 일치하지 않습니다'),
        recovery: { type: 'login', label: tr(KEY.login, '다시 로그인') },
        raw: { status, code },
      }
    }
    if (status >= 500) {
      return {
        message: tr(KEY.serverError, '서버 오류가 발생했어요'),
        recovery: { type: 'retry', label: tr(KEY.retry, '다시 시도') },
        raw: { status, code },
      }
    }

    // Other 4xx — prefer the server-translated message ApiError already
    // assembled, falling back to the generic unknown bucket.
    const fallbackMessage = error.userMessage?.trim()
      ? error.userMessage
      : tr(KEY.unknownError, '알 수 없는 오류가 발생했어요')
    return {
      message: fallbackMessage,
      raw: { status, code },
    }
  }

  // 3) Native fetch / abort / generic Error.
  if (typeof window !== 'undefined' && window.navigator?.onLine === false) {
    return {
      message: tr(KEY.networkError, '네트워크 연결을 확인해 주세요'),
      recovery: { type: 'retry', label: tr(KEY.retry, '다시 시도') },
      raw: {},
    }
  }
  if (error instanceof Error && /failed to fetch|networkerror|econn/i.test(error.message)) {
    return {
      message: tr(KEY.networkError, '네트워크 연결을 확인해 주세요'),
      recovery: { type: 'retry', label: tr(KEY.retry, '다시 시도') },
      raw: {},
    }
  }

  // 4) Last-resort fallback: keep raw message visible if it's a plain Error /
  //    string, otherwise show the generic localized bucket.
  if (error instanceof Error && error.message.trim()) {
    return { message: error.message, raw: {} }
  }
  if (typeof error === 'string' && error.trim()) {
    return { message: error, raw: {} }
  }
  return {
    message: tr(KEY.unknownError, '알 수 없는 오류가 발생했어요'),
    raw: {},
  }
}

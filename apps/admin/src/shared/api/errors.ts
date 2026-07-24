import i18n from 'i18next'

function extractServerMessage(body: unknown): string | undefined {
  if (body && typeof body === 'object') {
    const row = body as Record<string, unknown>
    if (typeof row.error === 'string' && row.error.trim()) return row.error
    if (typeof row.message === 'string' && row.message.trim()) return row.message
    if (typeof row.detail === 'string' && row.detail.trim()) return row.detail
  }
  return undefined
}

function extractDisplayMessage(body: unknown): string | undefined {
  if (body && typeof body === 'object') {
    const row = body as Record<string, unknown>
    if (typeof row.error === 'string' && row.error.trim()) return row.error
    if (typeof row.message === 'string' && row.message.trim()) return row.message
  }
  return undefined
}

function statusToCode(status: number): string {
  if (status === 400) return 'BAD_REQUEST'
  if (status === 403) return 'FORBIDDEN'
  if (status === 404) return 'NOT_FOUND'
  if (status === 409) return 'CONFLICT'
  if (status === 422) return 'VALIDATION'
  if (status === 429) return 'RATE_LIMIT'
  if (status >= 500) return 'SERVER_ERROR'
  return 'UNKNOWN'
}

function codeToI18nKey(code: string): string {
  return code
    .toLowerCase()
    .replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())
}

/** Translate with fallback for when i18next is not yet initialized (e.g. in tests) */
function t(key: string, fallback: string): string {
  const result = i18n.isInitialized ? i18n.t(key) : undefined
  return typeof result === 'string' && result !== key && result.length > 0
    ? result
    : fallback
}

/**
 * Replace raw technical error messages with user-friendly i18n strings.
 * Prevents messages like "socket hang up" or "ECONNREFUSED" from reaching users.
 */
export function sanitizeErrorMessage(message: string): string {
  const lower = message.toLowerCase()
  if (
    lower.includes('socket hang up') ||
    lower.includes('econnrefused') ||
    lower.includes('econnreset')
  ) {
    return t('error.network', '네트워크 연결이 끊어졌어요')
  }
  if (lower.includes('timeout') || lower.includes('etimedout')) {
    return t('error.serverError', '서버 오류가 발생했어요')
  }
  if (lower.includes('failed to fetch') || lower.includes('networkerror')) {
    return t('error.network', '네트워크 연결이 끊어졌어요')
  }
  return message
}

export class ApiError extends Error {
  name = 'ApiError' as const
  readonly status: number
  readonly code: string
  readonly userMessage: string
  readonly serverMessage: string | undefined

  constructor(status: number, code: string, userMessage: string, serverMessage?: string) {
    super(userMessage)
    this.status = status
    this.code = code
    this.userMessage = userMessage
    this.serverMessage = serverMessage
  }

  static fromResponse(status: number, body: unknown): ApiError {
    const serverMessage = extractServerMessage(body)
    const displayMessage = extractDisplayMessage(body)
    const code = statusToCode(status)
    const i18nKey = codeToI18nKey(code)
    const statusFallback = t(`error.${i18nKey}`, `HTTP ${status}`)
    // FastAPI `detail` is retained as structured diagnostic context but never
    // promoted to product copy. Only explicit public `error` / `message`
    // fields can become user-facing text, after technical-text sanitization.
    const userMessage = displayMessage
      ? sanitizeErrorMessage(displayMessage)
      : statusFallback
    return new ApiError(status, code, userMessage, serverMessage)
  }
}

export class NetworkError extends Error {
  name = 'NetworkError' as const

  constructor() {
    super(t('error.network', '네트워크 연결이 끊어졌어요'))
  }
}

/**
 * Converts an HTTP response (or a failed connection) into the same safe error
 * shape used by authenticated and public API callers. Keeping this boundary in
 * one place prevents login, registration, and demo flows from leaking raw
 * proxy/backend text or falling into a vague catch-all state.
 */
export async function normalizeResponseError(response?: Response): Promise<ApiError | NetworkError> {
  if (!response) return new NetworkError()

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // A reverse proxy may return a non-JSON response. The status code still
    // gives the UI a safe, actionable classification without exposing it.
  }
  return ApiError.fromResponse(response.status, body)
}

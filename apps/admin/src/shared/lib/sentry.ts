import * as Sentry from '@sentry/react'

const DSN = import.meta.env.VITE_SENTRY_DSN as string | undefined
const GIT_SHA_RAW = import.meta.env.VITE_GIT_SHA as string | undefined
const GIT_SHA = GIT_SHA_RAW && GIT_SHA_RAW.length > 0 ? GIT_SHA_RAW : 'unknown'
const MODE = import.meta.env.MODE
const IS_PROD = MODE === 'production'

/**
 * Keys whose values must never reach Sentry. Matched case-insensitively against
 * object property names found anywhere in the event payload (extras, contexts,
 * request headers, breadcrumb data, etc.).
 */
const PII_KEY_PATTERN = /(token|password|secret|authorization|api[-_]?key|email|cookie|session)/i

/**
 * Recursively replaces sensitive values with '[redacted]' to prevent PII /
 * credentials leaking into Sentry. Operates on a structural clone so the
 * original event reference held by Sentry's pipeline is mutated safely.
 */
function scrubPii<T>(value: T, depth = 0): T {
  if (depth > 6 || value === null || value === undefined) return value
  if (typeof value !== 'object') return value
  if (Array.isArray(value)) {
    return value.map((item) => scrubPii(item, depth + 1)) as unknown as T
  }
  const source = value as Record<string, unknown>
  const next: Record<string, unknown> = {}
  for (const [key, val] of Object.entries(source)) {
    if (PII_KEY_PATTERN.test(key)) {
      next[key] = '[redacted]'
    } else {
      next[key] = scrubPii(val, depth + 1)
    }
  }
  return next as unknown as T
}

/**
 * Noise filter — errors that are either harmless (browser ResizeObserver
 * benign loop notification) or out of our control (third-party script
 * failures we cannot action).
 */
const IGNORED_ERRORS = [
  'ResizeObserver loop limit exceeded',
  'ResizeObserver loop completed with undelivered notifications',
  'Non-Error promise rejection captured',
  'Network request failed',
]

export function initSentry(): void {
  if (!DSN) return

  Sentry.init({
    dsn: DSN,
    environment: MODE,
    release: GIT_SHA,
    integrations: [Sentry.browserTracingIntegration()],
    // Trace sampling: only sample in production. Dev noise wastes quota.
    tracesSampleRate: IS_PROD ? 0.1 : 0,
    // Disable PII auto-collection at the SDK level as a defence-in-depth
    // measure; beforeSend below is the authoritative scrubber.
    sendDefaultPii: false,
    ignoreErrors: IGNORED_ERRORS,
    beforeSend(event) {
      try {
        return scrubPii(event)
      } catch {
        // If scrubbing throws, drop the event rather than risk leaking PII.
        return null
      }
    },
    beforeBreadcrumb(breadcrumb) {
      try {
        return scrubPii(breadcrumb)
      } catch {
        return null
      }
    },
  })
}

export function captureException(error: unknown, context?: Record<string, unknown>): void {
  if (!DSN) return
  Sentry.withScope((scope) => {
    if (context) {
      scope.setExtras(context)
    }
    Sentry.captureException(error)
  })
}

/**
 * Attach a minimal user identity to the active Sentry scope. Email / name /
 * raw IDs must NOT be passed — only the auth role and an optional opaque
 * user id (already a UUID, not PII). This keeps user context useful for
 * triage (e.g. "all errors are from ADMIN_MANAGER") without violating the
 * "no user-identifying info" rule.
 */
export function setSentryUser(user: { id?: string; role?: string } | null): void {
  if (!DSN) return
  if (!user) {
    Sentry.setUser(null)
    return
  }
  Sentry.setUser({
    id: user.id,
    role: user.role,
  } as { id?: string; role?: string })
}

export function clearSentryUser(): void {
  setSentryUser(null)
}

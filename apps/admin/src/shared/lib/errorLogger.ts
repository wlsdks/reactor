import { ApiError } from '../api/errors'
import { captureException } from './sentry'

interface ErrorLogContext {
  component?: string
  action?: string
  userId?: string
  [key: string]: unknown
}

interface ErrorReport {
  message: string
  name: string
  stack?: string
  status?: number
  context?: ErrorLogContext
  timestamp: number
}

const errorBuffer: ErrorReport[] = []
const MAX_BUFFER = 100

export const errorLogger = {
  /**
   * Capture an error with optional context.
   * Errors are forwarded to Sentry (when configured) and buffered in-memory.
   * In development, errors are also logged to the console.
   *
   * Security: serverMessage is never logged to prevent information leakage.
   */
  capture(error: Error, context?: ErrorLogContext): void {
    const report: ErrorReport = {
      message: error.message,
      name: error.name,
      stack: error.stack,
      status: error instanceof ApiError ? error.status : undefined,
      context,
      timestamp: Date.now(),
    }

    errorBuffer.push(report)
    if (errorBuffer.length > MAX_BUFFER) errorBuffer.shift()

    // Forward to Sentry for persistent external error tracking
    captureException(error, context)

    if (import.meta.env.DEV) {
      console.error('[Reactor]', {
        name: error.name,
        message: error.message,
        status: error instanceof ApiError ? error.status : undefined,
        ...context,
      })
    }
    // Production: errors are handled by error boundaries and toast notifications
    // Server error details (serverMessage) are NOT logged to browser console
  },

  /** Return a copy of recently captured errors (newest last). */
  getRecentErrors(): ErrorReport[] {
    return [...errorBuffer]
  },

  /** Clear the error buffer. */
  clearErrors(): void {
    errorBuffer.length = 0
  },
}

export type { ErrorReport, ErrorLogContext }

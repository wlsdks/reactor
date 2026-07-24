import { ApiError } from '../api/errors'

/**
 * Returns true when `error` is an HTTP 403 from the admin API.
 *
 * Use at the top of a query-error branch to swap the generic load-failure
 * UI for an `EmptyState forbidden` so the user is told the resource is
 * gated by their role rather than missing or broken. For mutation 403s,
 * prefer `showApiErrorToast` (already maps 403 → "관리자 문의" recovery).
 */
export function isForbiddenError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403
}

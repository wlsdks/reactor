/**
 * Persists the *reason* the current session ended so the login page can
 * surface a friendly banner instead of silently bouncing the user.
 *
 * Stored in `sessionStorage` (per-tab, cleared when the tab closes) under the
 * key `reactor-admin-logout-reason`. Cleared after the banner reads it once.
 *
 * Reasons:
 * - `cross-tab`   — token removed in another tab via the `storage` event
 * - `session-expired` — server returned 401 → ky `afterResponse` triggered
 *                        `onUnauthorized`
 */

const KEY = 'reactor-admin-logout-reason'

export type LogoutReason = 'cross-tab' | 'session-expired'

function isLogoutReason(value: string | null): value is LogoutReason {
  return value === 'cross-tab' || value === 'session-expired'
}

export function setLogoutReason(reason: LogoutReason): void {
  try {
    sessionStorage.setItem(KEY, reason)
  } catch {
    // sessionStorage unavailable — banner will just not appear
  }
}

export function readLogoutReason(): LogoutReason | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    return isLogoutReason(raw) ? raw : null
  } catch {
    return null
  }
}

export function clearLogoutReason(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // sessionStorage unavailable
  }
}

/**
 * Read-and-clear in a single call. Convenient for the login page banner
 * which should display the reason exactly once.
 */
export function consumeLogoutReason(): LogoutReason | null {
  const reason = readLogoutReason()
  if (reason) clearLogoutReason()
  return reason
}

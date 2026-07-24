import type { User } from './types'

const AUTH_USER_KEY = 'reactor-admin-user'

export function readStoredUser(): User | null {
  // User data is fetched from /auth/me on app init
  // Not persisted in localStorage to prevent PII exposure via XSS
  return null
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function writeStoredUser(_user: User): void {
  // No-op: user data not persisted in localStorage for security
}

export function clearStoredUser(): void {
  try {
    localStorage.removeItem(AUTH_USER_KEY)
  } catch {
    // localStorage unavailable
  }
}

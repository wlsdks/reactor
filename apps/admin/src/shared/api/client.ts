import ky from 'ky'
import { ApiError, NetworkError, normalizeResponseError } from './errors'

const TOKEN_KEY = 'reactor-admin-token'

export const AUTH_STORAGE_BOUNDARY = Object.freeze({
  mode: 'bearer_local_storage',
  tokenKey: TOKEN_KEY,
  sendsAuthorizationHeader: true,
  requiresBackendCookieCsrfContract: true,
  backendCookieAuthSupported: false,
})

export function getAuthToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setAuthToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // localStorage unavailable
  }
}

export function removeAuthToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    // localStorage unavailable
  }
}

// Callback for 401 auto-logout (set by AuthContext)
let onUnauthorized: (() => void) | null = null

export function setOnUnauthorized(callback: (() => void) | null): void {
  onUnauthorized = callback
}

const API_PREFIX = import.meta.env.VITE_API_URL ?? ''

export function getReactorApiKey(): string | null {
  const value = import.meta.env.VITE_REACTOR_API_KEY
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

/**
 * Authenticated HTTP client (ky).
 *
 * Security notes:
 * - Authentication: JWT Bearer token in Authorization header
 * - CSRF protection: Bearer tokens are immune to CSRF because they cannot be
 *   auto-included in cross-origin requests. Only same-origin JavaScript can
 *   access and send the token via this header.
 * - Token storage boundary: `AUTH_STORAGE_BOUNDARY`; cookie auth requires a
 *   backend-owned httpOnly cookie + CSRF contract before this client can switch.
 * - Auto-logout: 401 responses trigger automatic session invalidation
 *
 * WARNING: Do NOT move authentication to cookies without implementing CSRF tokens.
 */
export const api = ky.create({
  prefixUrl: `${API_PREFIX}/api`,
  hooks: {
    beforeRequest: [
      (request) => {
        const token = getAuthToken()
        if (token) {
          request.headers.set('Authorization', `Bearer ${token}`)
        }
        const apiKey = getReactorApiKey()
        if (apiKey) {
          request.headers.set('X-Reactor-API-Key', apiKey)
        }
      },
    ],
    afterResponse: [
      (_request, _options, response) => {
        if (response.status === 401 && getAuthToken() && onUnauthorized) {
          onUnauthorized()
        }
      },
    ],
    beforeError: [
      async (error) => {
        throw await normalizeResponseError(error.response)
      },
    ],
  },
  retry: {
    limit: 2,
    statusCodes: [429, 502, 503, 504],
    backoffLimit: 10000,
  },
  timeout: 30000,
})

/**
 * Raw fetch wrapper that automatically adds the Authorization header.
 * Used only for SSE streaming endpoints that ky does not support.
 */
export async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getAuthToken()
  const headers = new Headers(options.headers)
  headers.set('Content-Type', headers.get('Content-Type') || 'application/json')
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const apiKey = getReactorApiKey()
  if (apiKey) {
    headers.set('X-Reactor-API-Key', apiKey)
  }

  let response: Response
  try {
    response = await fetch(url, { ...options, headers })
  } catch {
    throw new NetworkError()
  }

  // 401: trigger auto-logout but do NOT throw (auth flow handles redirect)
  if (response.status === 401 && token && onUnauthorized) {
    onUnauthorized()
    return response
  }

  // All other non-OK: normalize to ApiError
  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      // non-JSON error response
    }
    throw ApiError.fromResponse(response.status, body)
  }

  return response
}

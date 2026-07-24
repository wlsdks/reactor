import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

// Node 25+ exposes a broken localStorage global that shadows jsdom's Storage.
// Provide a spec-compliant in-memory Storage so the module and tests agree.
function createStorage(): Storage {
  let store: Record<string, string> = {}
  return {
    getItem(key: string) { return key in store ? store[key] : null },
    setItem(key: string, value: string) { store[key] = String(value) },
    removeItem(key: string) { delete store[key] },
    clear() { store = {} },
    key(index: number) { return Object.keys(store)[index] ?? null },
    get length() { return Object.keys(store).length },
  }
}

Object.defineProperty(globalThis, 'localStorage', {
  value: createStorage(),
  writable: true,
  configurable: true,
})

import {
  AUTH_STORAGE_BOUNDARY,
  getAuthToken,
  getReactorApiKey,
  setAuthToken,
  removeAuthToken,
  fetchWithAuth,
  setOnUnauthorized,
} from '../client'
import { ApiError, NetworkError } from '../errors'

const TOKEN_KEY = 'reactor-admin-token'

describe('auth token management', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('documents the current release auth storage boundary', () => {
    expect(AUTH_STORAGE_BOUNDARY).toEqual({
      mode: 'bearer_local_storage',
      tokenKey: TOKEN_KEY,
      sendsAuthorizationHeader: true,
      requiresBackendCookieCsrfContract: true,
      backendCookieAuthSupported: false,
    })
  })

  it('getAuthToken returns null when no token stored', () => {
    expect(getAuthToken()).toBeNull()
  })

  it('setAuthToken stores token in localStorage', () => {
    setAuthToken('my-token')
    expect(localStorage.getItem(TOKEN_KEY)).toBe('my-token')
  })

  it('getAuthToken retrieves stored token', () => {
    localStorage.setItem(TOKEN_KEY, 'test-token')
    expect(getAuthToken()).toBe('test-token')
  })

  it('removeAuthToken removes token from localStorage', () => {
    localStorage.setItem(TOKEN_KEY, 'test-token')
    removeAuthToken()
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
  })
})

describe('fetchWithAuth', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllEnvs()
  })

  it('sends request without Authorization header when no token', async () => {
    const spy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    )

    await fetchWithAuth('/api/test')

    const [, options] = spy.mock.calls[0]
    const headers = options?.headers as Headers
    expect(headers.get('Authorization')).toBeNull()
    spy.mockRestore()
  })

  it('sends Authorization Bearer header when token exists', async () => {
    setAuthToken('jwt-token-123')
    const spy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    )

    await fetchWithAuth('/api/test')

    const [, options] = spy.mock.calls[0]
    const headers = options?.headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer jwt-token-123')
    spy.mockRestore()
  })

  it('sends X-Reactor-API-Key header when configured', async () => {
    vi.stubEnv('VITE_REACTOR_API_KEY', 'reactor-local-key')
    const spy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    )

    await fetchWithAuth('/api/test')

    const [, options] = spy.mock.calls[0]
    const headers = options?.headers as Headers
    expect(getReactorApiKey()).toBe('reactor-local-key')
    expect(headers.get('X-Reactor-API-Key')).toBe('reactor-local-key')
    spy.mockRestore()
  })

  it('sets Content-Type to application/json by default', async () => {
    const spy = vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response('{}', { status: 200 }),
    )

    await fetchWithAuth('/api/test')

    const [, options] = spy.mock.calls[0]
    const headers = options?.headers as Headers
    expect(headers.get('Content-Type')).toBe('application/json')
    spy.mockRestore()
  })

  it('calls onUnauthorized callback on 401 when token exists', async () => {
    setAuthToken('expired-token')
    const onUnauthorized = vi.fn()
    setOnUnauthorized(onUnauthorized)

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response('Unauthorized', { status: 401 }),
    )

    await fetchWithAuth('/api/protected')
    expect(onUnauthorized).toHaveBeenCalledOnce()

    setOnUnauthorized(null)
  })

  it('does not call onUnauthorized on 401 when no token and throws ApiError', async () => {
    const onUnauthorized = vi.fn()
    setOnUnauthorized(onUnauthorized)

    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response('Unauthorized', { status: 401 }),
    )

    await expect(fetchWithAuth('/api/protected')).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).not.toHaveBeenCalled()

    setOnUnauthorized(null)
  })
})

describe('fetchWithAuth error handling', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    setOnUnauthorized(null)
    localStorage.clear()
    vi.unstubAllEnvs()
  })

  it('throws NetworkError when fetch fails', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(fetchWithAuth('/api/test')).rejects.toBeInstanceOf(NetworkError)
  })

  it('throws ApiError for 400 response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'Bad input' }), { status: 400 })
    )
    await expect(fetchWithAuth('/api/test')).rejects.toSatisfy((err: ApiError) => {
      return err instanceof ApiError && err.status === 400 && err.code === 'BAD_REQUEST' && err.serverMessage === 'Bad input'
    })
  })

  it('throws ApiError for 404 response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(null, { status: 404 })
    )
    await expect(fetchWithAuth('/api/test')).rejects.toSatisfy((err: ApiError) => {
      return err instanceof ApiError && err.status === 404 && err.code === 'NOT_FOUND'
    })
  })

  it('throws ApiError for 500 response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Internal error' }), { status: 500 })
    )
    await expect(fetchWithAuth('/api/test')).rejects.toSatisfy((err: ApiError) => {
      return err instanceof ApiError && err.status === 500 && err.code === 'SERVER_ERROR'
    })
  })

  it('calls onUnauthorized on 401 but does NOT throw ApiError', async () => {
    const unauthorizedCb = vi.fn()
    setOnUnauthorized(unauthorizedCb)
    setAuthToken('test-token')

    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(null, { status: 401 })
    )

    const res = await fetchWithAuth('/api/test')
    expect(unauthorizedCb).toHaveBeenCalled()
    expect(res.status).toBe(401)
  })

  it('returns Response for successful requests', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )
    const res = await fetchWithAuth('/api/test')
    expect(res.status).toBe(200)
  })

  it('throws ApiError for non-JSON error body (falls back gracefully)', async () => {
    // Response.json() will throw for non-JSON, body should be null
    const response = new Response('plain text error', { status: 422 })
    // Override json to throw
    vi.spyOn(response, 'json').mockRejectedValue(new SyntaxError('Unexpected token'))
    globalThis.fetch = vi.fn().mockResolvedValue(response)

    await expect(fetchWithAuth('/api/test')).rejects.toSatisfy((err: ApiError) => {
      return err instanceof ApiError && err.status === 422 && err.serverMessage === undefined
    })
  })

  it('does not call onUnauthorized on 401 when token exists but no callback set', async () => {
    setAuthToken('some-token')
    setOnUnauthorized(null)

    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response('Unauthorized', { status: 401 })
    )

    // Without onUnauthorized callback, 401 falls through to non-OK error handling
    await expect(fetchWithAuth('/api/test')).rejects.toBeInstanceOf(ApiError)
  })

  it('preserves custom Content-Type header', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response('', { status: 200 })
    )

    await fetchWithAuth('/api/test', {
      headers: { 'Content-Type': 'multipart/form-data' },
    })

    const [, options] = vi.mocked(globalThis.fetch).mock.calls[0]
    const headers = options?.headers as Headers
    expect(headers.get('Content-Type')).toBe('multipart/form-data')
  })

  it('throws ApiError for 403 Forbidden response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'Forbidden' }), { status: 403 })
    )
    await expect(fetchWithAuth('/api/test')).rejects.toSatisfy((err: ApiError) => {
      return err instanceof ApiError && err.status === 403 && err.code === 'FORBIDDEN'
    })
  })

  it('throws ApiError for 429 Rate Limit response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'Too many requests' }), { status: 429 })
    )
    await expect(fetchWithAuth('/api/test')).rejects.toSatisfy((err: ApiError) => {
      return err instanceof ApiError && err.status === 429 && err.code === 'RATE_LIMIT'
    })
  })
})

describe('fetchWithAuth additional branch coverage', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    setOnUnauthorized(null)
    localStorage.clear()
  })

  it('returns 401 response when token exists but no onUnauthorized callback', async () => {
    // This scenario: token exists + no callback → 401 is NOT a special-case,
    // falls through to generic non-OK handling
    setAuthToken('valid-token')
    setOnUnauthorized(null)

    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(null, { status: 401 }),
    )

    await expect(fetchWithAuth('/api/test')).rejects.toBeInstanceOf(ApiError)
  })

  it('passes additional RequestInit options to fetch', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response('{}', { status: 200 }),
    )
    globalThis.fetch = fetchSpy

    await fetchWithAuth('/api/test', {
      method: 'POST',
      body: JSON.stringify({ key: 'value' }),
    })

    const [, options] = fetchSpy.mock.calls[0]
    expect(options?.method).toBe('POST')
    expect(options?.body).toBe(JSON.stringify({ key: 'value' }))
  })

  it('on 401 with token and callback, returns the response (does not throw)', async () => {
    setAuthToken('my-token')
    const cb = vi.fn()
    setOnUnauthorized(cb)

    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response('', { status: 401 }),
    )

    const res = await fetchWithAuth('/api/test')
    expect(res.status).toBe(401)
    expect(cb).toHaveBeenCalledOnce()
  })

  it('extracts message field from JSON error body', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Validation failed' }), { status: 422 }),
    )

    await expect(fetchWithAuth('/api/test')).rejects.toSatisfy((err: ApiError) => {
      return err instanceof ApiError && err.serverMessage === 'Validation failed'
    })
  })

  it('handles 409 Conflict response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'Already exists' }), { status: 409 }),
    )

    await expect(fetchWithAuth('/api/test')).rejects.toSatisfy((err: ApiError) => {
      return err instanceof ApiError && err.status === 409 && err.code === 'CONFLICT'
    })
  })
})

describe('localStorage error handling', () => {
  it('getAuthToken returns null when localStorage.getItem throws', () => {
    const original = localStorage.getItem.bind(localStorage)
    Object.defineProperty(localStorage, 'getItem', {
      value: () => { throw new Error('SecurityError') },
      configurable: true,
    })

    expect(getAuthToken()).toBeNull()

    Object.defineProperty(localStorage, 'getItem', {
      value: original,
      configurable: true,
    })
  })

  it('setAuthToken does not throw when localStorage.setItem throws', () => {
    const original = localStorage.setItem.bind(localStorage)
    Object.defineProperty(localStorage, 'setItem', {
      value: () => { throw new Error('QuotaExceededError') },
      configurable: true,
    })

    expect(() => setAuthToken('test')).not.toThrow()

    Object.defineProperty(localStorage, 'setItem', {
      value: original,
      configurable: true,
    })
  })

  it('removeAuthToken does not throw when localStorage.removeItem throws', () => {
    const original = localStorage.removeItem.bind(localStorage)
    Object.defineProperty(localStorage, 'removeItem', {
      value: () => { throw new Error('SecurityError') },
      configurable: true,
    })

    expect(() => removeAuthToken()).not.toThrow()

    Object.defineProperty(localStorage, 'removeItem', {
      value: original,
      configurable: true,
    })
  })
})

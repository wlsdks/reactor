import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock @sentry/react before importing the module under test
const mockInit = vi.fn()
const mockCaptureException = vi.fn()
const mockSetExtras = vi.fn()
const mockSetUser = vi.fn()
const mockWithScope = vi.fn((callback: (scope: { setExtras: typeof mockSetExtras }) => void) => {
  callback({ setExtras: mockSetExtras })
})
const mockBrowserTracingIntegration = vi.fn(() => ({ name: 'BrowserTracing' }))

vi.mock('@sentry/react', () => ({
  init: mockInit,
  captureException: mockCaptureException,
  withScope: mockWithScope,
  setUser: mockSetUser,
  browserTracingIntegration: mockBrowserTracingIntegration,
}))

describe('sentry', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
  })

  describe('initSentry', () => {
    it('does not call Sentry.init when VITE_SENTRY_DSN is not set', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', '')
      const { initSentry } = await import('../sentry')
      initSentry()
      expect(mockInit).not.toHaveBeenCalled()
    })

    it('calls Sentry.init with hardened config when DSN is set', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      const { initSentry } = await import('../sentry')
      initSentry()
      expect(mockInit).toHaveBeenCalledTimes(1)
      const config = mockInit.mock.calls[0][0]
      expect(config.dsn).toBe('https://examplePublicKey@o0.ingest.sentry.io/0')
      expect(config.environment).toBeDefined()
      expect(config.release).toBeDefined()
      expect(config.sendDefaultPii).toBe(false)
      expect(config.ignoreErrors).toEqual(expect.arrayContaining(['ResizeObserver loop limit exceeded']))
      expect(typeof config.beforeSend).toBe('function')
      expect(typeof config.beforeBreadcrumb).toBe('function')
      // Test mode is not 'production', so traces should be sampled at 0.
      expect(config.tracesSampleRate).toBe(0)
    })

    it('falls back to release "unknown" when VITE_GIT_SHA is unset', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      vi.stubEnv('VITE_GIT_SHA', '')
      const { initSentry } = await import('../sentry')
      initSentry()
      const config = mockInit.mock.calls[0][0]
      expect(config.release).toBe('unknown')
    })

    it('uses VITE_GIT_SHA as release when provided', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      vi.stubEnv('VITE_GIT_SHA', 'abc1234')
      const { initSentry } = await import('../sentry')
      initSentry()
      const config = mockInit.mock.calls[0][0]
      expect(config.release).toBe('abc1234')
    })
  })

  describe('beforeSend PII scrubbing', () => {
    it('redacts sensitive top-level keys', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      const { initSentry } = await import('../sentry')
      initSentry()
      const config = mockInit.mock.calls[0][0]
      const event = {
        extra: {
          token: 'secret-token-value',
          password: 'hunter2',
          email: 'admin@example.com',
          authorization: 'Bearer xyz',
          username: 'safeuser',
        },
      }
      const result = config.beforeSend(event)
      expect(result.extra.token).toBe('[redacted]')
      expect(result.extra.password).toBe('[redacted]')
      expect(result.extra.email).toBe('[redacted]')
      expect(result.extra.authorization).toBe('[redacted]')
      expect(result.extra.username).toBe('safeuser')
    })

    it('redacts nested PII fields recursively', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      const { initSentry } = await import('../sentry')
      initSentry()
      const config = mockInit.mock.calls[0][0]
      const event = {
        request: {
          headers: {
            Authorization: 'Bearer xyz',
            'X-Api-Key': 'k',
            'Content-Type': 'application/json',
          },
        },
        contexts: {
          state: {
            user: { email: 'user@example.com', id: 'u1' },
          },
        },
      }
      const result = config.beforeSend(event)
      expect(result.request.headers.Authorization).toBe('[redacted]')
      expect(result.request.headers['X-Api-Key']).toBe('[redacted]')
      expect(result.request.headers['Content-Type']).toBe('application/json')
      expect(result.contexts.state.user.email).toBe('[redacted]')
      expect(result.contexts.state.user.id).toBe('u1')
    })

    it('returns null if scrubbing throws', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      const { initSentry } = await import('../sentry')
      initSentry()
      const config = mockInit.mock.calls[0][0]
      // A circular structure can break naive recursion, but our scrubber stops at depth 6.
      // Force a throw by passing an exotic getter.
      const evil = {}
      Object.defineProperty(evil, 'token', {
        enumerable: true,
        get() {
          throw new Error('boom')
        },
      })
      const result = config.beforeSend({ extra: evil })
      expect(result).toBeNull()
    })

    it('beforeBreadcrumb redacts sensitive crumb data', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      const { initSentry } = await import('../sentry')
      initSentry()
      const config = mockInit.mock.calls[0][0]
      const crumb = { category: 'fetch', data: { token: 'abc', url: '/api/x' } }
      const result = config.beforeBreadcrumb(crumb)
      expect(result.data.token).toBe('[redacted]')
      expect(result.data.url).toBe('/api/x')
    })
  })

  describe('captureException', () => {
    it('does not call Sentry when DSN is not set', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', '')
      const { captureException } = await import('../sentry')
      captureException(new Error('test'))
      expect(mockWithScope).not.toHaveBeenCalled()
    })

    it('forwards error to Sentry when DSN is set', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      const { captureException } = await import('../sentry')
      const error = new Error('test error')
      captureException(error)
      expect(mockWithScope).toHaveBeenCalled()
      expect(mockCaptureException).toHaveBeenCalledWith(error)
    })

    it('sets extras when context is provided', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      const { captureException } = await import('../sentry')
      const context = { component: 'TestComponent', action: 'click' }
      captureException(new Error('test'), context)
      expect(mockSetExtras).toHaveBeenCalledWith(context)
    })
  })

  describe('setSentryUser / clearSentryUser', () => {
    it('no-ops when DSN is not set', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', '')
      const { setSentryUser, clearSentryUser } = await import('../sentry')
      setSentryUser({ id: 'u1', role: 'ADMIN' })
      clearSentryUser()
      expect(mockSetUser).not.toHaveBeenCalled()
    })

    it('passes only id + role to Sentry.setUser (no email/name)', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      const { setSentryUser } = await import('../sentry')
      setSentryUser({ id: 'u-123', role: 'ADMIN_MANAGER' })
      expect(mockSetUser).toHaveBeenCalledWith({ id: 'u-123', role: 'ADMIN_MANAGER' })
    })

    it('clearSentryUser passes null to Sentry.setUser', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      const { clearSentryUser } = await import('../sentry')
      clearSentryUser()
      expect(mockSetUser).toHaveBeenCalledWith(null)
    })

    it('setSentryUser(null) passes null to Sentry.setUser', async () => {
      vi.stubEnv('VITE_SENTRY_DSN', 'https://examplePublicKey@o0.ingest.sentry.io/0')
      const { setSentryUser } = await import('../sentry')
      setSentryUser(null)
      expect(mockSetUser).toHaveBeenCalledWith(null)
    })
  })
})

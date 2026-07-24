import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  sendSlackCommand,
  sendSlackEvent,
  sendErrorReport,
  probeEndpoint,
  runSlackLiveSmoke,
  runA2aLiveSmoke,
} from '../api'
import { api } from '../../../shared/api/client'

// We mock the shared ky `api` instance so we can assert which path / options
// each integration helper calls without going through real HTTP. The instance
// is callable as a function (for arbitrary methods) and exposes `get`/`post`
// shortcuts.
vi.mock('../../../shared/api/client', () => {
  const callable = vi.fn()
  Object.assign(callable, {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  })
  return {
    api: callable,
    getAuthToken: vi.fn(() => null),
    setAuthToken: vi.fn(),
    removeAuthToken: vi.fn(),
    setOnUnauthorized: vi.fn(),
  }
})

const apiMock = api as unknown as ReturnType<typeof vi.fn> & {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

function makeMockResponse(status: number, body: unknown, contentType = 'application/json') {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get: (header: string) => (header.toLowerCase() === 'content-type' ? contentType : null),
    },
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(typeof body === 'string' ? body : JSON.stringify(body)),
  }
}

describe('integrations api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('confirms external side effects only through fixed smoke operation payloads', async () => {
    const json = vi.fn().mockResolvedValue({ ok: true, status: 'passed' })
    apiMock.post.mockReturnValue({ json })

    await expect(runSlackLiveSmoke()).resolves.toMatchObject({ ok: true })
    await expect(runA2aLiveSmoke()).resolves.toMatchObject({ ok: true })

    expect(apiMock.post).toHaveBeenNthCalledWith(1, 'admin/slack/smoke', {
      json: { confirmExternalSideEffects: true },
    })
    expect(apiMock.post).toHaveBeenNthCalledWith(2, 'admin/a2a/smoke', {
      json: { confirmExternalSideEffects: true },
    })
  })

  describe('sendSlackCommand', () => {
    it('POSTs to slack/commands and returns parsed result', async () => {
      apiMock.post.mockResolvedValue(makeMockResponse(200, { ok: true }))

      const result = await sendSlackCommand({
        command: '/reactor',
        text: 'help',
        channelId: 'C123',
        responseUrl: 'https://hooks.slack.com/respond',
      })

      expect(apiMock.post).toHaveBeenCalledWith(
        'slack/commands',
        expect.objectContaining({
          throwHttpErrors: false,
          headers: expect.objectContaining({
            'Content-Type': 'application/x-www-form-urlencoded',
          }),
        }),
      )
      const opts = apiMock.post.mock.calls[0][1]
      expect(opts.body).toContain('command=%2Freactor')
      expect(opts.body).toContain('text=help')
      expect(result).toEqual({ status: 200, body: { ok: true } })
    })

    it('includes optional userName in form params', async () => {
      apiMock.post.mockResolvedValue(makeMockResponse(200, {}))

      await sendSlackCommand({
        command: '/reactor',
        text: 'ping',
        channelId: 'C456',
        responseUrl: 'https://hooks.slack.com/respond',
        userName: 'alice',
      })

      const opts = apiMock.post.mock.calls[0][1]
      expect(opts.body).toContain('user_name=alice')
    })

    it('preserves non-2xx status without throwing (tester UI surfaces errors)', async () => {
      apiMock.post.mockResolvedValue(makeMockResponse(500, { error: 'boom' }))

      const result = await sendSlackCommand({
        command: '/reactor',
        text: 'x',
        channelId: 'C',
        responseUrl: 'https://hooks.slack.com/respond',
      })

      expect(result).toEqual({ status: 500, body: { error: 'boom' } })
    })
  })

  describe('sendSlackEvent', () => {
    it('POSTs JSON to slack/events and returns parsed result', async () => {
      apiMock.post.mockResolvedValue(makeMockResponse(200, { challenge: 'abc' }))

      const result = await sendSlackEvent({
        payload: { type: 'url_verification', challenge: 'abc' },
      })

      expect(apiMock.post).toHaveBeenCalledWith(
        'slack/events',
        expect.objectContaining({
          json: { type: 'url_verification', challenge: 'abc' },
          throwHttpErrors: false,
        }),
      )
      expect(result).toEqual({ status: 200, body: { challenge: 'abc' } })
    })

    it('includes Slack retry headers when provided', async () => {
      apiMock.post.mockResolvedValue(makeMockResponse(200, {}))

      await sendSlackEvent({
        payload: { type: 'message' },
        retryNum: '1',
        retryReason: 'timeout',
      })

      const opts = apiMock.post.mock.calls[0][1]
      expect(opts.headers).toMatchObject({
        'X-Slack-Retry-Num': '1',
        'X-Slack-Retry-Reason': 'timeout',
      })
    })
  })

  describe('sendErrorReport', () => {
    it('POSTs to error-report endpoint and returns parsed result', async () => {
      apiMock.post.mockResolvedValue(makeMockResponse(200, { reported: true }))

      const result = await sendErrorReport({
        stackTrace: 'Error at line 1',
        serviceName: 'payments',
        repoSlug: 'payments-service',
        slackChannel: '#alerts',
      })

      expect(apiMock.post).toHaveBeenCalledWith(
        'error-report',
        expect.objectContaining({
          throwHttpErrors: false,
          json: expect.objectContaining({
            stackTrace: 'Error at line 1',
            serviceName: 'payments',
            repoSlug: 'payments-service',
            slackChannel: '#alerts',
          }),
        }),
      )
      expect(result).toEqual({ status: 200, body: { reported: true } })
    })

    it('sets X-API-Key header when apiKey is provided', async () => {
      apiMock.post.mockResolvedValue(makeMockResponse(200, {}))

      await sendErrorReport({
        stackTrace: 'err',
        serviceName: 'svc',
        repoSlug: 'repo',
        slackChannel: '#ch',
        apiKey: 'test-key-123',
      })

      const opts = apiMock.post.mock.calls[0][1]
      expect(opts.headers).toMatchObject({ 'X-API-Key': 'test-key-123' })
    })

    it('omits X-API-Key header when apiKey is absent', async () => {
      apiMock.post.mockResolvedValue(makeMockResponse(200, {}))

      await sendErrorReport({
        stackTrace: 'err',
        serviceName: 'svc',
        repoSlug: 'repo',
        slackChannel: '#ch',
      })

      const opts = apiMock.post.mock.calls[0][1]
      expect(opts.headers).not.toHaveProperty('X-API-Key')
    })
  })

  describe('probeEndpoint', () => {
    it('strips /api/ prefix and calls ky api with the relative path', async () => {
      apiMock.mockResolvedValue(makeMockResponse(200, { status: 'ok' }))

      const result = await probeEndpoint({ path: '/api/health', method: 'GET' })

      expect(apiMock).toHaveBeenCalledWith(
        'health',
        expect.objectContaining({ method: 'GET', throwHttpErrors: false }),
      )
      expect(result.status).toBe(200)
      expect(result.body).toEqual({ status: 'ok' })
      expect(typeof result.durationMs).toBe('number')
    })

    it('preserves nested paths and query strings when stripping /api/', async () => {
      apiMock.mockResolvedValue(makeMockResponse(200, []))

      await probeEndpoint({ path: '/api/admin/audits?limit=5' })

      expect(apiMock).toHaveBeenCalledWith(
        'admin/audits?limit=5',
        expect.objectContaining({ method: 'GET' }),
      )
    })

    it('returns null status with error message when the request rejects', async () => {
      apiMock.mockRejectedValue(new Error('Connection refused'))

      const result = await probeEndpoint({ path: '/api/unreachable' })

      expect(result.status).toBeNull()
      expect(result.body).toBeNull()
      expect(result.error).toBe('Connection refused')
    })

    it('preserves non-2xx HTTP status without throwing (probes report failure status)', async () => {
      apiMock.mockResolvedValue(makeMockResponse(404, { error: 'not found' }))

      const result = await probeEndpoint({ path: '/api/missing' })

      expect(result.status).toBe(404)
      expect(result.body).toEqual({ error: 'not found' })
      expect(result.error).toBeUndefined()
    })
  })
})

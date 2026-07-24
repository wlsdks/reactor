import { api } from '../../shared/api/client'
import { getErrorMessage } from '../../shared/lib/getErrorMessage'
import type {
  EndpointProbeRequest,
  EndpointProbeResult,
  ErrorReportRequest,
  HttpCallResult,
  SlackCommandRequest,
  SlackEventRequest,
  SlackLiveSmokeResult,
  A2aLiveSmokeResult,
} from './types'

/**
 * These integrations endpoints are administrator-facing testers / probes whose
 * UI surfaces the raw HTTP `status` and parsed `body` (including 4xx/5xx) so
 * operators can diagnose Slack / error-report wiring without a separate tool.
 *
 * For that reason every call uses ky with `throwHttpErrors: false` — error
 * responses are returned to the caller as `HttpCallResult` instead of being
 * thrown as `ApiError`. The shared ky `afterResponse` hook still fires on 401,
 * so auto-logout behaviour is preserved; only the throw-on-non-2xx step is
 * suppressed.
 */

async function parseBody(res: Response): Promise<unknown> {
  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    try {
      return await res.json()
    } catch {
      return null
    }
  }
  return res.text()
}

/**
 * Strip the `/api/` prefix that callers attach to absolute admin paths so the
 * value is compatible with the shared ky instance, which already configures
 * `prefixUrl` ending in `/api` and rejects inputs that begin with `/`.
 */
function toRelativeApiPath(path: string): string {
  if (path.startsWith('/api/')) return path.slice('/api/'.length)
  if (path.startsWith('api/')) return path.slice('api/'.length)
  // Defensive: ky rejects leading slashes when prefixUrl is set; strip if
  // present so we never throw on an unexpected path shape.
  return path.replace(/^\/+/, '')
}

export async function sendSlackCommand(request: SlackCommandRequest): Promise<HttpCallResult> {
  const params = new URLSearchParams({
    command: request.command,
    text: request.text,
    user_id: 'admin-integration',
    channel_id: request.channelId,
    response_url: request.responseUrl,
  })
  if (request.userName) params.set('user_name', request.userName)
  if (request.channelName) params.set('channel_name', request.channelName)
  if (request.triggerId) params.set('trigger_id', request.triggerId)

  const res = await api.post('slack/commands', {
    body: params.toString(),
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    throwHttpErrors: false,
  })

  return {
    status: res.status,
    body: await parseBody(res),
  }
}

export async function sendSlackEvent(request: SlackEventRequest): Promise<HttpCallResult> {
  const headers: Record<string, string> = {}
  if (request.retryNum) headers['X-Slack-Retry-Num'] = request.retryNum
  if (request.retryReason) headers['X-Slack-Retry-Reason'] = request.retryReason

  const res = await api.post('slack/events', {
    json: request.payload,
    headers,
    throwHttpErrors: false,
  })

  return {
    status: res.status,
    body: await parseBody(res),
  }
}

export async function sendErrorReport(request: ErrorReportRequest): Promise<HttpCallResult> {
  const headers: Record<string, string> = {}
  if (request.apiKey) headers['X-API-Key'] = request.apiKey

  const res = await api.post('error-report', {
    json: {
      stackTrace: request.stackTrace,
      serviceName: request.serviceName,
      repoSlug: request.repoSlug,
      slackChannel: request.slackChannel,
      environment: request.environment || undefined,
      timestamp: request.timestamp || undefined,
      metadata: request.metadata || undefined,
    },
    headers,
    throwHttpErrors: false,
  })

  return {
    status: res.status,
    body: await parseBody(res),
  }
}

export async function probeEndpoint(request: EndpointProbeRequest): Promise<EndpointProbeResult> {
  const startedAt = performance.now()
  const relativePath = toRelativeApiPath(request.path)

  try {
    const res = await api(relativePath, {
      method: request.method || 'GET',
      throwHttpErrors: false,
    })

    return {
      status: res.status,
      body: await parseBody(res),
      durationMs: Math.round(performance.now() - startedAt),
    }
  } catch (e) {
    return {
      status: null,
      body: null,
      durationMs: Math.round(performance.now() - startedAt),
      error: getErrorMessage(e),
    }
  }
}

export const runSlackLiveSmoke = (): Promise<SlackLiveSmokeResult> =>
  api.post('admin/slack/smoke', {
    json: { confirmExternalSideEffects: true },
  }).json()

export const runA2aLiveSmoke = (): Promise<A2aLiveSmokeResult> =>
  api.post('admin/a2a/smoke', {
    json: { confirmExternalSideEffects: true },
  }).json()

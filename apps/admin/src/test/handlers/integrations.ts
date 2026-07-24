import { http, HttpResponse } from 'msw'
import { NOW } from './shared'

export const mockProactiveChannels = [
  { channelId: 'C0123DAILY', channelName: '#daily-updates', addedAt: NOW - 14 * 86_400_000 },
  { channelId: 'C0456OPS', channelName: '#ops-alerts', addedAt: NOW - 10 * 86_400_000 },
  { channelId: 'C0789ENG', channelName: '#engineering', addedAt: NOW - 5 * 86_400_000 },
]

export const integrationsHandlers = [
  // Chat Inspector
  http.post('/api/chat', async ({ request }) => {
    const body = await request.json() as { message: string; graphProfile?: string }
    if (body.graphProfile === 'research') {
      return HttpResponse.json({
        content: 'Jira 연동 정책은 관리자 승인을 거쳐야 합니다 [policy_jira:0].',
        success: true,
        grounded: true,
        verifiedSourceCount: 1,
        model: 'ollama:gemma4:12b',
        durationMs: 840,
        tokenUsage: { inputTokens: 42, outputTokens: 31, totalTokens: 73 },
        metadata: {
          runId: 'run-rag-grounded-1',
          research_plan: {
            status: 'complete',
            profile: 'research',
            evidenceStatus: 'grounded',
            citationCount: 1,
            citationIds: ['policy_jira:0'],
            sourceCount: 1,
            sourceLabels: ['policy://jira-integration'],
            answerContract: {
              status: 'grounded',
              citationIds: ['policy_jira:0'],
              sourceLabels: ['policy://jira-integration'],
              citationStyle: 'manifest_ids',
              uncitedClaimsAllowed: false,
            },
          },
        },
      })
    }
    return HttpResponse.json({
      response: `모의 응답: "${body.message}". 프로덕션에서는 설정된 페르소나와 도구를 사용하여 AI 엔진이 처리합니다.`,
      sessionId: 'mock-session-chat',
      runId: 'mock-run-1',
      toolCalls: [],
      model: 'claude-sonnet-4-20250514',
      durationMs: 1500,
      inputTokens: 150,
      outputTokens: 85,
    })
  }),

  // Integrations — POST handlers
  http.post('/api/slack/commands', () => {
    return HttpResponse.json({ status: 200, body: { text: 'Command received' } })
  }),

  http.post('/api/slack/events', () => {
    return HttpResponse.json({ status: 200, body: { ok: true } })
  }),

  http.post('/api/error-report', () => {
    return HttpResponse.json({ status: 200, body: { reported: true } })
  }),

  http.options('/api/approvals', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.options('/api/slack/commands', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.options('/api/slack/events', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.options('/api/error-report', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/v1/a2a/diagnostics', () => {
    return HttpResponse.json({ status: 'ready', protocolVersion: '1.0' })
  }),

  http.post('/api/admin/slack/smoke', () => {
    return HttpResponse.json({
      ok: true,
      status: 'passed',
      scope: 'live',
      liveTarget: {
        workspaceId: 'T0REACTOR',
        channelId: 'C0123456789',
        channelName: 'jarvis',
        botUserId: 'U0JARVIS',
      },
      evidence: {
        slackGatewaySmoke: {
          status: 'verified',
          gateway: 'native_slack_gateway',
        },
      },
      checks: {
        auth_test: { status: 'passed' },
        channel_info: { status: 'passed' },
        thread_message: { status: 'passed' },
        socket_mode: { status: 'passed' },
      },
    })
  }),

  http.post('/api/admin/a2a/smoke', () => {
    return HttpResponse.json({
      ok: true,
      status: 'passed',
      scope: 'live',
      base_url: 'https://reactor.example',
      evidence: {
        a2aProtocol: {
          status: 'verified',
          agentCard: { name: 'Reactor', interfaceCount: 1 },
          taskApi: { status: 'passed', taskStatus: 'completed', path: '/v1/a2a/tasks' },
          secretFree: true,
          tlsRequired: true,
        },
      },
      checks: {
        agent_card: { status: 'passed' },
        diagnostics: { status: 'passed' },
        task_api: { status: 'passed', task_id: 'task_release_smoke_123' },
      },
    })
  }),

  // Integrations — GET probes (control plane probes hit these with GET, return 405 to signal "route exists")
  http.get('/api/slack/commands', () => {
    return new HttpResponse(null, { status: 405 })
  }),

  http.get('/api/slack/events', () => {
    return new HttpResponse(null, { status: 405 })
  }),

  http.get('/api/error-report', () => {
    return new HttpResponse(null, { status: 405 })
  }),

  // Proactive Channels
  http.get('/api/proactive-channels', () => {
    return HttpResponse.json(mockProactiveChannels)
  }),

  http.post('/api/proactive-channels', async ({ request }) => {
    const body = await request.json() as { channelId: string; channelName?: string }
    return HttpResponse.json({ channelId: body.channelId, channelName: body.channelName ?? null, addedAt: NOW })
  }),

  http.delete('/api/proactive-channels/:channelId', () => {
    return new HttpResponse(null, { status: 204 })
  }),
]

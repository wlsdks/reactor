import { http, HttpResponse } from 'msw'
import { NOW, HOUR, DAY } from './shared'

export const mockSessions = [
  {
    sessionId: 'session-1',
    messageCount: 12,
    lastActivity: NOW - 2 * HOUR,
    preview: 'How do I set up the Jira integration for our team workspace?',
  },
  {
    sessionId: 'session-2',
    messageCount: 5,
    lastActivity: NOW - 8 * HOUR,
    preview: 'Please summarize the Q1 sales report from Confluence.',
  },
  {
    sessionId: 'session-3',
    messageCount: 28,
    lastActivity: NOW - DAY,
    preview: 'Can you help me debug the API timeout errors in production?',
  },
  {
    sessionId: 'session-4',
    messageCount: 3,
    lastActivity: NOW - 3 * DAY,
    preview: 'What are the current output guard rules configured?',
  },
]

function getMockSessions() {
  return [
    { ...mockSessions[0], preview: '팀 워크스페이스에 Jira 연동을 어떻게 설정하나요?' },
    { ...mockSessions[1], preview: 'Confluence에서 1분기 영업 보고서를 요약해 주세요.' },
    { ...mockSessions[2], preview: '프로덕션에서 발생하는 API 타임아웃 오류 디버깅을 도와줄 수 있나요?' },
    { ...mockSessions[3], preview: '현재 설정된 출력 가드 규칙이 무엇인가요?' },
  ]
}

export const mockSessionDetail = {
  sessionId: 'session-1',
  messages: [
    { role: 'user', content: 'How do I set up the Jira integration for our team workspace?', timestamp: NOW - 2 * HOUR - 600000 },
    { role: 'assistant', content: 'To set up the Jira integration, navigate to MCP Servers and register a new Atlassian server. You\'ll need your Jira API token and base URL.', timestamp: NOW - 2 * HOUR - 540000 },
    { role: 'user', content: 'Where do I find the API token?', timestamp: NOW - 2 * HOUR - 480000 },
    { role: 'assistant', content: 'Go to Atlassian Account Settings > Security > API tokens > Create API token. Copy the token and paste it into the MCP server configuration.', timestamp: NOW - 2 * HOUR - 420000 },
  ],
}

function getMockSessionDetail() {
  return {
    ...mockSessionDetail,
    messages: [
      { role: 'user', content: '팀 워크스페이스에 Jira 연동을 어떻게 설정하나요?', timestamp: NOW - 2 * HOUR - 600000 },
      { role: 'assistant', content: 'Jira 연동을 설정하려면 MCP 서버로 이동하여 새 Atlassian 서버를 등록하세요. Jira API 토큰과 기본 URL이 필요합니다.', timestamp: NOW - 2 * HOUR - 540000 },
      { role: 'user', content: 'API 토큰은 어디에서 찾을 수 있나요?', timestamp: NOW - 2 * HOUR - 480000 },
      { role: 'assistant', content: 'Atlassian 계정 설정 > 보안 > API 토큰 > API 토큰 생성으로 이동하세요. 토큰을 복사하여 MCP 서버 설정에 붙여넣으세요.', timestamp: NOW - 2 * HOUR - 420000 },
    ],
  }
}

export const mockModels = {
  models: [
    { name: 'claude-sonnet-4-20250514', isDefault: true },
    { name: 'claude-haiku-35-20241022', isDefault: false },
    { name: 'claude-opus-4-20250514', isDefault: false },
  ],
  defaultModel: 'claude-sonnet-4-20250514',
}

export const sessionsHandlers = [
  http.get('/api/sessions', () => {
    return HttpResponse.json(getMockSessions())
  }),

  http.get('/api/sessions/:id', ({ params }) => {
    const sessions = getMockSessions()
    const session = sessions.find(s => s.sessionId === params.id)
    if (!session) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json({ ...getMockSessionDetail(), sessionId: params.id })
  }),

  http.delete('/api/sessions/:id', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  // Models
  http.get('/api/models', () => {
    return HttpResponse.json(mockModels)
  }),

  // ---- Admin Sessions ----
  http.get('/api/admin/sessions/overview', ({ request }) => {
    const url = new URL(request.url)
    const period = url.searchParams.get('period') ?? '7d'
    return HttpResponse.json({
      period,
      days: Number.parseInt(period, 10) || 7,
      totalSessions: 150,
      statusCounts: { completed: 145, failed: 5 },
      uniqueUsers: 20,
    })
  }),

  http.get('/api/admin/sessions/:sessionId/export', () => {
    return new HttpResponse(JSON.stringify({ sessionId: 'sess_1', exportedAt: NOW, messages: [] }), {
      headers: { 'Content-Type': 'application/json', 'Content-Disposition': 'attachment; filename="session-export.json"' },
    })
  }),

  http.get('/api/admin/sessions/:sessionId', ({ params }) => {
    const sessionId = params.sessionId as string
    return HttpResponse.json({
      sessionId,
      userId: 'user_001',
      channel: 'web',
      personaId: 'p1',
      personaName: 'Default',
      model: null,
      messageCount: 3,
      duration: 60000,
      startedAt: NOW - HOUR,
      lastActivity: NOW,
      trust: 'clean',
      feedback: 'positive',
      tags: [],
      messages: [
        { id: 1, role: 'user', content: 'Hello', timestamp: NOW - HOUR },
        { id: 2, role: 'assistant', content: 'Hi there!', timestamp: NOW - HOUR + 2000, model: 'gpt-4', durationMs: 1500 },
        { id: 3, role: 'user', content: 'Thanks', timestamp: NOW - HOUR + 5000 },
      ],
    })
  }),

  http.get('/api/admin/sessions', ({ request }) => {
    const url = new URL(request.url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const limit = Number(url.searchParams.get('limit') ?? 30)
    const channel = url.searchParams.getAll('channel')
    const sessions = Array.from({ length: 50 }, (_, i) => ({
      sessionId: `sess_${i + 1}`,
      userId: `user_${String((i % 5) + 1).padStart(3, '0')}`,
      channel: (['web', 'slack', 'teams'] as const)[i % 3],
      status: i % 7 === 0 ? 'failed' : 'completed',
      createdAt: NOW - (i + 1) * HOUR,
      updatedAt: NOW - i * HOUR,
      personaId: 'p1',
      personaName: 'Default',
      messageCount: 3 + i,
      preview: `대화 ${i + 1}의 최근 질문`,
    }))
    const filtered = channel.length > 0 ? sessions.filter((s) => channel.includes(s.channel)) : sessions
    return HttpResponse.json({
      items: filtered.slice(offset, offset + limit),
      total: filtered.length,
      offset,
      limit,
    })
  }),

  http.delete('/api/admin/sessions/:sessionId', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/admin/users/:userId/sessions', ({ request }) => {
    const url = new URL(request.url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const limit = Number(url.searchParams.get('limit') ?? 30)
    const items = Array.from({ length: 5 }, (_, i) => ({
      sessionId: `sess_u_${i + 1}`,
      userId: 'user_001',
      channel: 'web' as const,
      status: i === 0 ? 'failed' : 'completed',
      createdAt: NOW - (i + 1) * HOUR,
      updatedAt: NOW - i * HOUR,
      personaId: 'p1',
      personaName: 'Default',
      messageCount: 3 + i,
      preview: `사용자 대화 ${i + 1}`,
    }))
    return HttpResponse.json({ items: items.slice(offset, offset + limit), total: items.length, offset, limit })
  }),

  http.get('/api/admin/users', ({ request }) => {
    const url = new URL(request.url)
    const offset = Number(url.searchParams.get('offset') ?? 0)
    const limit = Number(url.searchParams.get('limit') ?? 30)
    const q = url.searchParams.get('q')
    const users = Array.from({ length: 20 }, (_, i) => ({
      userId: `user_${String(i + 1).padStart(3, '0')}`,
      sessionCount: 20 - i,
      totalMessages: 100 - i * 5,
      lastActive: NOW - i * DAY,
      firstSeen: NOW - 30 * DAY,
      trustIssueCount: i % 5 === 0 ? 2 : 0,
      negativeFeedbackCount: i % 3 === 0 ? 1 : 0,
      positiveFeedbackCount: 5,
    }))
    const filtered = q ? users.filter((u) => u.userId.includes(q)) : users
    return HttpResponse.json({ items: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit })
  }),

  http.post('/api/admin/sessions/:sessionId/tags', async ({ request, params }) => {
    const body = await request.json() as { label: string; comment?: string }
    void params.sessionId
    return HttpResponse.json({
      id: `tag_${NOW}`,
      label: body.label,
      comment: body.comment ?? null,
      createdBy: 'admin',
      createdAt: NOW,
    })
  }),

  http.delete('/api/admin/sessions/:sessionId/tags/:tagId', () => {
    return new HttpResponse(null, { status: 204 })
  }),
]

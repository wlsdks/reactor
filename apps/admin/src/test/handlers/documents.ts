import { http, HttpResponse } from 'msw'
import { NOW, HOUR, DAY } from './shared'

export const mockDocumentCandidates = [
  {
    id: 'candidate-1',
    runId: 'run-201',
    channel: 'slack',
    query: 'How do I configure SSO for the admin dashboard?',
    response: 'SSO can be configured by navigating to Platform Admin > Security > Authentication and enabling SAML or OIDC provider settings.',
    status: 'PENDING' as const,
    capturedAt: NOW - 4 * HOUR,
    reviewedAt: null,
    reviewedBy: null,
    reviewComment: null,
    ingestedDocumentId: null,
  },
  {
    id: 'candidate-2',
    runId: 'run-202',
    channel: 'web',
    query: 'What are the rate limits for the Jira integration?',
    response: 'The Jira integration is configured with a rate limit of 10 requests per second per service. You can check current usage in MCP Servers > atlassian > Preflight.',
    status: 'INGESTED' as const,
    capturedAt: NOW - 2 * DAY,
    reviewedAt: NOW - DAY,
    reviewedBy: 'admin@example.com',
    reviewComment: 'Good knowledge base entry for operations team',
    ingestedDocumentId: 'doc-ingested-1',
  },
  {
    id: 'candidate-3',
    runId: 'run-203',
    channel: 'slack',
    query: 'Can I use the bot to send emails?',
    response: 'Email sending is not currently supported. The platform supports Slack and Teams channels for outbound messaging.',
    status: 'REJECTED' as const,
    capturedAt: NOW - 3 * DAY,
    reviewedAt: NOW - 2 * DAY,
    reviewedBy: 'ops@example.com',
    reviewComment: 'Too specific and may become outdated when email integration is added',
    ingestedDocumentId: null,
  },
]

function getMockDocumentCandidates() {
  return [
    {
      ...mockDocumentCandidates[0],
      query: '관리자 대시보드에서 SSO를 어떻게 설정하나요?',
      response: 'SSO는 플랫폼 관리자 > 보안 > 인증으로 이동하여 SAML 또는 OIDC 프로바이더 설정을 활성화하면 됩니다.',
    },
    {
      ...mockDocumentCandidates[1],
      query: 'Jira 연동의 속도 제한은 어떻게 되나요?',
      response: 'Jira 연동은 서비스당 초당 10건의 요청으로 속도 제한이 설정되어 있습니다. MCP 서버 > atlassian > 사전 점검에서 현재 사용량을 확인할 수 있습니다.',
      reviewComment: '운영팀을 위한 좋은 지식 베이스 항목',
    },
    {
      ...mockDocumentCandidates[2],
      query: '봇으로 이메일을 보낼 수 있나요?',
      response: '이메일 전송은 현재 지원되지 않습니다. 플랫폼은 아웃바운드 메시징을 위해 Slack과 Teams 채널을 지원합니다.',
      reviewComment: '너무 구체적이며 이메일 연동이 추가되면 구식이 될 수 있음',
    },
  ]
}

export const mockRagIngestionPolicy = {
  configEnabled: true,
  dynamicEnabled: true,
  effective: {
    enabled: true,
    requireReview: true,
    allowedChannels: ['slack', 'web'],
    minQueryChars: 20,
    minResponseChars: 50,
    blockedPatterns: ['password', 'secret', 'api_key'],
    createdAt: NOW - 15 * DAY,
    updatedAt: NOW - 3 * DAY,
  },
  stored: {
    enabled: true,
    requireReview: true,
    allowedChannels: ['slack', 'web'],
    minQueryChars: 20,
    minResponseChars: 50,
    blockedPatterns: ['password', 'secret', 'api_key'],
    createdAt: NOW - 15 * DAY,
    updatedAt: NOW - 3 * DAY,
  },
}

export const documentsHandlers = [
  http.post('/api/admin/rag/seed-policy', async ({ request }) => {
    const body = await request.json() as { entries?: Array<{ key?: string }> }
    const entries = body.entries ?? []
    return HttpResponse.json({
      documentCount: entries.length,
      chunkCount: entries.length * 2,
      keys: entries.flatMap((entry) => entry.key ? [entry.key] : []),
      durationMs: 42,
    })
  }),

  http.post('/api/documents/search', async ({ request }) => {
    const body = await request.json() as { query: string }
    return HttpResponse.json([
      { id: 'doc-1', content: `검색 결과: ${body.query}\n\nJira 연동은 이슈 생성, 업데이트, 검색을 지원합니다. MCP 서버에서 접근 권한을 설정하세요.`, metadata: { source: 'knowledge_base' }, score: 0.92 },
      { id: 'doc-2', content: '속도 제한은 MCP 사전 점검 설정에서 서비스별로 구성됩니다. 기본값은 10 req/s입니다.', metadata: { source: 'docs' }, score: 0.78 },
    ])
  }),

  http.post('/api/documents', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ id: 'doc-new', content: body.content, metadata: body.metadata ?? {} })
  }),

  http.get('/api/rag-ingestion/candidates', () => {
    return HttpResponse.json(getMockDocumentCandidates())
  }),

  http.post('/api/rag-ingestion/candidates/:id/approve', ({ params }) => {
    const candidates = getMockDocumentCandidates()
    const candidate = candidates.find(c => c.id === params.id)
    if (!candidate) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json({ ...candidate, status: 'INGESTED', reviewedAt: NOW, reviewedBy: 'admin@example.com' })
  }),

  http.post('/api/rag-ingestion/candidates/:id/reject', ({ params }) => {
    const candidates = getMockDocumentCandidates()
    const candidate = candidates.find(c => c.id === params.id)
    if (!candidate) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json({ ...candidate, status: 'REJECTED', reviewedAt: NOW, reviewedBy: 'admin@example.com' })
  }),

  http.get('/api/rag-ingestion/policy', () => {
    return HttpResponse.json(mockRagIngestionPolicy)
  }),

  http.put('/api/rag-ingestion/policy', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ ...mockRagIngestionPolicy.effective, ...body, updatedAt: NOW })
  }),

  http.delete('/api/rag-ingestion/policy', () => {
    return new HttpResponse(null, { status: 204 })
  }),
]

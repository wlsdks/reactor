import { http, HttpResponse } from 'msw'
import { NOW, HOUR, DAY } from './shared'

export const mockMcpServers = [
  {
    id: 'mcp-1',
    name: 'atlassian',
    description: 'Atlassian Jira & Confluence integration server',
    transportType: 'SSE',
    autoConnect: true,
    status: 'CONNECTED',
    toolCount: 8,
    createdAt: NOW - 30 * DAY,
    updatedAt: NOW - 2 * HOUR,
  },
  {
    id: 'mcp-2',
    name: 'swagger',
    description: 'OpenAPI/Swagger specification management',
    transportType: 'SSE',
    autoConnect: false,
    status: 'DISCONNECTED',
    toolCount: 4,
    createdAt: NOW - 20 * DAY,
    updatedAt: NOW - 5 * DAY,
  },
]

function getMockMcpServers() {
  return [
    { ...mockMcpServers[0], description: 'Atlassian Jira & Confluence 연동 서버' },
    { ...mockMcpServers[1], description: 'OpenAPI/Swagger 사양 관리' },
  ]
}

function toBackendServer(server: ReturnType<typeof getMockMcpServers>[number]) {
  return {
    server_id: server.id,
    tenant_id: 'tenant-demo',
    name: server.name,
    transport: 'streamable_http',
    status: server.status === 'CONNECTED' ? 'healthy' : 'registered',
    command: null,
    url: server.name === 'atlassian' ? 'http://localhost:8085/mcp' : 'http://localhost:8081/mcp',
    auth_type: 'none',
    timeout_ms: 15_000,
    protocol_version: '2025-06-18',
    created_at: new Date(server.createdAt).toISOString(),
    updated_at: new Date(server.updatedAt).toISOString(),
  }
}

export const mockMcpServerDetail = {
  id: 'mcp-1',
  name: 'atlassian',
  description: 'Atlassian Jira & Confluence integration server',
  transportType: 'SSE',
  config: { baseUrl: 'https://example.atlassian.net', apiToken: '***' },
  version: '1.2.0',
  autoConnect: true,
  status: 'CONNECTED',
  tools: ['jira_search', 'jira_create_issue', 'jira_update_issue', 'confluence_get_page', 'confluence_search', 'confluence_update_page', 'bitbucket_list_repos', 'bitbucket_get_file'],
  createdAt: NOW - 30 * DAY,
  updatedAt: NOW - 2 * HOUR,
}

export const mockMcpPreflight = {
  ok: true,
  readyForProduction: true,
  policySource: 'dynamic',
  checkedAt: new Date(NOW - HOUR).toISOString(),
  kind: 'operational' as const,
  summary: { passCount: 5, warnCount: 1, failCount: 0 },
  rateBudget: {
    observedWindow: 'PT1H',
    services: [
      { service: 'jira', configuredRequestsPerSecond: 10, requestTotal: 245, retryTotal: 2, status429Total: 0, attention: false },
      { service: 'confluence', configuredRequestsPerSecond: 10, requestTotal: 87, retryTotal: 0, status429Total: 0, attention: false },
    ],
    summary: { configuredRequestsPerSecond: 10, attentionServices: 0, rateLimitedServices: 0 },
  },
  checks: [
    { name: 'Connection Health', status: 'PASS', message: 'Server responds within 200ms' },
    { name: 'Authentication', status: 'PASS', message: 'API token is valid' },
    { name: 'Tool Discovery', status: 'PASS', message: '8 tools available' },
    { name: 'Policy Bound', status: 'PASS', message: 'Access policy configured' },
    { name: 'Rate Budget', status: 'PASS', message: 'All services within budget' },
    { name: 'Schema Version', status: 'WARN', message: 'Server schema v1.1.0 is behind latest v1.2.0' },
  ],
}

function getMockMcpPreflight() {
  return {
    ...mockMcpPreflight,
    checks: [
      { name: '연결 상태', status: 'PASS', message: '서버가 200ms 이내에 응답합니다' },
      { name: '인증', status: 'PASS', message: 'API 토큰이 유효합니다' },
      { name: '도구 탐색', status: 'PASS', message: '8개 도구 사용 가능' },
      { name: '정책 바인딩', status: 'PASS', message: '접근 정책이 설정되었습니다' },
      { name: '속도 예산', status: 'PASS', message: '모든 서비스가 예산 범위 내입니다' },
      { name: '스키마 버전', status: 'WARN', message: '서버 스키마 v1.1.0이 최신 v1.2.0보다 이전 버전입니다' },
    ],
  }
}

export const mockMcpAccessPolicy = {
  allowedJiraProjectKeys: ['DEMO', 'OPS', 'PLAT'],
  allowedConfluenceSpaceKeys: ['ENG', 'OPS'],
  allowedBitbucketRepositories: ['reactor-admin', 'reactor-api'],
  allowedSourceNames: ['petstore-api'],
  allowPreviewReads: true,
  allowPreviewWrites: false,
  allowDirectUrlLoads: false,
  publishedOnly: true,
  policySource: 'dynamic',
  dynamicEnabled: true,
  dynamicPolicy: null,
}

export const mcpServersHandlers = [
  http.get('/api/mcp/servers', () => {
    return HttpResponse.json(getMockMcpServers().map(toBackendServer))
  }),

  http.get('/api/mcp/servers/:name', ({ params }) => {
    const servers = getMockMcpServers()
    const server = servers.find(s => s.name === params.name)
    if (!server) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json(toBackendServer(server))
  }),

  http.post('/api/mcp/servers', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json(
      { id: 'mcp-new', ...body, status: 'DISCONNECTED', toolCount: 0, createdAt: NOW, updatedAt: NOW },
      { status: 201 },
    )
  }),

  http.post('/api/mcp/servers/:name/connect', ({ params }) => {
    return HttpResponse.json({
      status: 'CONNECTED',
      tools: params.name === 'atlassian' ? mockMcpServerDetail.tools : ['swagger_sync', 'swagger_search'],
    })
  }),

  http.post('/api/mcp/servers/:name/disconnect', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/mcp/servers/:name/preflight', () => {
    return HttpResponse.json(getMockMcpPreflight())
  }),

  http.get('/api/mcp/servers/:name/access-policy', () => {
    return HttpResponse.json(mockMcpAccessPolicy)
  }),

  http.put('/api/mcp/servers/:name/access-policy', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ ...mockMcpAccessPolicy, ...body })
  }),

  http.delete('/api/mcp/servers/:name/access-policy', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/mcp/servers/:serverName/swagger/sources', () => {
    return HttpResponse.json([
      {
        id: 'source-1',
        name: 'petstore-api',
        url: 'https://petstore.swagger.io/v2/swagger.json',
        enabled: true,
        syncCron: '0 */6 * * *',
        jiraProjectKey: 'DEMO',
        confluenceSpaceKey: 'ENG',
        bitbucketRepository: null,
        serviceSlug: 'petstore',
        ownerTeam: 'platform',
        publishedRevisionId: 'rev-1',
        etag: '"abc123"',
        lastModified: new Date(NOW - 6 * HOUR).toISOString(),
        lastSyncStatus: 'SUCCESS',
        lastSyncMessage: '변경 사항 없음',
        lastSyncAt: new Date(NOW - 6 * HOUR).toISOString(),
        createdAt: new Date(NOW - 20 * DAY).toISOString(),
        updatedAt: new Date(NOW - 6 * HOUR).toISOString(),
      },
    ])
  }),
]

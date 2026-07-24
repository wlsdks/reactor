import { http, HttpResponse } from 'msw'
import { NOW, HOUR, DAY } from './shared'

export const mockPlatformHealth = {
  pipelineBufferUsage: 0,
  pipelineDropRate: 0,
  pipelineWriteLatencyMs: 0,
  pipelineMetricsAvailable: false,
  responseCacheEnabled: true,
  activeAlerts: 1,
  cacheExactHits: 1240,
  cacheSemanticHits: 380,
  cacheMisses: 222,
}

export const mockTenants = [
  {
    id: 'tenant-1',
    name: 'Example Corp',
    slug: 'example-corp',
    plan: 'ENTERPRISE' as const,
    status: 'ACTIVE' as const,
    quota: { maxRequestsPerMonth: 100000, maxTokensPerMonth: 50000000, maxUsers: 100, maxAgents: 10, maxMcpServers: 20 },
    billingCycleStart: NOW - 15 * DAY,
    billingEmail: 'billing@example.com',
    sloAvailability: 99.95,
    sloLatencyP99Ms: 500,
    metadata: { region: 'ap-northeast-2' },
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-03-15T00:00:00Z',
  },
  {
    id: 'tenant-2',
    name: 'Acme Corp',
    slug: 'acme-corp',
    plan: 'BUSINESS' as const,
    status: 'ACTIVE' as const,
    quota: { maxRequestsPerMonth: 50000, maxTokensPerMonth: 20000000, maxUsers: 50, maxAgents: 5, maxMcpServers: 10 },
    billingCycleStart: NOW - 10 * DAY,
    billingEmail: 'admin@tenant-a.example',
    sloAvailability: 99.9,
    sloLatencyP99Ms: 800,
    metadata: { region: 'us-west-2' },
    createdAt: '2024-02-15T00:00:00Z',
    updatedAt: '2024-03-10T00:00:00Z',
  },
  {
    id: 'tenant-3',
    name: 'Startup Inc',
    slug: 'startup-inc',
    plan: 'STARTER' as const,
    status: 'SUSPENDED' as const,
    quota: { maxRequestsPerMonth: 10000, maxTokensPerMonth: 5000000, maxUsers: 10, maxAgents: 2, maxMcpServers: 3 },
    billingCycleStart: NOW - 25 * DAY,
    billingEmail: 'dev@tenant-b.example',
    sloAvailability: 99.5,
    sloLatencyP99Ms: 1000,
    metadata: { region: 'eu-west-1' },
    createdAt: '2024-03-01T00:00:00Z',
    updatedAt: '2024-03-18T00:00:00Z',
  },
]

export const mockTenantAnalytics = [
  { tenantId: 'tenant-1', tenantName: 'Example Corp', plan: 'ENTERPRISE', requests: 42150, cost: '2,150.30', sloStatus: 'HEALTHY', quotaUsagePercent: 42.1 },
  { tenantId: 'tenant-2', tenantName: 'Acme Corp', plan: 'BUSINESS', requests: 18200, cost: '890.50', sloStatus: 'HEALTHY', quotaUsagePercent: 36.4 },
  { tenantId: 'tenant-3', tenantName: 'Startup Inc', plan: 'STARTER', requests: 0, cost: '0.00', sloStatus: 'SUSPENDED', quotaUsagePercent: 0 },
]

export const mockModelPricing = [
  { id: 'price-1', provider: 'anthropic', model: 'claude-sonnet-4-20250514', promptPricePer1m: '3', completionPricePer1m: '15', cachedInputPricePer1m: '0.3', reasoningPricePer1m: '0', batchPromptPricePer1m: '0', batchCompletionPricePer1m: '0', effectiveFrom: '2025-01-01', effectiveTo: null },
  { id: 'price-2', provider: 'anthropic', model: 'claude-opus-4-20250514', promptPricePer1m: '15', completionPricePer1m: '75', cachedInputPricePer1m: '1.5', reasoningPricePer1m: '0', batchPromptPricePer1m: '0', batchCompletionPricePer1m: '0', effectiveFrom: '2025-01-01', effectiveTo: null },
  { id: 'price-3', provider: 'anthropic', model: 'claude-haiku-35-20241022', promptPricePer1m: '0.8', completionPricePer1m: '4', cachedInputPricePer1m: '0.08', reasoningPricePer1m: '0', batchPromptPricePer1m: '0', batchCompletionPricePer1m: '0', effectiveFrom: '2024-10-22', effectiveTo: null },
]

export const mockAlertRules = [
  { id: 'alert-rule-1', tenantId: null, name: 'High Latency Alert', description: 'Fires when p99 latency exceeds 500ms', type: 'STATIC_THRESHOLD' as const, severity: 'WARNING' as const, metric: 'api.latency.p99', threshold: 500, windowMinutes: 5, enabled: true, platformOnly: true, createdAt: '2024-02-01T00:00:00Z' },
  { id: 'alert-rule-2', tenantId: null, name: 'Error Rate Spike', description: 'Fires when error rate exceeds 5%', type: 'BASELINE_ANOMALY' as const, severity: 'CRITICAL' as const, metric: 'api.errors.rate', threshold: 5, windowMinutes: 10, enabled: true, platformOnly: true, createdAt: '2024-02-01T00:00:00Z' },
]

function getMockAlertRules() {
  return [
    { ...mockAlertRules[0], name: '높은 지연 시간 알림', description: 'p99 지연 시간이 500ms를 초과하면 발생' },
    { ...mockAlertRules[1], name: '오류율 급증', description: '오류율이 5%를 초과하면 발생' },
  ]
}

export const mockActiveAlerts = [
  { id: 'alert-1', ruleId: 'alert-rule-1', tenantId: null, severity: 'WARNING' as const, status: 'FIRING', message: 'API p99 latency is 520ms (threshold: 500ms)', metricValue: 520, threshold: 500, firedAt: NOW - 2 * HOUR, resolvedAt: null, acknowledgedBy: null },
]

function getMockActiveAlerts() {
  return [
    { ...mockActiveAlerts[0], message: 'API p99 지연 시간 520ms (임계값: 500ms)' },
  ]
}

export const mockTenantOverview = {
  tenantId: 'tenant-1',
  tenantName: 'Example Corp',
  plan: 'ENTERPRISE',
  status: 'ACTIVE',
  totalRequests: 42150,
  totalTokens: 18500000,
  activeUsers: 23,
  activeSessions: 8,
  connectedMcpServers: 1,
  lastActivityAt: NOW - HOUR,
}

export const mockTenantUsage = {
  requestsByDay: [
    { date: new Date(NOW - 6 * DAY).toISOString().split('T')[0], count: 5800 },
    { date: new Date(NOW - 5 * DAY).toISOString().split('T')[0], count: 6200 },
    { date: new Date(NOW - 4 * DAY).toISOString().split('T')[0], count: 5950 },
    { date: new Date(NOW - 3 * DAY).toISOString().split('T')[0], count: 7100 },
    { date: new Date(NOW - 2 * DAY).toISOString().split('T')[0], count: 6400 },
    { date: new Date(NOW - DAY).toISOString().split('T')[0], count: 6800 },
    { date: new Date(NOW).toISOString().split('T')[0], count: 3900 },
  ],
  totalRequests: 42150,
  totalTokens: 18500000,
  avgLatencyMs: 285,
}

export const mockTenantQuality = {
  feedbackPositiveRate: 0.87,
  groundedRate: 0.93,
  errorRate: 0.02,
  avgResponseTimeMs: 1850,
  totalFeedback: 156,
  positiveFeedback: 136,
}

export const mockTenantCost = {
  totalCost: 2150.3,
  apiCallCost: 245.8,
  tokenCost: 1892.5,
  storageCost: 12.0,
  costByModel: [
    { model: 'claude-sonnet-4-20250514', cost: 1450.2, tokens: 12000000 },
    { model: 'claude-opus-4-20250514', cost: 688.1, tokens: 6200000 },
    { model: 'claude-haiku-35-20241022', cost: 12.0, tokens: 300000 },
  ],
}

export const mockTenantQuota = {
  quota: { maxRequestsPerMonth: 100000, maxTokensPerMonth: 50000000, maxUsers: 100, maxAgents: 10, maxMcpServers: 20 },
  usage: { requests: 42150, tokens: 18500000, users: 23, agents: 3, mcpServers: 2 },
  requestUsagePercent: 42.1,
  tokenUsagePercent: 37.0,
}

export const mockTenantSlo = {
  availability: { target: 99.95, actual: 99.98, status: 'HEALTHY' },
  latencyP99: { target: 500, actual: 425, status: 'HEALTHY' },
  errorBudgetRemaining: 0.85,
}

export const mockTenantAlerts = [
  { id: 'tenant-alert-1', severity: 'INFO', message: 'Token usage is at 37% of monthly quota', firedAt: new Date(NOW - 2 * HOUR).toISOString() },
]

function getMockTenantAlerts() {
  return [
    { ...mockTenantAlerts[0], message: '토큰 사용량이 월간 할당량의 37%입니다' },
  ]
}

export const platformAdminHandlers = [
  // Platform Admin
  http.get('/api/admin/platform/health', () => {
    return HttpResponse.json(mockPlatformHealth)
  }),

  http.get('/api/admin/platform/tenants', () => {
    return HttpResponse.json(mockTenants)
  }),

  http.get('/api/admin/platform/tenants/analytics', () => {
    return HttpResponse.json(mockTenantAnalytics)
  }),

  http.get('/api/admin/platform/tenants/:id', ({ params }) => {
    const tenant = mockTenants.find(t => t.id === params.id)
    if (!tenant) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json(tenant)
  }),

  http.post('/api/admin/platform/tenants', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json(
      { id: 'tenant-new', ...body, status: 'ACTIVE', quota: { maxRequestsPerMonth: 10000, maxTokensPerMonth: 5000000, maxUsers: 10, maxAgents: 2, maxMcpServers: 3 }, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() },
      { status: 201 },
    )
  }),

  http.post('/api/admin/platform/tenants/:id/suspend', ({ params }) => {
    const tenant = mockTenants.find(t => t.id === params.id)
    if (!tenant) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json({ ...tenant, status: 'SUSPENDED' })
  }),

  http.post('/api/admin/platform/tenants/:id/activate', ({ params }) => {
    const tenant = mockTenants.find(t => t.id === params.id)
    if (!tenant) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json({ ...tenant, status: 'ACTIVE' })
  }),

  http.get('/api/admin/platform/pricing', () => {
    return HttpResponse.json(mockModelPricing)
  }),

  http.post('/api/admin/platform/pricing', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ id: 'price-new', ...body })
  }),

  http.get('/api/admin/platform/alerts/rules', () => {
    return HttpResponse.json(getMockAlertRules())
  }),

  http.post('/api/admin/platform/alerts/rules', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ id: 'alert-rule-new', ...body, createdAt: new Date().toISOString() })
  }),

  http.delete('/api/admin/platform/alerts/rules/:id', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/admin/platform/alerts', () => {
    return HttpResponse.json(getMockActiveAlerts())
  }),

  http.post('/api/admin/platform/alerts/:id/resolve', () => {
    return new HttpResponse(null, { status: 200 })
  }),

  http.post('/api/admin/platform/alerts/evaluate', () => {
    return HttpResponse.json({ status: 'evaluated' })
  }),

  http.post('/api/admin/platform/cache/invalidate', () => {
    return HttpResponse.json({ invalidated: true, cacheEnabled: true, message: '응답 캐시가 성공적으로 무효화되었습니다' })
  }),

  http.get('/api/admin/platform/users/by-email', ({ request }) => {
    const url = new URL(request.url)
    const email = url.searchParams.get('email')
    return HttpResponse.json({
      id: 'user-lookup-1',
      email: email ?? 'user@example.com',
      name: 'Lookup User',
      role: 'USER' as const,
      adminScope: null,
      createdAt: '2024-01-15T00:00:00Z',
    })
  }),

  http.post('/api/admin/platform/users/:userId/role', async ({ params, request }) => {
    const body = await request.json() as { role: string }
    return HttpResponse.json({
      id: params.userId,
      email: 'user@example.com',
      name: 'Updated User',
      role: body.role,
      adminScope: null,
      createdAt: '2024-01-15T00:00:00Z',
    })
  }),

  // Tenant Admin
  http.get('/api/admin/tenant/overview', () => {
    return HttpResponse.json(mockTenantOverview)
  }),

  http.get('/api/admin/tenant/usage', () => {
    return HttpResponse.json(mockTenantUsage)
  }),

  http.get('/api/admin/tenant/quality', () => {
    return HttpResponse.json(mockTenantQuality)
  }),

  http.get('/api/admin/tenant/tools', () => {
    return HttpResponse.json({
      toolCalls: [
        { toolName: 'jira_search', callCount: 95, avgDurationMs: 850, errorRate: 0.02 },
        { toolName: 'confluence_get_page', callCount: 72, avgDurationMs: 620, errorRate: 0.01 },
        { toolName: 'web_search', callCount: 45, avgDurationMs: 1200, errorRate: 0.04 },
        { toolName: 'calculator', callCount: 18, avgDurationMs: 50, errorRate: 0 },
      ],
    })
  }),

  http.get('/api/admin/tenant/cost', () => {
    return HttpResponse.json(mockTenantCost)
  }),

  http.get('/api/admin/tenant/slo', () => {
    return HttpResponse.json(mockTenantSlo)
  }),

  http.get('/api/admin/tenant/alerts', () => {
    return HttpResponse.json(getMockTenantAlerts())
  }),

  http.get('/api/admin/tenant/quota', () => {
    return HttpResponse.json(mockTenantQuota)
  }),

  http.get('/api/admin/tenant/export/executions', () => {
    return HttpResponse.text('timestamp,session_id,query,response_time_ms,tokens,model\n2024-03-20T10:00:00Z,session-1,Jira 설정은 어떻게 하나요?,1250,450,claude-sonnet-4\n')
  }),

  http.get('/api/admin/tenant/export/tools', () => {
    return HttpResponse.text('timestamp,tool_name,duration_ms,success,error\n2024-03-20T10:00:00Z,jira_search,850,true,\n')
  }),

  // Metric Ingestion (OPTIONS for probe support)
  http.options('/api/admin/metrics/ingest/mcp-health', () => {
    return new HttpResponse(null, { status: 204, headers: { Allow: 'POST, OPTIONS' } })
  }),
  http.post('/api/admin/metrics/ingest/mcp-health', () => {
    return HttpResponse.json({ status: 'accepted', count: 1 })
  }),
  http.options('/api/admin/metrics/ingest/tool-call', () => {
    return new HttpResponse(null, { status: 204, headers: { Allow: 'POST, OPTIONS' } })
  }),
  http.post('/api/admin/metrics/ingest/tool-call', () => {
    return HttpResponse.json({ status: 'accepted', count: 1 })
  }),
  http.options('/api/admin/metrics/ingest/eval-result', () => {
    return new HttpResponse(null, { status: 204, headers: { Allow: 'POST, OPTIONS' } })
  }),
  http.post('/api/admin/metrics/ingest/eval-result', () => {
    return HttpResponse.json({ status: 'accepted', count: 1 })
  }),
  http.options('/api/admin/metrics/ingest/eval-results', () => {
    return new HttpResponse(null, { status: 204, headers: { Allow: 'POST, OPTIONS' } })
  }),
  http.post('/api/admin/metrics/ingest/eval-results', () => {
    return HttpResponse.json({ status: 'accepted', count: 1 })
  }),
  http.options('/api/admin/metrics/ingest/batch', () => {
    return new HttpResponse(null, { status: 204, headers: { Allow: 'POST, OPTIONS' } })
  }),
  http.post('/api/admin/metrics/ingest/batch', () => {
    return HttpResponse.json({ status: 'accepted', count: 1 })
  }),
]

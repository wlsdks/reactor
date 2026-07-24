import { http, HttpResponse } from 'msw'
import { NOW, DAY } from './shared'

export const mockToolPolicy = {
  configEnabled: true,
  dynamicEnabled: true,
  effective: {
    enabled: true,
    writeToolNames: ['write_file', 'apply_patch'],
    denyWriteChannels: ['commentary'],
    allowWriteToolNamesInDenyChannels: ['apply_patch'],
    allowWriteToolNamesByChannel: {
      summary: ['write_file'],
    },
    denyWriteMessage: 'Denied',
    createdAt: 1710000000000,
    updatedAt: 1710003600000,
  },
  stored: {
    enabled: true,
    writeToolNames: ['write_file'],
    denyWriteChannels: ['commentary'],
    allowWriteToolNamesInDenyChannels: [],
    allowWriteToolNamesByChannel: {},
    denyWriteMessage: 'Denied',
    createdAt: 1710000000000,
    updatedAt: 1710000000000,
  },
}

export const mockMcpSecurity = {
  effective: {
    allowedServerNames: ['atlassian'],
    maxToolOutputLength: 50000,
    createdAt: 1710000000000,
    updatedAt: 1710003600000,
  },
  stored: {
    allowedServerNames: ['atlassian'],
    maxToolOutputLength: 50000,
    createdAt: 1710000000000,
    updatedAt: 1710000000000,
  },
  configDefault: {
    allowedServerNames: ['atlassian', 'swagger'],
    maxToolOutputLength: 50000,
    createdAt: 1710000000000,
    updatedAt: 1710000000000,
  },
}

export const mockOutputGuardRules = [
  {
    id: 'rule-pii-filter',
    name: 'PII Filter',
    pattern: '\\b\\d{3}-\\d{2}-\\d{4}\\b|\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z]{2,}\\b',
    action: 'MASK' as const,
    priority: 1,
    enabled: true,
    createdAt: NOW - 30 * DAY,
    updatedAt: NOW - 5 * 3_600_000,
  },
  {
    id: 'rule-api-key',
    name: 'API Key Blocker',
    pattern: '(sk-[a-zA-Z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36})',
    action: 'REJECT' as const,
    priority: 2,
    enabled: true,
    createdAt: NOW - 25 * DAY,
    updatedAt: NOW - 25 * DAY,
  },
  {
    id: 'rule-internal-url',
    name: 'Internal URL Filter',
    pattern: 'https?://internal\\.[a-z]+\\.example\\.com',
    action: 'MASK' as const,
    priority: 3,
    enabled: false,
    createdAt: NOW - 10 * DAY,
    updatedAt: NOW - 2 * DAY,
  },
]

export const mockOutputGuardAudits = [
  {
    id: 'og-audit-1',
    ruleId: 'rule-pii-filter',
    action: 'MASK',
    actor: 'system',
    detail: 'Masked 2 email addresses in response to user query about team contacts',
    createdAt: NOW - 3 * 3_600_000,
  },
  {
    id: 'og-audit-2',
    ruleId: 'rule-api-key',
    action: 'REJECT',
    actor: 'system',
    detail: 'Blocked response containing GitHub personal access token',
    createdAt: NOW - 3_600_000,
  },
  {
    id: 'og-audit-3',
    ruleId: 'rule-pii-filter',
    action: 'MASK',
    actor: 'system',
    detail: 'Masked SSN pattern found in Jira ticket description',
    createdAt: NOW - 6 * 3_600_000,
  },
]

function getMockOutputGuardRules() {
  return [
    { ...mockOutputGuardRules[0], name: '개인정보 필터' },
    { ...mockOutputGuardRules[1], name: 'API 키 차단기' },
    { ...mockOutputGuardRules[2], name: '내부 URL 필터' },
  ]
}

function getMockOutputGuardAudits() {
  return [
    { ...mockOutputGuardAudits[0], detail: '팀 연락처에 대한 사용자 쿼리 응답에서 이메일 주소 2개 마스킹됨' },
    { ...mockOutputGuardAudits[1], detail: 'GitHub 개인 접근 토큰이 포함된 응답 차단됨' },
    { ...mockOutputGuardAudits[2], detail: 'Jira 티켓 설명에서 SSN 패턴이 감지되어 마스킹됨' },
  ]
}

export const governanceHandlers = [
  // Tool policy
  http.get('/api/tool-policy', () => {
    return HttpResponse.json(mockToolPolicy)
  }),
  http.put('/api/tool-policy', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({
      ...mockToolPolicy.effective,
      ...body,
      updatedAt: Date.now(),
    })
  }),
  http.delete('/api/tool-policy', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  // MCP security
  http.get('/api/mcp/security', () => {
    return HttpResponse.json(mockMcpSecurity)
  }),
  http.put('/api/mcp/security', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({
      ...mockMcpSecurity.effective,
      ...body,
      updatedAt: Date.now(),
    })
  }),
  http.delete('/api/mcp/security', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  // Output Guard
  http.get('/api/output-guard/rules', () => {
    return HttpResponse.json(getMockOutputGuardRules())
  }),

  http.get('/api/output-guard/rules/audits', () => {
    return HttpResponse.json(getMockOutputGuardAudits())
  }),

  http.post('/api/output-guard/rules', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json(
      { id: 'rule-new', ...body, priority: 10, enabled: true, createdAt: NOW, updatedAt: NOW },
      { status: 201 },
    )
  }),

  http.put('/api/output-guard/rules/:id', async ({ params, request }) => {
    const body = await request.json() as Record<string, unknown>
    const rules = getMockOutputGuardRules()
    const rule = rules.find(r => r.id === params.id)
    if (!rule) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json({ ...rule, ...body, updatedAt: NOW })
  }),

  http.delete('/api/output-guard/rules/:id', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/output-guard/rules/simulate', async ({ request }) => {
    const body = await request.json() as { content: string }
    return HttpResponse.json({
      originalContent: body.content,
      resultContent: body.content.replace(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}\b/gi, '[MASKED]'),
      blocked: false,
      modified: true,
      blockedByRuleId: null,
      blockedByRuleName: null,
      matchedRules: [{ ruleId: 'rule-pii-filter', ruleName: 'PII Filter', action: 'MASK', priority: 1 }],
      invalidRules: [],
    })
  }),
]

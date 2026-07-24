import { http, HttpResponse } from 'msw'

interface MockRule {
  id: string
  name: string
  pattern: string
  patternType: 'regex' | 'keyword'
  action: 'block' | 'warn' | 'flag'
  priority: number
  category: string
  description: string | null
  enabled: boolean
  createdAt: string
  updatedAt: string
}

const mockRules: MockRule[] = [
  { id: 'rule-001', name: 'Block PII patterns', pattern: '\\b\\d{3}-\\d{2}-\\d{4}\\b', patternType: 'regex', action: 'block', priority: 1, category: 'pii', description: 'Blocks SSN-like patterns in user input', enabled: true, createdAt: '2026-03-20T09:00:00Z', updatedAt: '2026-04-10T14:30:00Z' },
  { id: 'rule-002', name: 'Warn on profanity', pattern: 'badword|offensive', patternType: 'keyword', action: 'warn', priority: 2, category: 'profanity', description: 'Flags profane language with a warning', enabled: true, createdAt: '2026-03-22T11:00:00Z', updatedAt: '2026-04-08T10:00:00Z' },
  { id: 'rule-003', name: 'Flag competitor mentions', pattern: 'competitor-x|rival-corp', patternType: 'keyword', action: 'flag', priority: 5, category: 'brand', description: 'Flags mentions of competitor brands for review', enabled: true, createdAt: '2026-04-01T08:00:00Z', updatedAt: '2026-04-01T08:00:00Z' },
  { id: 'rule-004', name: 'Block credit card numbers', pattern: '\\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14})\\b', patternType: 'regex', action: 'block', priority: 1, category: 'pii', description: 'Blocks Visa/MC card number patterns', enabled: true, createdAt: '2026-04-05T16:00:00Z', updatedAt: '2026-04-12T09:15:00Z' },
  { id: 'rule-005', name: 'Block system prompt extraction', pattern: 'show me your (system )?prompt|reveal your instructions', patternType: 'regex', action: 'block', priority: 1, category: 'injection', description: null, enabled: false, createdAt: '2026-04-10T12:00:00Z', updatedAt: '2026-04-10T12:00:00Z' },
]

let nextRuleId = 6

export const mockInputGuardStages = [
  { name: 'rate-limit', order: 1, enabled: true, className: 'com.example.reactor.guard.RateLimitStage', runtimeOverride: false },
  { name: 'unicode-normalization', order: 2, enabled: true, className: 'com.example.reactor.guard.UnicodeNormStage', runtimeOverride: false },
  { name: 'injection-detection', order: 3, enabled: true, className: 'com.example.reactor.guard.InjectionDetectStage', runtimeOverride: false },
  { name: 'rule-classification', order: 4, enabled: true, className: 'com.example.reactor.guard.RuleClassStage', runtimeOverride: false },
  { name: 'llm-classification', order: 5, enabled: false, className: 'com.example.reactor.guard.LlmClassStage', runtimeOverride: true },
  { name: 'topic-drift', order: 6, enabled: true, className: 'com.example.reactor.guard.TopicDriftStage', runtimeOverride: false },
  { name: 'permission', order: 7, enabled: true, className: 'com.example.reactor.guard.PermissionStage', runtimeOverride: false },
]

export const inputGuardHandlers = [
  http.get('/api/admin/input-guard/pipeline', () => {
    return HttpResponse.json({ stages: mockInputGuardStages })
  }),

  http.put('/api/admin/input-guard/settings', async ({ request }) => {
    const body = await request.json() as { settings: Record<string, string> }
    const count = Object.keys(body.settings).length
    return HttpResponse.json({
      updated: count,
      note: 'Changes applied to runtime settings',
    })
  }),

  http.get('/api/admin/input-guard/stats', ({ request }) => {
    const url = new URL(request.url)
    const hours = Number(url.searchParams.get('hours') || '24')
    return HttpResponse.json({
      periodHours: hours,
      totalRequests: 15420,
      totalAllowed: 15078,
      totalRejected: 312,
      totalErrors: 30,
      blockRate: 0.0202,
      byStage: [
        { stage: 'rate-limit', triggered: 15420, allowed: 15300, rejected: 98, errors: 22, topReasons: [{ reason: 'rpm_exceeded', count: 71 }, { reason: 'burst_limit', count: 27 }] },
        { stage: 'unicode-normalization', triggered: 15300, allowed: 15298, rejected: 2, errors: 0, topReasons: [{ reason: 'mixed_script_block', count: 2 }] },
        { stage: 'injection-detection', triggered: 15298, allowed: 15146, rejected: 148, errors: 4, topReasons: [{ reason: 'prompt_override', count: 89 }, { reason: 'system_prompt_leak', count: 42 }, { reason: 'jailbreak_attempt', count: 17 }] },
        { stage: 'rule-classification', triggered: 15146, allowed: 15112, rejected: 30, errors: 4, topReasons: [{ reason: 'pii_detected', count: 18 }, { reason: 'profanity', count: 12 }] },
        { stage: 'llm-classification', triggered: 0, allowed: 0, rejected: 0, errors: 0, topReasons: [] },
        { stage: 'topic-drift', triggered: 15112, allowed: 15088, rejected: 24, errors: 0, topReasons: [{ reason: 'off_topic', count: 24 }] },
        { stage: 'permission', triggered: 15088, allowed: 15078, rejected: 10, errors: 0, topReasons: [{ reason: 'role_denied', count: 10 }] },
      ],
    })
  }),

  http.get('/api/admin/input-guard/audits', ({ request }) => {
    const url = new URL(request.url)
    const limit = Number(url.searchParams.get('limit') || '200')
    const action = url.searchParams.get('action')
    const now = Date.now()
    const allAudits = [
      { id: 'aud-001', timestamp: new Date(now - 3 * 60_000).toISOString(), category: 'GUARD', action: 'BLOCK', actor: 'user-7a3f', resourceType: 'injection-detection', resourceId: null, detail: 'Prompt override attempt blocked (confidence 0.94)' },
      { id: 'aud-002', timestamp: new Date(now - 8 * 60_000).toISOString(), category: 'GUARD', action: 'WARN', actor: 'user-b12c', resourceType: 'rule-classification', resourceId: 'rule-pii-01', detail: 'PII pattern detected in input — allowed with warning' },
      { id: 'aud-003', timestamp: new Date(now - 15 * 60_000).toISOString(), category: 'GUARD', action: 'BLOCK', actor: 'user-e4d9', resourceType: 'rate-limit', resourceId: null, detail: 'Rate limit exceeded: 65/60 rpm' },
      { id: 'aud-004', timestamp: new Date(now - 22 * 60_000).toISOString(), category: 'CONFIG', action: 'UPDATE_SETTINGS', actor: 'admin@example.com', resourceType: 'llm-classification', resourceId: null, detail: 'Stage disabled: guard.stage.llm-classification.enabled → false' },
      { id: 'aud-005', timestamp: new Date(now - 45 * 60_000).toISOString(), category: 'GUARD', action: 'BLOCK', actor: 'user-1f8a', resourceType: 'injection-detection', resourceId: null, detail: 'System prompt leak attempt detected' },
      { id: 'aud-006', timestamp: new Date(now - 72 * 60_000).toISOString(), category: 'GUARD', action: 'BLOCK', actor: 'user-c3e7', resourceType: 'topic-drift', resourceId: null, detail: 'Off-topic input rejected (drift score 0.87)' },
      { id: 'aud-007', timestamp: new Date(now - 90 * 60_000).toISOString(), category: 'GUARD', action: 'WARN', actor: 'user-9d2b', resourceType: 'rule-classification', resourceId: 'rule-profanity-02', detail: 'Profanity filter triggered — warning issued' },
      { id: 'aud-008', timestamp: new Date(now - 120 * 60_000).toISOString(), category: 'CONFIG', action: 'UPDATE_SETTINGS', actor: 'admin@example.com', resourceType: 'rate-limit', resourceId: null, detail: 'Updated: guard.stage.rate-limit.maxRpm → 60' },
    ]
    const filtered = action ? allAudits.filter((a) => a.action === action) : allAudits
    return HttpResponse.json({
      audits: filtered.slice(0, limit),
      total: filtered.length,
    })
  }),

  http.get('/api/admin/input-guard/rules', () => {
    return HttpResponse.json({
      rules: mockRules,
      total: mockRules.length,
    })
  }),

  http.get('/api/admin/input-guard/rules/:id', ({ params }) => {
    const id = params.id as string
    const rule = mockRules.find((r) => r.id === id)
    if (!rule) return new HttpResponse(null, { status: 404 })
    return HttpResponse.json(rule)
  }),

  http.post('/api/admin/input-guard/rules', async ({ request }) => {
    const body = await request.json() as Omit<MockRule, 'id' | 'createdAt' | 'updatedAt'>
    const now = new Date().toISOString()
    const rule: MockRule = {
      ...body,
      id: `rule-${String(nextRuleId++).padStart(3, '0')}`,
      description: body.description ?? null,
      createdAt: now,
      updatedAt: now,
    }
    mockRules.push(rule)
    return HttpResponse.json(rule, { status: 201 })
  }),

  http.put('/api/admin/input-guard/rules/:id', async ({ request, params }) => {
    const id = params.id as string
    const body = await request.json() as Omit<MockRule, 'id' | 'createdAt' | 'updatedAt'>
    const idx = mockRules.findIndex((r) => r.id === id)
    if (idx === -1) return new HttpResponse(null, { status: 404 })
    const updated: MockRule = {
      ...mockRules[idx],
      ...body,
      description: body.description ?? null,
      updatedAt: new Date().toISOString(),
    }
    mockRules[idx] = updated
    return HttpResponse.json(updated)
  }),

  http.delete('/api/admin/input-guard/rules/:id', ({ params }) => {
    const id = params.id as string
    const idx = mockRules.findIndex((r) => r.id === id)
    if (idx === -1) return new HttpResponse(null, { status: 404 })
    mockRules.splice(idx, 1)
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/admin/input-guard/simulate', async ({ request }) => {
    const body = await request.json() as { input: string; userId?: string }
    const input = body.input || ''
    const hasInjection = /ignore|system prompt|이전 지시/i.test(input)
    const isLong = input.length > 10000
    const hasHomograph = /[^\x00-\x7F]/.test(input) && /ignore|instructions/i.test(input)

    const stages = [
      { stage: 'rate-limit', order: 1, passed: true, action: 'ALLOW', durationMs: 1, reason: null, category: null },
      { stage: 'unicode-normalization', order: 2, passed: !hasHomograph, action: hasHomograph ? 'BLOCK' : 'ALLOW', durationMs: 2, reason: hasHomograph ? 'Mixed-script homograph detected' : null, category: hasHomograph ? 'UNICODE' : null },
      { stage: 'injection-detection', order: 3, passed: !hasInjection, action: hasInjection ? 'BLOCK' : 'ALLOW', durationMs: 14, reason: hasInjection ? 'Prompt override pattern detected' : null, category: hasInjection ? 'INJECTION' : null },
      { stage: 'rule-classification', order: 4, passed: true, action: 'ALLOW', durationMs: 3, reason: null, category: null },
      { stage: 'llm-classification', order: 5, passed: true, action: 'SKIP', durationMs: 0, reason: 'Stage disabled', category: null },
      { stage: 'topic-drift', order: 6, passed: true, action: 'ALLOW', durationMs: 8, reason: null, category: null },
      { stage: 'permission', order: 7, passed: true, action: 'ALLOW', durationMs: 1, reason: null, category: null },
    ]

    const blockingStage = stages.find((s) => !s.passed)
    const totalMs = stages.reduce((sum, s) => sum + s.durationMs, 0)

    return HttpResponse.json({
      passed: !blockingStage,
      totalDurationMs: totalMs,
      finalAction: blockingStage ? 'BLOCK' : 'ALLOW',
      blockingStage: blockingStage?.stage ?? null,
      stageResults: isLong ? stages.map((s, i) => i === 0 ? { ...s, durationMs: 45, reason: 'Large payload processing', category: 'PERFORMANCE' } : s) : stages,
    })
  }),
]

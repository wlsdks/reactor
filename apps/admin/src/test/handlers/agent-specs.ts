import { http, HttpResponse } from 'msw'
import type { AgentSpec } from '../../features/reactor-universe/types'

const systemPrompts: Record<string, string | null> = {
  'agent-spec-support': '고객의 질문에 필요한 근거를 먼저 확인하고, 확인할 수 없는 내용은 추측하지 않습니다.',
  'agent-spec-operations': '운영 상태와 변경 이력을 함께 확인한 뒤, 다음 조치와 확인 방법을 간단히 안내합니다.',
}

export const mockAgentSpecs: AgentSpec[] = [
  {
    id: 'agent-spec-support',
    name: '고객 문의 담당',
    description: '고객 문의의 근거를 확인하고 답변을 준비합니다.',
    toolNames: ['rag_search', 'ticket_lookup'],
    keywords: ['문의', '환불', '배송', '계정'],
    systemPromptPreview: '고객의 질문에 필요한 근거를 먼저 확인하고…',
    hasSystemPrompt: true,
    mode: 'REACT',
    independentExecution: true,
    enabled: true,
    createdAt: '2026-07-11T01:00:00Z',
    updatedAt: '2026-07-12T01:00:00Z',
  },
  {
    id: 'agent-spec-operations',
    name: '운영 점검 담당',
    description: '운영 상태를 확인하고 필요한 다음 조치를 안내합니다.',
    toolNames: ['release_readiness', 'audit_lookup', 'trace_lookup'],
    keywords: ['배포', '점검', '오류', '운영'],
    systemPromptPreview: '운영 상태와 변경 이력을 함께 확인한 뒤…',
    hasSystemPrompt: true,
    mode: 'PLAN_EXECUTE',
    independentExecution: false,
    enabled: true,
    createdAt: '2026-07-10T01:00:00Z',
    updatedAt: '2026-07-12T02:00:00Z',
  },
]

function findAgentSpec(id: string): AgentSpec | undefined {
  return mockAgentSpecs.find((agentSpec) => agentSpec.id === id)
}

export const agentSpecsHandlers = [
  http.get('/api/admin/agent-specs', () => HttpResponse.json(mockAgentSpecs)),

  http.get('/api/admin/agent-specs/:id/system-prompt', ({ params }) => {
    const id = String(params.id)
    if (!findAgentSpec(id)) {
      return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    }
    return HttpResponse.json({ systemPrompt: systemPrompts[id] ?? null })
  }),

  http.get('/api/admin/agent-specs/:id', ({ params }) => {
    const agentSpec = findAgentSpec(String(params.id))
    return agentSpec
      ? HttpResponse.json(agentSpec)
      : HttpResponse.json({ error: 'Not found' }, { status: 404 })
  }),

  http.post('/api/admin/agent-specs', async ({ request }) => {
    const body = await request.json() as Partial<AgentSpec> & { systemPrompt?: string | null }
    const systemPrompt = body.systemPrompt?.trim() || null
    const agentSpec: AgentSpec = {
      id: 'agent-spec-new',
      name: body.name ?? '',
      description: body.description ?? '',
      toolNames: body.toolNames ?? [],
      keywords: body.keywords ?? [],
      systemPromptPreview: systemPrompt ? `${systemPrompt.slice(0, 48)}…` : null,
      hasSystemPrompt: systemPrompt !== null,
      mode: body.mode ?? 'REACT',
      independentExecution: body.independentExecution ?? true,
      enabled: body.enabled ?? true,
      createdAt: '2026-07-13T01:00:00Z',
      updatedAt: '2026-07-13T01:00:00Z',
    }
    return HttpResponse.json(agentSpec, { status: 201 })
  }),

  http.put('/api/admin/agent-specs/:id', async ({ params, request }) => {
    const current = findAgentSpec(String(params.id))
    if (!current) {
      return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    }
    const body = await request.json() as Partial<AgentSpec>
    return HttpResponse.json({
      ...current,
      ...body,
      updatedAt: '2026-07-13T01:00:00Z',
    })
  }),

  http.delete('/api/admin/agent-specs/:id', ({ params }) => {
    return findAgentSpec(String(params.id))
      ? new HttpResponse(null, { status: 204 })
      : HttpResponse.json({ error: 'Not found' }, { status: 404 })
  }),
]

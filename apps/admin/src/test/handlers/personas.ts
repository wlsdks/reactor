import { http, HttpResponse } from 'msw'

export const mockPersonas = [
  {
    id: 'persona-1',
    name: 'Support Bot',
    description: 'Customer support assistant',
    systemPrompt: 'You are a helpful support assistant.',
    responseGuideline: null,
    welcomeMessage: null,
    promptTemplateId: null,
    icon: '🤖',
    isDefault: true,
    isActive: true,
    status: 'ACTIVE',
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-02T00:00:00Z',
  },
  {
    id: 'persona-2',
    name: 'Sales Bot',
    description: 'Sales assistant',
    systemPrompt: 'You are a helpful sales assistant.',
    responseGuideline: null,
    welcomeMessage: null,
    promptTemplateId: 'template-sales',
    icon: '📣',
    isDefault: false,
    isActive: true,
    status: 'ACTIVE',
    createdAt: '2024-01-03T00:00:00Z',
    updatedAt: '2024-01-04T00:00:00Z',
  },
]

function getMockPersonas() {
  return [
    {
      ...mockPersonas[0],
      name: '고객 지원 봇',
      description: '고객 지원 어시스턴트',
      systemPrompt: '당신은 친절한 고객 지원 어시스턴트입니다.',
    },
    {
      ...mockPersonas[1],
      name: '영업 봇',
      description: '영업 어시스턴트',
      systemPrompt: '당신은 친절한 영업 어시스턴트입니다.',
    },
  ]
}

export const personasHandlers = [
  http.get('/api/personas', () => {
    return HttpResponse.json(getMockPersonas())
  }),

  http.get('/api/personas/:id', ({ params }) => {
    const personas = getMockPersonas()
    const persona = personas.find(p => p.id === params.id)
    if (!persona) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json(persona)
  }),

  http.post('/api/personas', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json(
      {
        id: 'persona-new',
        ...body,
        status: 'ACTIVE',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
      { status: 201 },
    )
  }),

  http.put('/api/personas/:id', async ({ params, request }) => {
    const body = await request.json() as Record<string, unknown>
    const personas = getMockPersonas()
    const persona = personas.find(p => p.id === params.id)
    if (!persona) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json({ ...persona, ...body, updatedAt: new Date().toISOString() })
  }),

  http.delete('/api/personas/:id', ({ params }) => {
    const personas = getMockPersonas()
    const persona = personas.find(p => p.id === params.id)
    if (!persona) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return new HttpResponse(null, { status: 204 })
  }),
]

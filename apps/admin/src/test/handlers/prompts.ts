import { http, HttpResponse } from 'msw'

export const mockPromptTemplates = [
  {
    id: 'template-sales',
    name: 'Sales Assistant Prompt',
    description: 'Sales-facing versioned prompt',
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-02T00:00:00Z',
  },
  {
    id: 'template-support',
    name: 'Support Prompt v2',
    description: 'Customer support versioned prompt with empathy guidelines',
    createdAt: '2024-01-05T00:00:00Z',
    updatedAt: '2024-01-10T00:00:00Z',
  },
]

function getMockPromptTemplates() {
  return [
    {
      ...mockPromptTemplates[0],
      name: '영업 어시스턴트 프롬프트',
      description: '영업용 버전 관리 프롬프트',
    },
    {
      ...mockPromptTemplates[1],
      name: '고객 지원 프롬프트',
      description: '공감 가이드라인이 포함된 고객 지원 버전 관리 프롬프트',
    },
  ]
}

export const promptsHandlers = [
  http.get('/api/prompt-templates', () => {
    return HttpResponse.json(getMockPromptTemplates())
  }),

  http.get('/api/prompt-templates/:id', ({ params }) => {
    const templates = getMockPromptTemplates()
    const template = templates.find(item => item.id === params.id)
    if (!template) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json({
      ...template,
      activeVersion: {
        id: 'version-1',
        templateId: template.id,
        version: 1,
        content: `${template.name}의 프롬프트 내용`,
        status: 'ACTIVE',
        changeLog: '최초 배포',
        createdAt: '2024-01-02T00:00:00Z',
      },
      versions: [],
    })
  }),
]

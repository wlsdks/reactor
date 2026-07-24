import { http, HttpResponse } from 'msw'
import { NOW, DAY, HOUR } from './shared'

const iso = (value: number) => new Date(value).toISOString()

export const mockDebugReplayCaptures = [
  {
    id: 'capture-timeout-001',
    tenantId: 'default',
    userHash: 'user_71f21c88',
    capturedAt: iso(NOW - 2 * HOUR),
    userPrompt: '지난주 고객 문의 가운데 배송 지연 사례를 요약해 주세요.',
    errorCode: 'MODEL_TIMEOUT',
    errorMessage: 'model response exceeded the configured timeout',
    modelId: 'gpt-5.1',
    toolsAttempted: 'search_documents',
    expiresAt: iso(NOW + 7 * DAY),
  },
  {
    id: 'capture-tool-002',
    tenantId: 'default',
    userHash: 'user_229ad135',
    capturedAt: iso(NOW - 6 * HOUR),
    userPrompt: '오늘 처리하지 못한 Jira 작업을 담당자별로 정리해 주세요.',
    errorCode: 'TOOL_ERROR',
    errorMessage: 'jira search connection was unavailable',
    modelId: 'gpt-5.1',
    toolsAttempted: 'atlassian:jira_search',
    expiresAt: iso(NOW + 7 * DAY),
  },
  {
    id: 'capture-guard-003',
    tenantId: 'default',
    userHash: 'user_8cbfc650',
    capturedAt: iso(NOW - DAY),
    userPrompt: '제한된 문서의 원문을 그대로 보여 주세요.',
    errorCode: 'GUARD_BLOCKED',
    errorMessage: 'request blocked by output policy',
    modelId: 'gpt-5.1',
    toolsAttempted: null,
    expiresAt: iso(NOW + 6 * DAY),
  },
]

export const debugReplayHandlers = [
  http.get('/api/admin/debug/replay', () => HttpResponse.json(mockDebugReplayCaptures)),
  http.get('/api/admin/debug/replay/:id', ({ params }) => {
    const capture = mockDebugReplayCaptures.find((item) => item.id === params.id)
    return capture
      ? HttpResponse.json(capture)
      : HttpResponse.json({ message: 'capture not found' }, { status: 404 })
  }),
]

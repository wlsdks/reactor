import { http, HttpResponse } from 'msw'

export const mockApprovals = [
  {
    id: 'approval-1',
    toolName: 'web_search',
    status: 'PENDING',
    runId: 'run-1',
    requestedAt: '2024-01-01T10:00:00Z',
    arguments: { query: 'test search' },
  },
  {
    id: 'approval-2',
    toolName: 'jira_create_issue',
    status: 'PENDING',
    runId: 'run-2',
    requestedAt: '2024-01-02T14:30:00Z',
    arguments: { project: 'DEMO', summary: 'Fix login timeout', type: 'Bug' },
  },
  {
    id: 'approval-3',
    toolName: 'confluence_update_page',
    status: 'APPROVED',
    runId: 'run-3',
    requestedAt: '2024-01-01T09:00:00Z',
    arguments: { pageId: 'page-123', title: 'API Migration Guide' },
  },
]

function getMockApprovals() {
  return [
    {
      ...mockApprovals[0],
      arguments: { query: '테스트 검색' },
    },
    {
      ...mockApprovals[1],
      arguments: { project: 'DEMO', summary: '로그인 타임아웃 수정', type: '버그' },
    },
    {
      ...mockApprovals[2],
      arguments: { pageId: 'page-123', title: 'API 마이그레이션 가이드' },
    },
  ]
}

export const approvalsHandlers = [
  http.get('/api/approvals', () => {
    return HttpResponse.json(getMockApprovals())
  }),

  http.post('/api/approvals/:id/approve', () => {
    return HttpResponse.json({ id: 'approval-1', status: 'APPROVED' })
  }),

  http.post('/api/approvals/:id/reject', () => {
    return HttpResponse.json({ id: 'approval-1', status: 'REJECTED' })
  }),
]

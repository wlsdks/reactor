import { http, HttpResponse } from 'msw'

const success = (ingested: number) => HttpResponse.json({
  success: true,
  ingested,
  message: '검증용 진단 데이터를 기록했습니다.',
})

export const metricIngestionHandlers = [
  http.post('/api/admin/metrics/ingest/mcp-health', () => success(1)),
  http.post('/api/admin/metrics/ingest/tool-call', () => success(1)),
  http.post('/api/admin/metrics/ingest/eval-result', () => success(1)),
  http.post('/api/admin/metrics/ingest/eval-results', () => success(2)),
  http.post('/api/admin/metrics/ingest/batch', async ({ request }) => {
    const body: unknown = await request.json()
    return success(Array.isArray(body) ? body.length : 0)
  }),
]

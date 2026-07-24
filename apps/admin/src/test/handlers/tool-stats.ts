import { http, HttpResponse } from 'msw'

export const mockToolStats = {
  total: 100,
  accuracy: 0.85,
  byOutcome: { ok: 80, error: 15, timeout: 5 },
  byServer: { 'mcp-a': 63, 'mcp-b': 37 },
  byTool: [
    { tool: 'web.search', server: 'mcp-a', outcome: 'ok', count: 40 },
    { tool: 'web.search', server: 'mcp-a', outcome: 'error', count: 10 },
    { tool: 'web.search', server: 'mcp-b', outcome: 'ok', count: 20 },
    { tool: 'fs.read', server: 'mcp-b', outcome: 'ok', count: 30 },
  ],
}

export const mockToolAccuracy = {
  total: 100,
  ok: 85,
  accuracy: 0.85,
  invalidCallRate: 0.02,
  timeoutRate: 0.05,
  notFoundRate: 0.08,
}

export const toolStatsHandlers = [
  http.get('/api/admin/tools/stats', () => HttpResponse.json(mockToolStats)),
  http.get('/api/admin/tools/accuracy', () => HttpResponse.json(mockToolAccuracy)),
]

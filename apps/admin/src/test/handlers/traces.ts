import { http, HttpResponse } from 'msw'
import { NOW, HOUR } from './shared'

function makeSpan(index: number, traceId: string, isError: boolean, isBlocked: boolean) {
  const models = ['claude-sonnet-4-20250514', 'claude-haiku-35-20241022', 'claude-opus-4-20250514']
  const baseDuration = 800 + index * 200

  return [
    {
      span_id: `${traceId}_span_1`,
      parent_span_id: null,
      operation_name: 'request',
      service_name: 'reactor',
      duration_ms: baseDuration,
      success: !isError && !isBlocked,
      error_class: null,
      attributes: { method: 'POST', path: '/api/chat' },
      time: NOW - (index + 1) * HOUR,
    },
    {
      span_id: `${traceId}_span_2`,
      parent_span_id: `${traceId}_span_1`,
      operation_name: 'content-filter',
      service_name: 'input-guard',
      duration_ms: 45,
      success: !isBlocked,
      error_class: isBlocked ? 'BlockedByGuard' : null,
      attributes: {
        action: isBlocked ? 'block' : 'allow',
        matchedRule: isBlocked ? 'pii-detection' : 'none',
        confidence: isBlocked ? 0.92 : 0.05,
      },
      time: NOW - (index + 1) * HOUR + 10,
    },
    {
      span_id: `${traceId}_span_3`,
      parent_span_id: `${traceId}_span_1`,
      operation_name: `llm:${models[index % 3]}`,
      service_name: 'llm-router',
      duration_ms: baseDuration - 200,
      success: !isError,
      error_class: isError ? 'LLM_TIMEOUT' : null,
      attributes: {
        model: models[index % 3],
        inputTokens: 150 + index * 50,
        outputTokens: 300 + index * 80,
        costUsd: 0.002 + index * 0.001,
        stopReason: isError ? 'error' : 'end_turn',
      },
      time: NOW - (index + 1) * HOUR + 60,
    },
    {
      span_id: `${traceId}_span_4`,
      parent_span_id: `${traceId}_span_3`,
      operation_name: 'tool:jira_search',
      service_name: 'mcp-bridge',
      duration_ms: 180 + index * 30,
      success: !(isError && index === 7),
      error_class: isError && index === 7 ? 'ConnectionTimeout' : null,
      attributes: {
        toolName: 'jira_search',
        mcpServer: 'atlassian-mcp',
        args: { query: 'open bugs', project: 'DEMO' },
        result: isError && index === 7 ? null : { count: 5, issues: ['DEMO-101', 'DEMO-102'] },
        error: isError && index === 7 ? 'Connection timeout' : null,
      },
      time: NOW - (index + 1) * HOUR + 120,
    },
  ]
}

function makeTrace(index: number) {
  const traceId = `trace_${String(index + 1).padStart(3, '0')}`
  const isError = index === 2 || index === 7
  const isBlocked = index === 5
  const baseDuration = 800 + index * 200

  return {
    trace_id: traceId,
    time: NOW - (index + 1) * HOUR,
    total_duration_ms: baseDuration,
    span_count: 4,
    success: !isError && !isBlocked,
    run_id: `run_${(index % 5) + 1}`,
  }
}

const mockTraceList = Array.from({ length: 10 }, (_, i) => makeTrace(i))

export const mockTraces = mockTraceList

export const tracesHandlers = [
  http.get('/api/admin/traces', ({ request }) => {
    const url = new URL(request.url)
    const statusFilter = url.searchParams.get('status')
    const limit = Number(url.searchParams.get('limit') ?? 50)

    let filtered = mockTraceList
    if (statusFilter === 'error') {
      filtered = filtered.filter((t) => !t.success)
    }

    return HttpResponse.json(filtered.slice(0, limit))
  }),

  http.get('/api/admin/traces/:traceId/spans', ({ params }) => {
    const traceId = params.traceId as string
    const trace = mockTraceList.find((t) => t.trace_id === traceId)
    if (!trace) {
      return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    }
    const index = mockTraceList.indexOf(trace)
    const isError = index === 2 || index === 7
    const isBlocked = index === 5
    return HttpResponse.json(makeSpan(index, traceId, isError, isBlocked))
  }),

  http.get('/api/admin/tool-calls', () => {
    return HttpResponse.json([
      {
        run_id: 'run_1',
        tool_name: 'jira_search',
        tool_source: 'mcp',
        mcp_server_name: 'atlassian-mcp',
        success: true,
        duration_ms: 210,
        error_class: null,
        error_message: null,
        time: NOW - HOUR,
        call_index: 0,
      },
    ])
  }),

  http.get('/api/admin/tool-calls/ranking', () => {
    return HttpResponse.json([
      {
        tool_name: 'jira_search',
        call_count: 150,
        success_count: 140,
        avg_duration_ms: 200,
        p95_duration_ms: 450,
      },
    ])
  }),
]

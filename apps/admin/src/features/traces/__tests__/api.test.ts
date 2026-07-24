import { describe, it, expect, vi, afterEach } from 'vitest'
import { listTraces, getTraceSpans, listToolCalls, getToolCallRanking } from '../api'

const mockApiGet = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

describe('traces api', () => {
  afterEach(() => {
    mockApiGet.mockReset()
  })

  describe('listTraces', () => {
    it('GETs admin/traces with default limit when no params', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([]))
      await listTraces()
      expect(mockApiGet).toHaveBeenCalledWith('admin/traces', { searchParams: { limit: 200 } })
    })

    it('passes through custom limit, days, status', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([]))
      await listTraces({ limit: 200, days: 7, status: 'ERROR' })
      expect(mockApiGet).toHaveBeenCalledWith('admin/traces', {
        searchParams: { limit: 200, days: 7, status: 'ERROR' },
      })
    })

    it('omits days when undefined and omits status when empty', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([]))
      await listTraces({ limit: 10 })
      expect(mockApiGet).toHaveBeenCalledWith('admin/traces', { searchParams: { limit: 10 } })
    })

    it('normalizes the current status/duration response into the trace view contract', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([{
        trace_id: 't1',
        run_id: 'run_1',
        status: 'completed',
        created_at: 1,
        duration_ms: 24,
      }]))
      const result = await listTraces()
      expect(result).toEqual([{
        traceId: 't1',
        runId: 'run_1',
        time: 1,
        totalDurationMs: 24,
        spanCount: 0,
        success: true,
      }])
    })

    it('fails closed on malformed numeric fields and drops rows without a trace id', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([
        { trace_id: 'failed', status: 'failed', duration_ms: 'bad', created_at: null },
        { status: 'completed', duration_ms: 12 },
      ]))

      expect(await listTraces()).toEqual([{
        traceId: 'failed',
        runId: 'failed',
        time: 0,
        totalDurationMs: 0,
        spanCount: 0,
        success: false,
      }])
    })
  })

  describe('getTraceSpans', () => {
    it('GETs admin/traces/{id}/spans', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([]))
      await getTraceSpans('t-123')
      expect(mockApiGet).toHaveBeenCalledWith('admin/traces/t-123/spans')
    })

    it('normalizes current trace events into safe drawer steps', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([{
        trace_id: 't-1',
        sequence: 1,
        event_type: 'run.created',
        graph_node: null,
        payload: { queue_id: 'queue_1' },
      }]))
      const result = await getTraceSpans('t-1')
      expect(result).toEqual([{
        spanId: 't-1:1',
        parentSpanId: null,
        operationName: '실행 시작',
        serviceName: 'Reactor',
        durationMs: 0,
        success: true,
        errorClass: null,
        attributes: { queueId: 'queue_1' },
        time: 1,
      }])
    })

    it('does not expose an unknown event key as the primary operation label', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([{
        trace_id: 't-1',
        sequence: 1,
        event_type: 'graph.internal_retry',
        graph_node: null,
        payload: {},
      }]))

      await expect(getTraceSpans('t-1')).resolves.toEqual([expect.objectContaining({
        operationName: '확인할 수 없는 실행 단계',
      })])
    })

    it('preserves legacy span fields while failing closed on invalid numbers', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([{
        span_id: 's1',
        parent_span_id: null,
        operation_name: 'tool:search',
        service_name: 'worker',
        duration_ms: 'bad',
        success: false,
        error_class: 'TimeoutError',
        attributes: { tool_name: 'search' },
        time: 12,
      }]))

      expect(await getTraceSpans('t-1')).toEqual([expect.objectContaining({
        spanId: 's1',
        operationName: 'tool:search',
        durationMs: 0,
        success: false,
        errorClass: 'TimeoutError',
      })])
    })
  })

  describe('listToolCalls', () => {
    it('GETs admin/tool-calls with default limit when no args', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([]))
      await listToolCalls()
      expect(mockApiGet).toHaveBeenCalledWith('admin/tool-calls', { searchParams: { limit: 200 } })
    })

    it('passes through runId, days, limit when provided', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([]))
      await listToolCalls('run-1', 14, 25)
      expect(mockApiGet).toHaveBeenCalledWith('admin/tool-calls', {
        searchParams: { limit: 25, runId: 'run-1', days: 14 },
      })
    })
  })

  describe('getToolCallRanking', () => {
    it('GETs admin/tool-calls/ranking with no params by default', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([]))
      await getToolCallRanking()
      expect(mockApiGet).toHaveBeenCalledWith('admin/tool-calls/ranking', { searchParams: {} })
    })

    it('passes through days when provided', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([]))
      await getToolCallRanking(30)
      expect(mockApiGet).toHaveBeenCalledWith('admin/tool-calls/ranking', { searchParams: { days: 30 } })
    })
  })
})

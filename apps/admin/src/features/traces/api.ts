import { api } from '../../shared/api/client'
import { snakeToCamel } from '../../shared/lib/caseTransform'
import type { TraceListItem, TraceListParams, TraceSpan, ToolCallEntry, ToolCallRanking } from './types'

function finiteNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function normalizedSuccess(value: unknown, status: unknown): boolean {
  if (typeof value === 'boolean') return value
  const normalized = typeof status === 'string' ? status.trim().toLowerCase() : ''
  return ['completed', 'passed', 'success', 'succeeded'].includes(normalized)
}

function normalizeTraceListItem(value: unknown): TraceListItem | null {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const traceId = typeof row.traceId === 'string' ? row.traceId.trim() : ''
  if (!traceId) return null

  return {
    traceId,
    runId: typeof row.runId === 'string' && row.runId.trim() ? row.runId : traceId,
    time: finiteNumber(row.time ?? row.createdAt),
    totalDurationMs: finiteNumber(row.totalDurationMs ?? row.durationMs),
    spanCount: finiteNumber(row.spanCount),
    success: normalizedSuccess(row.success, row.status),
  }
}

function eventOperationName(value: unknown): string {
  if (typeof value !== 'string') return '실행 이벤트'
  const labels: Record<string, string> = {
    'run.created': '실행 시작',
    'run.completed': '실행 완료',
    'run.failed': '실행 실패',
  }
  return labels[value] ?? '확인할 수 없는 실행 단계'
}

function normalizeTraceSpan(value: unknown, index: number): TraceSpan | null {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const eventType = typeof row.eventType === 'string' ? row.eventType : ''
  const payload = row.payload && typeof row.payload === 'object'
    ? row.payload as Record<string, unknown>
    : {}
  const traceId = typeof row.traceId === 'string' ? row.traceId : 'trace'
  const sequence = finiteNumber(row.sequence) || index + 1
  const operationName = typeof row.operationName === 'string' && row.operationName.trim()
    ? row.operationName
    : eventOperationName(eventType)
  const payloadStatus = typeof payload.status === 'string' ? payload.status : ''
  const successful = row.success === undefined
    ? !eventType.toLowerCase().includes('fail') && payloadStatus.toLowerCase() !== 'failed'
    : normalizedSuccess(row.success, row.status)

  return {
    spanId: typeof row.spanId === 'string' && row.spanId.trim()
      ? row.spanId
      : `${traceId}:${sequence}`,
    parentSpanId: typeof row.parentSpanId === 'string' ? row.parentSpanId : null,
    operationName,
    serviceName: typeof row.serviceName === 'string' ? row.serviceName : 'Reactor',
    durationMs: finiteNumber(row.durationMs),
    success: successful,
    errorClass: typeof row.errorClass === 'string'
      ? row.errorClass
      : typeof payload.error === 'string'
        ? payload.error
        : null,
    attributes: row.attributes && typeof row.attributes === 'object'
      ? row.attributes as Record<string, unknown>
      : payload,
    time: finiteNumber(row.time ?? row.createdAt ?? sequence),
  }
}

export const listTraces = async (params?: TraceListParams): Promise<TraceListItem[]> => {
  const searchParams: Record<string, string | number> = { limit: params?.limit ?? 200 }
  if (params?.days != null) searchParams.days = params.days
  if (params?.status) searchParams.status = params.status
  const raw = await api.get('admin/traces', { searchParams }).json()
  const normalized = snakeToCamel(raw)
  if (!Array.isArray(normalized)) return []
  return normalized.flatMap((item) => {
    const trace = normalizeTraceListItem(item)
    return trace ? [trace] : []
  })
}

export const getTraceSpans = async (traceId: string): Promise<TraceSpan[]> => {
  const raw = await api.get(`admin/traces/${traceId}/spans`).json()
  const normalized = snakeToCamel(raw)
  if (!Array.isArray(normalized)) return []
  return normalized.flatMap((item, index) => {
    const span = normalizeTraceSpan(item, index)
    return span ? [span] : []
  })
}

export const listToolCalls = async (
  runId?: string,
  days?: number,
  limit?: number,
): Promise<ToolCallEntry[]> => {
  const searchParams: Record<string, string | number> = { limit: limit ?? 200 }
  if (runId) searchParams.runId = runId
  if (days != null) searchParams.days = days
  const raw = await api.get('admin/tool-calls', { searchParams }).json()
  return snakeToCamel(raw) as ToolCallEntry[]
}

export const getToolCallRanking = async (days?: number): Promise<ToolCallRanking[]> => {
  const searchParams: Record<string, string | number> = {}
  if (days != null) searchParams.days = days
  const raw = await api.get('admin/tool-calls/ranking', { searchParams }).json()
  return snakeToCamel(raw) as ToolCallRanking[]
}

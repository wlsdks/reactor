/** Trace list query parameters matching the backend API. */
export interface TraceListParams {
  days?: number
  limit?: number
  status?: string
}

/** A single trace in the list response. */
export interface TraceListItem {
  traceId: string
  time: number
  totalDurationMs: number
  spanCount: number
  success: boolean
  runId: string
}

/** A single span inside a trace detail response. */
export interface TraceSpan {
  spanId: string
  parentSpanId: string | null
  operationName: string
  serviceName: string
  durationMs: number
  success: boolean
  errorClass: string | null
  attributes: Record<string, unknown>
  time: number
}

/** Tool call entry from GET /api/admin/tool-calls */
export interface ToolCallEntry {
  runId: string
  toolName: string
  toolSource: string
  mcpServerName: string | null
  success: boolean
  durationMs: number
  errorClass: string | null
  errorMessage: string | null
  time: number
  callIndex: number
}

/** Tool call ranking from GET /api/admin/tool-calls/ranking */
export interface ToolCallRanking {
  toolName: string
  callCount: number
  successCount: number
  avgDurationMs: number
  p95DurationMs: number
}

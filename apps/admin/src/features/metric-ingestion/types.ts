export interface McpHealthRequest {
  tenantId: string
  serverName: string
  status?: string
  responseTimeMs?: number
  errorClass?: string
  errorMessage?: string
  toolCount?: number
}

export interface ToolCallRequest {
  tenantId: string
  runId: string
  toolName: string
  toolSource?: string
  mcpServerName?: string
  callIndex?: number
  success?: boolean
  durationMs?: number
  errorClass?: string
  errorMessage?: string
}

export interface EvalResultRequest {
  tenantId: string
  evalRunId: string
  testCaseId: string
  pass: boolean
  score?: number
  latencyMs?: number
  tokenUsage?: number
  cost?: number
  assertionType?: string
  failureClass?: string
  failureDetail?: string
  tags?: string[]
}

export interface EvalTestCaseResult {
  testCaseId: string
  pass: boolean
  score?: number
  latencyMs?: number
  tokenUsage?: number
  cost?: number
  assertionType?: string
  failureClass?: string
  failureDetail?: string
  tags?: string[]
}

export interface EvalRunResultsRequest {
  tenantId: string
  evalRunId: string
  results: EvalTestCaseResult[]
}

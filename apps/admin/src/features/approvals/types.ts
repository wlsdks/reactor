export interface ApprovalSummary {
  id: string
  runId: string
  toolName: string
  requestedAt: string
  requestedBy: string
  decidedAt: string | null
  decidedBy: string | null
  decisionReason: string | null
  riskLevel: string | null
  timeoutMs: number | null
  idempotencyKey: string | null
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'TIMED_OUT' | 'CANCELLED'
}

export interface ApprovalActionResponse {
  id: string
  success: boolean
  message: string
  status: string
}

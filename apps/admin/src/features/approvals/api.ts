import type { ApprovalSummary, ApprovalActionResponse } from './types'
import { api } from '../../shared/api/client'

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function optionalText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

function normalizeStatus(value: unknown): ApprovalSummary['status'] {
  switch (text(value).toLowerCase()) {
    case 'approved': return 'APPROVED'
    case 'rejected': return 'REJECTED'
    case 'expired': return 'TIMED_OUT'
    case 'cancelled': return 'CANCELLED'
    default: return 'PENDING'
  }
}

function backendStatus(value: string): string {
  return value === 'TIMED_OUT' ? 'expired' : value.toLowerCase()
}

export function parseApproval(data: unknown): ApprovalSummary {
  const row = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>
  const payload = row.request_payload && typeof row.request_payload === 'object'
    ? row.request_payload as Record<string, unknown>
    : {}
  return {
    id: text(row.approval_id ?? row.id),
    runId: text(row.run_id ?? row.runId),
    toolName: text(row.tool_id ?? row.toolName ?? payload.tool_id),
    requestedAt: text(row.requested_at ?? row.requestedAt ?? row.createdAt),
    requestedBy: text(row.requested_by ?? row.requestedBy ?? payload.requested_by),
    decidedAt: optionalText(row.decided_at ?? row.decidedAt),
    decidedBy: optionalText(row.decided_by ?? row.decidedBy),
    decisionReason: optionalText(row.decision_reason ?? row.decisionReason),
    riskLevel: optionalText(payload.tool_risk_level),
    timeoutMs: typeof payload.tool_timeout_ms === 'number' ? payload.tool_timeout_ms : null,
    idempotencyKey: optionalText(payload.idempotency_key),
    status: normalizeStatus(row.status),
  }
}

export const listAllApprovals = async (status?: string): Promise<ApprovalSummary[]> => {
  const searchParams: Record<string, string | number> = { limit: 200 }
  if (status) searchParams.status = backendStatus(status)
  const data = await api.get('approvals', { searchParams }).json<unknown>()
  const items = Array.isArray(data)
    ? data
    : data && typeof data === 'object' && Array.isArray((data as { items?: unknown }).items)
      ? (data as { items: unknown[] }).items
      : []
  return items.map(parseApproval)
}

async function decision(path: string, reason?: string): Promise<ApprovalActionResponse> {
  const data = await api.post(path, { json: reason ? { reason } : {} }).json<Record<string, unknown>>()
  return {
    id: text(data.approval_id ?? data.id),
    success: true,
    message: '',
    status: text(data.status),
  }
}

export const approveToolCall = (id: string): Promise<ApprovalActionResponse> =>
  decision(`approvals/${id}/approve`)

export const rejectToolCall = (id: string, reason?: string): Promise<ApprovalActionResponse> =>
  decision(`approvals/${id}/reject`, reason)

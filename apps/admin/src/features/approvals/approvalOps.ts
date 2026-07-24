import { summarizeStatus, classifyLoadIssue, type OpsStatus, type LoadIssue } from '../../shared/lib/ops'
import type { ApprovalSummary } from './types'

/**
 * Severity ordering used to surface the most actionable signals first across
 * the approvals console (readiness checks, attention queue). Lower number =
 * more urgent. Sorts that consume this map should remain stable so items with
 * the same severity preserve their original (e.g. age-based) ordering.
 */
export const APPROVAL_SEVERITY_ORDER: Record<OpsStatus, number> = {
  FAIL: 0, // critical
  WARN: 1, // warning
  PASS: 2, // info / healthy
}

export interface ApprovalSignal {
  id: 'approvalContract' | 'pendingQueue' | 'timeoutDebt' | 'payloadCoverage'
  status: OpsStatus
  detailId:
    | 'contractHealthy'
    | 'contractMissing'
    | 'contractDenied'
    | 'contractTransport'
    | 'contractError'
    | 'pendingQueueClear'
    | 'pendingQueueActive'
    | 'timeoutDebtClear'
    | 'timeoutDebtPresent'
    | 'payloadCoverageReady'
    | 'payloadCoverageMissing'
  meta?: {
    count?: number
    total?: number
  }
}

export interface ApprovalAttentionItem {
  id: string
  approval: ApprovalSummary
  kind: 'timedOut' | 'stalePending' | 'pending'
  status: OpsStatus
  ageMinutes: number
  detailId: 'approvalTimedOut' | 'pendingTooLong' | 'pendingReview'
}

export interface ApprovalOpsSummary {
  status: OpsStatus
  loadIssue: LoadIssue | null
  totalApprovals: number
  pendingCount: number
  timedOutCount: number
  stalePendingCount: number
  attentionCount: number
  coveredCount: number
  oldestPendingMinutes: number | null
  signals: ApprovalSignal[]
  attentionItems: ApprovalAttentionItem[]
}

export type ApprovalQuickFilter =
  | 'all'
  | 'attention'
  | 'timedOut'
  | 'stalePending'
  | 'pendingReview'

function summarizeContractSignal(loadIssue: LoadIssue | null): ApprovalSignal {
  if (loadIssue === 'notAdvertised') {
    return { id: 'approvalContract', status: 'WARN', detailId: 'contractMissing' }
  }
  if (loadIssue === 'accessDenied') {
    return { id: 'approvalContract', status: 'FAIL', detailId: 'contractDenied' }
  }
  if (loadIssue === 'transportFailure') {
    return { id: 'approvalContract', status: 'FAIL', detailId: 'contractTransport' }
  }
  if (loadIssue === 'httpError') {
    return { id: 'approvalContract', status: 'FAIL', detailId: 'contractError' }
  }
  return { id: 'approvalContract', status: 'PASS', detailId: 'contractHealthy' }
}

function ageMinutes(requestedAt: string, now: number): number {
  const parsed = Date.parse(requestedAt)
  if (Number.isNaN(parsed)) return 0
  return Math.max(0, Math.floor((now - parsed) / 60000))
}

function buildAttentionItems(approvals: ApprovalSummary[], now: number): ApprovalAttentionItem[] {
  const items: ApprovalAttentionItem[] = []

  for (const approval of approvals) {
    const minutes = ageMinutes(approval.requestedAt, now)
    if (approval.status === 'TIMED_OUT') {
      items.push({
        id: `${approval.id}:timed-out`,
        approval,
        kind: 'timedOut',
        status: 'FAIL',
        ageMinutes: minutes,
        detailId: 'approvalTimedOut',
      })
      continue
    }
    if (approval.status !== 'PENDING') continue

    if (minutes >= 30) {
      items.push({
        id: `${approval.id}:stale`,
        approval,
        kind: 'stalePending',
        status: 'FAIL',
        ageMinutes: minutes,
        detailId: 'pendingTooLong',
      })
      continue
    }

    items.push({
      id: `${approval.id}:pending`,
      approval,
      kind: 'pending',
      status: 'WARN',
      ageMinutes: minutes,
      detailId: 'pendingReview',
    })
  }

  return items.sort((left, right) => {
    const severityDelta =
      APPROVAL_SEVERITY_ORDER[left.status] - APPROVAL_SEVERITY_ORDER[right.status]
    if (severityDelta !== 0) return severityDelta
    return right.ageMinutes - left.ageMinutes
  })
}

export function summarizeApprovalOps(
  approvals: ApprovalSummary[],
  loadError: string | null,
  now = Date.now(),
): ApprovalOpsSummary {
  const loadIssue = classifyLoadIssue(loadError)
  const contractSignal = summarizeContractSignal(loadIssue)
  const attentionItems = buildAttentionItems(approvals, now)
  const pendingCount = approvals.filter((approval) => approval.status === 'PENDING').length
  const timedOutCount = approvals.filter((approval) => approval.status === 'TIMED_OUT').length
  const stalePendingCount = attentionItems.filter((item) => item.kind === 'stalePending').length
  const coveredCount = approvals.filter((approval) => (
    approval.runId
    && approval.toolName
    && approval.requestedAt
    && approval.riskLevel
    && approval.timeoutMs != null
    && approval.idempotencyKey
  )).length
  const pendingItems = attentionItems.filter((item) => item.kind === 'pending' || item.kind === 'stalePending')
  const oldestPendingMinutes = pendingItems.length === 0
    ? null
    : Math.max(...pendingItems.map((item) => item.ageMinutes))

  const signals: ApprovalSignal[] = [
    contractSignal,
    pendingCount > 0
      ? {
          id: 'pendingQueue',
          status: stalePendingCount > 0 ? 'FAIL' : 'WARN',
          detailId: 'pendingQueueActive',
          meta: { count: pendingCount, total: approvals.length },
        }
      : {
          id: 'pendingQueue',
          status: 'PASS',
          detailId: 'pendingQueueClear',
        },
    timedOutCount > 0
      ? {
          id: 'timeoutDebt',
          status: 'FAIL',
          detailId: 'timeoutDebtPresent',
          meta: { count: timedOutCount },
        }
      : {
          id: 'timeoutDebt',
          status: 'PASS',
          detailId: 'timeoutDebtClear',
        },
    coveredCount === approvals.length
      ? {
          id: 'payloadCoverage',
          status: 'PASS',
          detailId: 'payloadCoverageReady',
          meta: { count: coveredCount, total: approvals.length },
        }
      : {
          id: 'payloadCoverage',
          status: 'WARN',
          detailId: 'payloadCoverageMissing',
          meta: { count: coveredCount, total: approvals.length },
        },
  ]

  return {
    status: summarizeStatus(signals),
    loadIssue,
    totalApprovals: approvals.length,
    pendingCount,
    timedOutCount,
    stalePendingCount,
    attentionCount: attentionItems.length,
    coveredCount,
    oldestPendingMinutes,
    signals,
    attentionItems,
  }
}

export function filterApprovals(
  approvals: ApprovalSummary[],
  attentionItems: ApprovalAttentionItem[],
  quickFilter: ApprovalQuickFilter,
): ApprovalSummary[] {
  if (quickFilter === 'all') return approvals

  const kindsByApprovalId = new Map<string, Set<ApprovalAttentionItem['kind']>>()
  for (const item of attentionItems) {
    const existing = kindsByApprovalId.get(item.approval.id) ?? new Set<ApprovalAttentionItem['kind']>()
    existing.add(item.kind)
    kindsByApprovalId.set(item.approval.id, existing)
  }

  return approvals.filter((approval) => {
    const kinds = kindsByApprovalId.get(approval.id)
    if (!kinds) return false

    switch (quickFilter) {
      case 'attention':
        return true
      case 'timedOut':
        return kinds.has('timedOut')
      case 'stalePending':
        return kinds.has('stalePending')
      case 'pendingReview':
        return kinds.has('pending')
      default:
        return true
    }
  })
}

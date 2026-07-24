import { describe, expect, it } from 'vitest'
import { classifyLoadIssue } from '../../../shared/lib/ops'
import { filterApprovals, summarizeApprovalOps } from '../approvalOps'
import type { ApprovalSummary } from '../types'

function buildApproval(overrides: Partial<ApprovalSummary> = {}): ApprovalSummary {
  return {
    id: 'approval-1',
    runId: 'run-1',
    toolName: 'jira_issue_transition',
    requestedAt: '2026-03-12T03:00:00.000Z',
    requestedBy: 'operator-1',
    decidedAt: null,
    decidedBy: null,
    decisionReason: null,
    riskLevel: 'external_side_effect',
    timeoutMs: 30000,
    idempotencyKey: 'approval-1',
    status: 'PENDING',
    ...overrides,
  }
}

describe('approvalOps', () => {
  it('classifies load failures for the recovery console', () => {
    expect(classifyLoadIssue('HTTP 404')).toBe('notAdvertised')
    expect(classifyLoadIssue('HTTP 401')).toBe('accessDenied')
    expect(classifyLoadIssue('empty reply from server')).toBe('transportFailure')
    expect(classifyLoadIssue('HTTP 500')).toBe('httpError')
  })

  it('flags pending and timed-out approvals as operator attention', () => {
    const summary = summarizeApprovalOps([
      buildApproval(),
      buildApproval({
        id: 'approval-2',
        status: 'TIMED_OUT',
      }),
      buildApproval({
        id: 'approval-3',
        status: 'APPROVED',
      }),
      buildApproval({
        id: 'approval-4',
        runId: '',
        riskLevel: null,
        status: 'REJECTED',
      }),
    ], null)

    expect(summary.status).toBe('FAIL')
    expect(summary.totalApprovals).toBe(4)
    expect(summary.pendingCount).toBe(1)
    expect(summary.timedOutCount).toBe(1)
    expect(summary.attentionCount).toBe(2)
    expect(summary.signals.find((signal) => signal.id === 'timeoutDebt')?.detailId).toBe('timeoutDebtPresent')
    expect(summary.signals.find((signal) => signal.id === 'payloadCoverage')?.detailId).toBe('payloadCoverageMissing')
  })

  it('filters approvals to the operator queue slices', () => {
    const approvals = [
      buildApproval({
        id: 'approval-stale',
        requestedAt: '2026-03-12T00:00:00.000Z',
        status: 'PENDING',
      }),
      buildApproval({
        id: 'approval-timed-out',
        toolName: 'confluence_write',
        status: 'TIMED_OUT',
      }),
      buildApproval({
        id: 'approval-pending',
        toolName: 'slack_post',
        requestedAt: '2026-03-12T02:50:00.000Z',
        status: 'PENDING',
      }),
      buildApproval({
        id: 'approval-approved',
        toolName: 'jira_comment',
        status: 'APPROVED',
      }),
    ]

    const summary = summarizeApprovalOps(approvals, null, Date.parse('2026-03-12T03:05:00.000Z'))

    expect(filterApprovals(approvals, summary.attentionItems, 'attention').map((approval) => approval.id)).toEqual([
      'approval-stale',
      'approval-timed-out',
      'approval-pending',
    ])
    expect(filterApprovals(approvals, summary.attentionItems, 'timedOut').map((approval) => approval.id)).toEqual([
      'approval-timed-out',
    ])
    expect(filterApprovals(approvals, summary.attentionItems, 'pendingReview').map((approval) => approval.id)).toEqual([
      'approval-pending',
    ])
  })
})

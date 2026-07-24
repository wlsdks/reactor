import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, i18n, render, screen, waitFor, within } from '../../../test/utils'
import { ApprovalsManager } from '../ui/ApprovalsManager'
import * as approvalsApi from '../api'
import type { ApprovalSummary } from '../types'

vi.mock('../api', () => ({
  listAllApprovals: vi.fn(),
  approveToolCall: vi.fn(),
  rejectToolCall: vi.fn(),
}))

const listAllApprovalsMock = vi.mocked(approvalsApi.listAllApprovals)

function buildApproval(overrides: Partial<ApprovalSummary> = {}): ApprovalSummary {
  return {
    id: 'approval-1',
    runId: 'run-1',
    toolName: 'jira_write',
    requestedAt: '2024-01-01T10:00:00Z',
    requestedBy: 'operator-1',
    decidedAt: null,
    decidedBy: null,
    decisionReason: null,
    riskLevel: 'write',
    timeoutMs: 30000,
    idempotencyKey: 'approval-1',
    status: 'PENDING',
    ...overrides,
  }
}

function renderManager() {
  return render(
    <MemoryRouter>
      <ApprovalsManager />
    </MemoryRouter>,
  )
}

describe('ApprovalsManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'nav.approvals': 'Approvals Queue',
      'nav.help.approvals': 'Review and resolve approval-gated actions.',
      'common.status': 'Status',
      'common.statuses.PENDING': 'Pending review',
      'common.statuses.APPROVED': 'Approved',
      'common.statuses.REJECTED': 'Rejected',
      'common.statuses.TIMED_OUT': 'Expired',
      'common.statuses.CANCELLED': 'Cancelled',
      'common.refresh': 'Refresh',
      'common.cancel': 'Cancel',
      'approvals.bannerTitle': 'Approvals',
      'approvals.lastSync': 'Last successful sync: {{time}}',
      'approvals.lastSyncUnknown': 'No successful approval snapshot loaded yet',
      'approvals.snapshotWarning': 'Showing the last verified approval list because the latest refresh failed.',
      'approvals.channelUnavailable': 'Approval contract failed ({{message}}). Treat this console as unavailable until the endpoint recovers.',
      'approvals.unavailableTitle': 'Approval requests are unavailable',
      'approvals.unavailableDescription': 'The values on this page cannot be verified until a successful response returns.',
      'approvals.retry': 'Try again',
      'approvals.retrying': 'Checking',
      'approvals.openHealth': 'Open platform status',
      'approvals.recoveryGuideTitle': 'Resolve the connection problem',
      'approvals.recoveryGuide.checkAccount': 'Check the current account and organization.',
      'approvals.recoveryGuide.checkStatus': 'Review server and access status.',
      'approvals.recoveryGuide.retry': 'Return and try again.',
      'approvals.technicalError': 'Technical detail',
      'approvals.opsTitle': 'Approvals Readiness',
      'approvals.readinessSummary': '{{pending}} pending · {{timedOut}} timed out · {{covered}}/{{total}} complete',
      'approvals.readinessDetails': 'View readiness diagnostics',
      'approvals.opsDescription': 'Confirm that the approvals contract is reachable, pending requests are still moving, timed-out gates are not stacking up, and each queue item carries enough metadata for a safe decision.',
      'approvals.totalRequestsCard': 'Loaded Requests',
      'approvals.pendingRequestsCard': 'Pending Queue',
      'approvals.timeoutRequestsCard': 'Timed Out',
      'approvals.decidedRequestsCard': 'Decided Requests',
      'approvals.filterTitle': 'Quick Filters',
      'approvals.queueTitle': 'Approval Queue',
      'approvals.emptyHealthyDescription': 'New requests will appear here.',
      'approvals.filterDescription': 'Trim the approval table down to the requests that still need active operator judgment.',
      'approvals.showingRows': 'Showing {{shown}} of {{total}} approvals in the current filter.',
      'approvals.filterEmpty': 'No approvals match the active quick filter',
      'approvals.filterEmptyDescription': 'Switch back to All Approvals or relax the queue filter before assuming there is nothing left to review.',
      'approvals.quickFilters.all': 'All Approvals',
      'approvals.quickFilters.attention': 'Needs Attention',
      'approvals.quickFilters.timedOut': 'Timed Out',
      'approvals.quickFilters.stalePending': 'Stale Pending',
      'approvals.quickFilters.pendingReview': 'Pending Review',
      'approvals.signals.approvalContract': 'Approval Contract',
      'approvals.signals.pendingQueue': 'Pending Queue',
      'approvals.signals.timeoutDebt': 'Timeout Debt',
      'approvals.signals.payloadCoverage': 'Request Completeness',
      'approvals.signalDetails.contractHealthy': 'The approvals contract is responding and can be used for live operator decisions.',
      'approvals.signalDetails.contractMissing': 'The backend is not exposing `/api/approvals` in this environment. Confirm feature wiring before relying on this console.',
      'approvals.signalDetails.contractDenied': 'The approvals endpoint is reachable, but this operator is not authorized. Review admin credentials and proxy auth settings.',
      'approvals.signalDetails.contractTransport': 'The approvals endpoint failed before a response returned. Inspect proxy or backend transport before forcing queue actions.',
      'approvals.signalDetails.contractError': 'The approvals endpoint returned an unexpected HTTP error. Treat the queue as degraded until the contract recovers.',
      'approvals.signalDetails.pendingQueueClear': 'No approvals are currently waiting on manual operator action.',
      'approvals.signalDetails.pendingQueueActive': '{{count}} of {{total}} approval request(s) are still pending manual action.',
      'approvals.signalDetails.timeoutDebtClear': 'No approval request is currently timed out.',
      'approvals.signalDetails.timeoutDebtPresent': '{{count}} approval request(s) have already timed out. Investigate before replaying the underlying tool call.',
      'approvals.signalDetails.payloadCoverageReady': '{{count}} of {{total}} queue item(s) include enough metadata for an informed approval decision.',
      'approvals.signalDetails.payloadCoverageMissing': 'Only {{count}} of {{total}} queue item(s) include complete metadata. Review backend logs before approving or rejecting the rest.',
      'approvals.attentionTitle': 'Attention Queue',
      'approvals.attentionDescription': 'Sort out timed-out or stale pending approvals before handling newer requests.',
      'approvals.attentionEmpty': 'No approvals currently require operator follow-up.',
      'approvals.attentionHealthy': 'The approval queue is not showing stale or timed-out requests right now.',
      'approvals.attentionDetails.approvalTimedOut': 'This approval timed out before a decision was recorded. Confirm whether the blocked run should be replayed or closed manually.',
      'approvals.attentionDetails.pendingTooLong': 'This approval has been pending for {{age}}. Review the blocked run before issuing an approval from memory.',
      'approvals.attentionDetails.pendingReview': 'This approval is waiting for operator review. Confirm the request context and arguments before acting.',
      'approvals.age': 'Age',
      'approvals.openApprovalDetail': 'Open Approval Detail',
      'approvals.detailDescription': 'Review the request payload before approving or rejecting the tool call.',
      'approvals.operatorNoteTitle': 'Why this needs attention',
      'approvals.runbookTitle': 'Troubleshooting Guide',
      'approvals.runbookDescription': 'Use this when the approval queue cannot load or when pending decisions look stale compared with upstream reality.',
      'approvals.runbook.verifyContractTitle': '1. Verify contract exposure',
      'approvals.runbook.verifyContractBody': 'Confirm that `/api/approvals` is advertised in the capability manifest and that approval gating is enabled in this environment.',
      'approvals.runbook.inspectQueueTitle': '2. Inspect the queue outside the page',
      'approvals.runbook.inspectQueueBody': 'Probe the approval endpoint or backend logs to confirm whether pending and timed-out items are current, duplicated, or missing from the UI snapshot.',
      'approvals.runbook.reopenConsolesTitle': '3. Reopen related operator consoles',
      'approvals.runbook.reopenConsolesBody': 'Once the queue responds again, reopen Integrations or Audit before forcing retries so the recovery path stays grounded in live state.',
      'approvals.openIntegrations': 'Open Integrations',
      'approvals.openAudit': 'Open Audit',
      'approvals.tool': 'Tool',
      'approvals.runId': 'Run ID',
      'approvals.requestedAt': 'Requested At',
      'approvals.requestedBy': 'Requested By',
      'approvals.riskLevel': 'Risk level',
      'approvals.timeout': 'Timeout',
      'approvals.idempotencyKey': 'Idempotency key',
      'approvals.technicalDetails': 'Developer details',
      'approvals.statusLabels.pending': 'Pending review',
      'approvals.statusLabels.approved': 'Approved',
      'approvals.statusLabels.rejected': 'Rejected',
      'approvals.statusLabels.timed_out': 'Expired',
      'approvals.statusLabels.cancelled': 'Cancelled',
      'approvals.riskLevels.write': 'Change request',
      'approvals.riskLevels.unknown': 'Needs confirmation',
      'approvals.ageUnknown': 'Needs confirmation',
      'approvals.ageMinutes': '{{count}} minutes',
      'approvals.ageHours': '{{count}} hours',
      'approvals.ageDays': '{{count}} days',
      'approvals.approve': 'Approve',
      'approvals.reject': 'Reject',
      'approvals.rejectTitle': 'Reject Tool Call',
      'approvals.rejectMessage': 'Reject "{{tool}}"?',
      'approvals.reason': 'Rejection Reason',
      'approvals.reasonPlaceholder': 'Optional reason',
      'approvals.allStatuses': 'All Statuses',
      'approvals.empty': 'No approvals found',
      'approvals.selectApproval': 'Select an approval to view details',
    }, true, true)

    listAllApprovalsMock.mockResolvedValue([buildApproval()])
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders queue readiness, attention items, and operator notes for stale approvals', async () => {
    listAllApprovalsMock.mockResolvedValue([
      buildApproval({ id: 'approval-stale', requestedAt: '2024-01-01T09:00:00Z' }),
      buildApproval({ id: 'approval-timeout', toolName: 'confluence_write', status: 'TIMED_OUT' }),
    ])

    const view = renderManager()

    await waitFor(() => {
      expect(screen.getByText('Approvals Readiness')).toBeInTheDocument()
    })

    const leftPane = within(view.container.querySelector('.split-left') as HTMLElement)

    await waitFor(() => {
      expect(screen.getByText('Attention Queue')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(leftPane.getByText('Showing 2 of 2 approvals in the current filter.')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Timed Out' }))

    await waitFor(() => {
      expect(leftPane.getByText('Showing 1 of 2 approvals in the current filter.')).toBeInTheDocument()
    })

    expect(leftPane.getByText('Confluence 문서 작성')).toBeInTheDocument()
    expect(leftPane.queryByText('Jira 쓰기')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'All Approvals' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Open Approval Detail' })[0])

    await waitFor(() => {
      expect(screen.getByText('Why this needs attention')).toBeInTheDocument()
    })

    expect(screen.getAllByText(/This approval timed out|This approval has been pending/).length).toBeGreaterThan(0)
  })

  it('keeps approval decisions inside the Today workspace', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Approval Queue')).toBeInTheDocument()
    })

    expect(document.querySelector('.release-workflow-backlink')).not.toBeInTheDocument()
    expect(screen.queryByText('Release workflow')).not.toBeInTheDocument()
  })

  it('keeps raw approval evidence and decisions out of the queue row', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getAllByText('Jira 쓰기').length).toBeGreaterThan(0)
    })

    expect(screen.getAllByText('Pending review').length).toBeGreaterThan(0)
    expect(screen.queryByText('PENDING')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByText('run-1')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Jira 쓰기 Pending review/ }))

    await waitFor(() => {
      expect(screen.getByText('Developer details')).toBeInTheDocument()
    })

    const technicalDetails = screen.getByText('Developer details').closest('details')
    expect(technicalDetails).not.toHaveAttribute('open')
    expect(screen.getByText('run-1')).not.toBeVisible()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()

    fireEvent.click(screen.getByText('Developer details'))
    expect(screen.getByText('run-1')).toBeVisible()
  })

  it('moves a selected approval into view on narrow screens', async () => {
    const matchMediaDescriptor = Object.getOwnPropertyDescriptor(window, 'matchMedia')
    const scrollIntoViewDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView')
    const scrollIntoView = vi.fn()

    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: true }),
    })
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    })

    try {
      renderManager()

      await waitFor(() => {
        expect(screen.getAllByText('Jira 쓰기').length).toBeGreaterThan(0)
      })

      fireEvent.click(screen.getByRole('button', { name: /Jira 쓰기 Pending review/ }))

      await waitFor(() => {
        expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
      })
    } finally {
      if (matchMediaDescriptor) Object.defineProperty(window, 'matchMedia', matchMediaDescriptor)
      else delete (window as { matchMedia?: Window['matchMedia'] }).matchMedia

      if (scrollIntoViewDescriptor) Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', scrollIntoViewDescriptor)
      else delete (HTMLElement.prototype as { scrollIntoView?: () => void }).scrollIntoView
    }
  })

  it('renders one compact empty queue when readiness passes', async () => {
    listAllApprovalsMock.mockResolvedValue([])
    const view = renderManager()

    await waitFor(() => {
      expect(screen.getByText('No approvals found')).toBeInTheDocument()
    })

    expect(screen.getByText('0 pending · 0 timed out · 0/0 complete')).toBeInTheDocument()
    expect(screen.queryByText('Attention Queue')).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Quick Filters' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(view.container.querySelectorAll('.stat-card')).toHaveLength(0)
    expect(view.container.querySelector('.readiness-strip')).not.toBeInTheDocument()
  })

  it('fails closed with one recovery surface when the approvals contract fails on first load', async () => {
    listAllApprovalsMock.mockRejectedValueOnce(new Error('HTTP 404'))

    renderManager()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Approval requests are unavailable')
    })

    expect(screen.queryByText('Approvals Readiness')).not.toBeInTheDocument()
    expect(screen.queryByText('Approval Queue')).not.toBeInTheDocument()
    expect(screen.queryByText('Troubleshooting Guide')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open platform status' })).toHaveAttribute('href', '/health')
    expect(screen.getByText('Resolve the connection problem').closest('details')).not.toHaveAttribute('open')
    expect(screen.getAllByRole('button', { name: 'Try again' })).toHaveLength(1)
  })

  it('keeps the last successful snapshot visible when refresh fails later', async () => {
    listAllApprovalsMock
      .mockResolvedValueOnce([buildApproval({ toolName: 'jira_write' })])
      .mockRejectedValueOnce(new Error('socket hang up'))

    renderManager()

    await waitFor(() => {
      expect(screen.getAllByText('Jira 쓰기').length).toBeGreaterThan(0)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => {
      expect(screen.getByText('Showing the last verified approval list because the latest refresh failed.')).toBeInTheDocument()
    })

    expect(screen.getAllByText('Jira 쓰기').length).toBeGreaterThan(0)
  })
})

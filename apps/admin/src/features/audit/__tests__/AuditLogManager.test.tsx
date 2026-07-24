import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, i18n, render, screen, waitFor } from '../../../test/utils'
import * as auditApi from '../api'
import type { AuditLogEntry } from '../types'
import { AuditLogManager } from '../ui/AuditLogManager'

vi.mock('../api', () => ({
  listAuditPage: vi.fn(),
  previewAuditRollback: vi.fn(),
  rollbackAuditEntry: vi.fn(),
}))

const row: AuditLogEntry = {
  id: 'admin_audit_1234567890',
  category: 'platform_user',
  action: 'ROLE_UPDATE',
  actor: 'admin-account:1234',
  resourceType: 'user',
  resourceId: 'user-1',
  detail: '{"changes":{"role":{"from":"USER","to":"ADMIN"}}}',
  createdAt: 1710000000000,
}

function renderPage(entry = '/audit') {
  const router = createMemoryRouter([
    { path: '/audit', element: <AuditLogManager /> },
    { path: '/tenants', element: <div>Tenants</div> },
  ], { initialEntries: [entry] })
  return render(<RouterProvider router={router} />)
}

describe('AuditLogManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.addResourceBundle('en', 'translation', {
      'nav.audit': 'Audit Log',
      'nav.help.audit': 'Review administrator changes.',
      'auditPage.showingRows': 'Showing {{shown}} of {{total}} rows',
      'auditPage.lastSyncUnknown': 'Not synchronized',
      'auditPage.lastSyncLabel': 'Last synchronized',
      'auditPage.category': 'Category',
      'auditPage.categoryAll': 'All categories',
      'auditPage.action': 'Action',
      'auditPage.actionAll': 'All actions',
      'auditPage.actor': 'Actor',
      'auditPage.resource': 'Resource',
      'auditPage.rollbackReady': 'Recovery',
      'auditPage.created': 'Created',
      'auditPage.historyTitle': 'Change history',
      'auditPage.detailCoverage': 'Detail coverage',
      'auditPage.detailAvailable': 'Change detail available',
      'auditPage.detailUnavailable': 'No change detail',
      'auditPage.recordId': 'Record ID',
      'auditPage.recoveryStatus': 'Recovery method',
      'auditPage.rollbackManualHelp': 'Verify backend state before manual recovery.',
      'auditPage.rollbackReadyHelp': 'This change can be reviewed for recovery.',
      'auditPage.reviewHelp': 'Review the current resource state.',
      'auditPage.openRecoveryConsole': 'Open owner console',
      'auditPage.changedFields': 'Changed fields',
      'auditPage.detail': 'Technical detail',
      'auditPage.noDetail': 'No detail',
      'auditPage.unavailableTitle': 'Audit records unavailable',
      'auditPage.unavailableDescription': 'The current audit records could not be verified.',
      'auditPage.recoveryGuideTitle': 'Recovery steps',
      'auditPage.recoveryCheckAccount': 'Check access.',
      'auditPage.recoveryCheckConnection': 'Check connection.',
      'auditPage.recoveryRetry': 'Try again.',
      'auditPage.revalidationTitle': 'Latest audit records need another check',
      'auditPage.revalidationDescription': 'Showing the last verified records.',
      'auditPage.categoryLabels.platform_user': 'Account access',
      'auditPage.categoryLabels.approval': 'Approval request',
      'auditPage.categoryLabels.mcp_server': 'External tool connection',
      'auditPage.categoryLabels.mcp_security': 'External tool security',
      'auditPage.categoryLabels.tool_policy': 'Tool permission',
      'auditPage.categoryLabels.output_guard': 'Answer protection',
      'auditPage.categoryLabels.session': 'Conversation record',
      'auditPage.categoryLabels.unknown': 'Other change',
      'auditPage.actionLabels.create': 'Create',
      'auditPage.actionLabels.update': 'Update',
      'auditPage.actionLabels.delete': 'Delete',
      'auditPage.actionLabels.approve': 'Approve',
      'auditPage.actionLabels.reject': 'Reject',
      'auditPage.actionLabels.disable': 'Disable',
      'auditPage.actionLabels.role_update': 'Change role',
      'auditPage.actionLabels.unknown': 'Change record',
      'auditPage.rollbackReadinessLabels.ready': 'Ready to recover',
      'auditPage.rollbackReadinessLabels.warn': 'Manual review',
      'auditPage.resourceLabels.user': 'User',
      'auditPage.resourceLabels.mcp_access_policy': 'External tool access',
      'auditPage.resourceLabels.unknown': 'Changed item',
      'auditPage.resourceNames.userAccount': 'User account',
      'auditPage.changedFieldCount': '{{count}} fields changed',
      'auditPage.empty': 'No audit entries',
      'auditPage.filteredEmpty': 'No matching audit entries',
      'common.apply': 'Apply',
      'common.reset': 'Reset',
      'common.yes': 'Yes',
      'common.no': 'No',
      'common.close': 'Close',
    }, true, true)
    vi.mocked(auditApi.listAuditPage).mockResolvedValue({
      items: [row], total: 1, offset: 0, limit: 25,
    })
  })

  it('renders one server-paginated ledger without readiness cards or release navigation', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Showing 1 of 1 rows')).toBeInTheDocument())

    expect(screen.getByRole('heading', { level: 1, name: 'Audit Log' })).toBeInTheDocument()
    expect(screen.queryByText('Change History Readiness')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /release workflow/i })).not.toBeInTheDocument()
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0)
    expect(document.querySelectorAll('.audit-ledger .badge')).toHaveLength(0)
    expect(document.querySelectorAll('.audit-ledger .data-table-row-trigger-cell')).toHaveLength(0)
    expect(screen.getByText('User account')).toBeInTheDocument()
    expect(screen.queryByText('user · user-1')).not.toBeInTheDocument()
  })

  it('passes URL-addressable category and action filters to the backend', async () => {
    renderPage('/audit?category=platform_user&action=ROLE_UPDATE&page=2')
    await waitFor(() => expect(auditApi.listAuditPage).toHaveBeenCalledWith({
      category: 'platform_user', action: 'ROLE_UPDATE', offset: 25, limit: 25,
    }))
  })

  it('uses human-readable filter options while preserving backend codes', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByRole('option', { name: 'Account access' })).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'platform_user' } })
    fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'ROLE_UPDATE' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(auditApi.listAuditPage).toHaveBeenLastCalledWith({
      category: 'platform_user', action: 'ROLE_UPDATE', offset: 0, limit: 25,
    }))
  })

  it('opens a humanized detail panel while keeping raw detail collapsed', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Showing 1 of 1 rows')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', {
      name: /Account access Change role admin-account:1234 User account/,
    }))

    await waitFor(() => expect(screen.getByRole('complementary')).toBeInTheDocument())
    expect(screen.getByText('Recovery method')).toBeInTheDocument()
    expect(screen.getByText('Record ID')).toBeInTheDocument()
    expect(screen.getByText('Technical detail')).toBeInTheDocument()
    expect(document.querySelector('.audit-technical-detail pre')).toHaveTextContent('"role"')
    expect(screen.getByText('1 fields changed')).toBeInTheDocument()
    expect(screen.queryByText('role')).not.toBeInTheDocument()
  })

  it('moves the selected audit detail into view on narrow screens', async () => {
    const matchMediaDescriptor = Object.getOwnPropertyDescriptor(window, 'matchMedia')
    const scrollIntoViewDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView')
    const scrollIntoView = vi.fn()

    renderPage()
    await waitFor(() => expect(screen.getByText('Showing 1 of 1 rows')).toBeInTheDocument())

    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: true }),
    })
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    })

    try {
      fireEvent.click(screen.getByRole('button', {
        name: /Account access Change role admin-account:1234 User account/,
      }))

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

  it('fails closed when the initial audit request cannot be loaded', async () => {
    vi.mocked(auditApi.listAuditPage).mockRejectedValue(new Error('HTTP 503'))
    renderPage()
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Audit records unavailable'))
    expect(screen.queryByText('Showing 0 of 0 rows')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Category')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Change history')).not.toBeInTheDocument()
    expect(document.querySelector('.alert-error')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(auditApi.listAuditPage).toHaveBeenCalledTimes(2))
  })

  it('retains verified audit records when a later filter request fails', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Showing 1 of 1 rows')).toBeInTheDocument())

    vi.mocked(auditApi.listAuditPage).mockRejectedValueOnce(new Error('HTTP 503'))
    fireEvent.change(screen.getByLabelText('Category'), { target: { value: 'platform_user' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(screen.getByText('Latest audit records need another check')).toBeInTheDocument())
    expect(screen.getByText('User account')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('does not surface unrecognized backend codes or identifiers in the primary ledger', async () => {
    vi.mocked(auditApi.listAuditPage).mockResolvedValueOnce({
      items: [{
        ...row,
        category: 'queue_recovery_v2',
        action: 'LEASE_RECOVERY',
        resourceType: 'job',
        resourceId: 'queue_recovery_v2',
      }],
      total: 1,
      offset: 0,
      limit: 25,
    })

    renderPage()
    await waitFor(() => expect(screen.getAllByText('Other change')).toHaveLength(1))

    expect(screen.getByText('Change record')).toBeInTheDocument()
    expect(screen.getByText('Changed item')).toBeInTheDocument()
    expect(screen.queryByText('queue_recovery_v2')).not.toBeInTheDocument()
    expect(screen.queryByText('LEASE_RECOVERY')).not.toBeInTheDocument()
  })

  it('normalizes known backend resource-type variants before rendering the ledger', async () => {
    vi.mocked(auditApi.listAuditPage).mockResolvedValueOnce({
      items: [{ ...row, resourceType: 'McpAccessPolicy', resourceId: 'tool-access-production' }],
      total: 1,
      offset: 0,
      limit: 25,
    })

    renderPage()
    await waitFor(() => expect(screen.getByText('External tool access')).toBeInTheDocument())
    expect(screen.queryByText('McpAccessPolicy')).not.toBeInTheDocument()
  })
})

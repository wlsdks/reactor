import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, i18n, render, screen, waitFor } from '../../../test/utils'
import { AuditRollbackModal } from '../ui/AuditRollbackModal'
import * as auditApi from '../api'
import { ApiError } from '../../../shared/api/errors'
import type { AuditLogEntry } from '../types'

vi.mock('../api', () => ({
  previewAuditRollback: vi.fn(),
  rollbackAuditEntry: vi.fn(),
}))

const previewMock = vi.mocked(auditApi.previewAuditRollback)
const rollbackMock = vi.mocked(auditApi.rollbackAuditEntry)

const baseEntry: AuditLogEntry = {
  id: 'audit-xyz',
  category: 'MCP_SERVER',
  action: 'UPDATE',
  actor: 'ops-admin',
  resourceType: 'server',
  resourceId: 'atlassian',
  detail: '{"before":{"status":"DISCONNECTED"},"after":{"status":"CONNECTED"}}',
  createdAt: 1710000000000,
}

describe('AuditRollbackModal', () => {
  beforeEach(() => {
    previewMock.mockResolvedValue({})
    i18n.addResourceBundle('en', 'translation', {
      'auditPage.category': 'Category',
      'auditPage.action': 'Action',
      'auditPage.actor': 'Actor',
      'auditPage.resource': 'Resource',
      'auditPage.created': 'Created',
      'auditPage.rollback.modalTitle': 'Roll back audit entry',
      'auditPage.rollback.entryTitle': 'Audit entry',
      'auditPage.rollback.impactPreview': 'Impact preview',
      'auditPage.rollback.previewField': 'Field',
      'auditPage.rollback.previewFrom': 'From',
      'auditPage.rollback.previewTo': 'To',
      'auditPage.rollback.previewEmpty': 'Backend returned no concrete changes for this rollback.',
      'auditPage.rollback.previewUnavailable': 'Preview unavailable; confirm with caution.',
      'auditPage.rollback.manualRecoveryBoundary': 'Automatic rollback is blocked; use this preview for manual recovery.',
      'auditPage.rollback.typeToConfirm': 'Type "{{name}}" to confirm',
      'auditPage.rollback.typeToConfirmHelp': 'This is a dangerous action.',
      'auditPage.rollback.confirm': 'Roll back',
      'auditPage.rollback.submitting': 'Rolling back…',
      'auditPage.rollback.cancel': 'Cancel',
      'auditPage.rollback.successToast': 'Rollback requested successfully.',
      'auditPage.rollback.errorToast': 'Rollback failed: {{message}}',
      'common.loading': 'Loading',
      'common.aria.close': 'Close',
    }, true, true)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('does not render when open is false', () => {
    render(
      <AuditRollbackModal open={false} entry={baseEntry} onClose={vi.fn()} onSuccess={vi.fn()} />,
    )
    expect(screen.queryByText('Roll back audit entry')).not.toBeInTheDocument()
  })

  it('shows entry details and the manual recovery boundary notice', async () => {
    previewMock.mockResolvedValueOnce({
      summary: 'Will flip status back to DISCONNECTED',
      changes: [{ field: 'status', from: 'CONNECTED', to: 'DISCONNECTED' }],
    })

    render(
      <AuditRollbackModal open={true} entry={baseEntry} onClose={vi.fn()} onSuccess={vi.fn()} />,
    )

    expect(screen.getByText('Roll back audit entry')).toBeInTheDocument()
    expect(screen.getByText(/Automatic rollback is blocked/)).toBeInTheDocument()
    expect(screen.getByText('MCP_SERVER')).toBeInTheDocument()
    expect(screen.getByText(/Actor: ops-admin/)).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('Will flip status back to DISCONNECTED')).toBeInTheDocument()
    })
    expect(screen.getByText('status')).toBeInTheDocument()
    expect(screen.getByText('CONNECTED')).toBeInTheDocument()
    expect(screen.getByText('DISCONNECTED')).toBeInTheDocument()
  })

  it('renders a graceful fallback when the preview endpoint returns 404', async () => {
    previewMock.mockRejectedValueOnce(new ApiError(404, 'NOT_FOUND', 'Not found'))
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    render(
      <AuditRollbackModal open={true} entry={baseEntry} onClose={vi.fn()} onSuccess={vi.fn()} />,
    )

    await waitFor(() => {
      expect(screen.getByText('Preview unavailable; confirm with caution.')).toBeInTheDocument()
    })

    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })

  it('keeps confirm disabled until the typed resource name matches', async () => {
    previewMock.mockResolvedValueOnce({})

    render(
      <AuditRollbackModal open={true} entry={baseEntry} onClose={vi.fn()} onSuccess={vi.fn()} />,
    )

    const confirm = screen.getByRole('button', { name: 'Roll back' })
    expect(confirm).toBeDisabled()

    const input = screen.getByLabelText(/Type "server:atlassian"/)
    fireEvent.change(input, { target: { value: 'server:atlassian' } })
    expect(confirm).not.toBeDisabled()
  })

  it('submits the rollback mutation and reports success via onSuccess + onClose', async () => {
    previewMock.mockResolvedValueOnce({})
    rollbackMock.mockResolvedValueOnce({ ok: true })
    const onClose = vi.fn()
    const onSuccess = vi.fn()

    render(
      <AuditRollbackModal open={true} entry={baseEntry} onClose={onClose} onSuccess={onSuccess} />,
    )

    const input = screen.getByLabelText(/Type "server:atlassian"/)
    fireEvent.change(input, { target: { value: 'server:atlassian' } })
    fireEvent.click(screen.getByRole('button', { name: 'Roll back' }))

    await waitFor(() => {
      expect(rollbackMock).toHaveBeenCalledWith('audit-xyz')
      expect(onSuccess).toHaveBeenCalled()
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('keeps modal open and surfaces error message on failed rollback', async () => {
    previewMock.mockResolvedValueOnce({})
    rollbackMock.mockRejectedValueOnce(new ApiError(404, 'NOT_FOUND', 'Not found'))
    const onClose = vi.fn()
    const onSuccess = vi.fn()

    render(
      <AuditRollbackModal open={true} entry={baseEntry} onClose={onClose} onSuccess={onSuccess} />,
    )

    const input = screen.getByLabelText(/Type "server:atlassian"/)
    fireEvent.change(input, { target: { value: 'server:atlassian' } })
    fireEvent.click(screen.getByRole('button', { name: 'Roll back' }))

    await waitFor(() => {
      expect(rollbackMock).toHaveBeenCalled()
    })
    expect(onSuccess).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('falls back to action+id slug when no resource metadata exists', async () => {
    previewMock.mockResolvedValueOnce({})
    const entryWithoutResource: AuditLogEntry = {
      ...baseEntry,
      resourceType: null,
      resourceId: null,
      id: 'abcd1234efgh',
    }

    render(
      <AuditRollbackModal
        open={true}
        entry={entryWithoutResource}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    )

    expect(screen.getByLabelText(/Type "UPDATE:abcd1234"/)).toBeInTheDocument()
  })
})

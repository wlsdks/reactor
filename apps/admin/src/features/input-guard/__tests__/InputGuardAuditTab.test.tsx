import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { i18n, render, screen } from '../../../test/utils'
import { InputGuardAuditTab } from '../ui/InputGuardAuditTab'
import * as inputGuardApi from '../api'

vi.mock('../api', () => ({
  listInputGuardAudits: vi.fn(),
}))

const listAuditsMock = vi.mocked(inputGuardApi.listInputGuardAudits)

function renderAuditTab() {
  return render(<MemoryRouter><InputGuardAuditTab /></MemoryRouter>)
}

beforeEach(() => {
  i18n.addResourceBundle('en', 'translation', {
    'auditPage.action': 'Activity',
    'inputGuard.audit.actionFilter': 'Record type',
    'inputGuard.audit.limit': 'Rows',
    'inputGuard.audit.resultCount': '{{count}} records',
    'inputGuard.audit.time': 'When',
    'inputGuard.audit.actor': 'Who',
    'inputGuard.audit.resource': 'Target',
    'inputGuard.audit.detail': 'What happened',
    'inputGuard.audit.emptyTitle': 'No history',
    'inputGuard.audit.emptyDesc': 'No changes yet.',
    'inputGuard.audit.all': 'All records',
    'inputGuard.audit.unavailableTitle': 'History is unavailable',
    'inputGuard.audit.unavailableDescription': 'Do not infer missing history.',
    'inputGuard.audit.unknownAction': 'Unknown activity',
    'inputGuard.audit.unknownTarget': 'Unknown target',
    'inputGuard.audit.unknownSummary': 'Activity details are unavailable',
    'inputGuard.audit.unknownActor': 'Unknown operator',
    'inputGuard.audit.actionLabels.updateSettings': 'Update request settings',
    'inputGuard.audit.actionLabels.stageConfigUpdate': 'Update check stage',
    'inputGuard.audit.actionLabels.pipelineReorder': 'Change check order',
    'inputGuard.audit.actionLabels.simulate': 'Run preview',
    'inputGuard.audit.actionLabels.ruleCreate': 'Add blocking rule',
    'inputGuard.audit.actionLabels.ruleUpdate': 'Update blocking rule',
    'inputGuard.audit.actionLabels.ruleDelete': 'Delete blocking rule',
    'inputGuard.audit.actionLabels.block': 'Block request',
    'inputGuard.audit.actionLabels.warn': 'Record warning',
    'inputGuard.audit.targetLabels.settings': 'Request settings',
    'inputGuard.audit.targetLabels.stage': 'Check stage',
    'inputGuard.audit.targetLabels.pipeline': 'Check order',
    'inputGuard.audit.targetLabels.simulation': 'Preview',
    'inputGuard.audit.targetLabels.rule': 'Blocking rule',
    'inputGuard.audit.targetLabels.request': 'Checked request',
    'inputGuard.audit.summaryLabels.updateSettings': 'Updated request settings',
    'inputGuard.audit.summaryLabels.stageConfigUpdate': 'Updated a check stage',
    'inputGuard.audit.summaryLabels.pipelineReorder': 'Changed check order',
    'inputGuard.audit.summaryLabels.simulate': 'Ran an input preview',
    'inputGuard.audit.summaryLabels.ruleCreate': 'Added a blocking rule',
    'inputGuard.audit.summaryLabels.ruleUpdate': 'Updated a blocking rule',
    'inputGuard.audit.summaryLabels.ruleDelete': 'Deleted a blocking rule',
    'inputGuard.audit.summaryLabels.block': 'Blocked a potentially unsafe request',
    'inputGuard.audit.summaryLabels.warn': 'Recorded a warning and continued',
    'inputGuard.recoveryTitle': 'How to recover',
    'inputGuard.recoveryAccount': 'Check access.',
    'inputGuard.recoveryConnection': 'Check service status.',
    'common.retry': 'Retry',
    'common.retrying': 'Retrying',
    'common.openStatusPage': 'Open status',
    'common.technicalDetails': 'Technical details',
  }, true, true)
})

describe('InputGuardAuditTab', () => {
  it('uses readable activity labels in the filter and table instead of backend codes', async () => {
    listAuditsMock.mockResolvedValue({
      total: 1,
      audits: [{
        id: 'audit-1',
        timestamp: new Date().toISOString(),
        category: 'rules',
        action: 'RULE_UPDATE',
        actor: 'Minji Kim',
        resourceType: 'rule',
        resourceId: 'rule-1',
        detail: 'rule=rule-1',
      }],
    })

    renderAuditTab()

    await screen.findByText('Updated a blocking rule')
    expect(screen.getByRole('option', { name: 'Update blocking rule' })).toBeInTheDocument()
    expect(screen.getByText('Blocking rule')).toBeInTheDocument()
    expect(screen.queryByText(/^RULE_UPDATE$/)).not.toBeInTheDocument()
    expect(screen.queryByText('rule=rule-1')).not.toBeInTheDocument()
  })

  it('keeps an unavailable audit request distinct from an empty history', async () => {
    listAuditsMock.mockRejectedValue(new Error('HTTP 503: audit service unavailable'))

    renderAuditTab()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('History is unavailable')
    expect(screen.queryByText('No history')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Record type')).not.toBeInTheDocument()
    const technicalDetails = screen.getByText('Technical details').closest('details')
    expect(technicalDetails).not.toHaveAttribute('open')
  })
})

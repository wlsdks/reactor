import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { fireEvent, i18n, render, screen, waitFor, within } from '../../../test/utils'
import { OutputGuardManager } from '../ui/OutputGuardManager'
import * as outputGuardApi from '../api'
import type { OutputGuardAuditLog, OutputGuardRule, SimulateOutputGuardResponse } from '../types'

vi.mock('../api', () => ({
  listRules: vi.fn(),
  listRuleAudits: vi.fn(),
  createRule: vi.fn(),
  updateRule: vi.fn(),
  deleteRule: vi.fn(),
  simulateGuard: vi.fn(),
}))

const listRulesMock = vi.mocked(outputGuardApi.listRules)
const listRuleAuditsMock = vi.mocked(outputGuardApi.listRuleAudits)
const simulateGuardMock = vi.mocked(outputGuardApi.simulateGuard)

function buildRule(overrides: Partial<OutputGuardRule> = {}): OutputGuardRule {
  return {
    id: 'rule-1',
    name: 'Credit card blocker',
    pattern: '\\b\\d{4}-\\d{4}-\\d{4}-\\d{4}\\b',
    action: 'REJECT',
    priority: 10,
    enabled: true,
    createdAt: 1710000000000,
    updatedAt: 1710003600000,
    ...overrides,
  }
}

function buildAudit(overrides: Partial<OutputGuardAuditLog> = {}): OutputGuardAuditLog {
  return {
    id: 'audit-1',
    ruleId: 'rule-1',
    action: 'SIMULATE',
    actor: 'ops-admin',
    detail: 'Blocked sample card number',
    createdAt: 1710007200000,
    ...overrides,
  }
}

function buildSimulation(overrides: Partial<SimulateOutputGuardResponse> = {}): SimulateOutputGuardResponse {
  return {
    originalContent: 'card number: 4111-1111-1111-1111',
    resultContent: 'card number: [redacted]',
    blocked: true,
    modified: true,
    blockedByRuleId: 'rule-1',
    blockedByRuleName: 'Credit card blocker',
    matchedRules: [
      {
        ruleId: 'rule-1',
        ruleName: 'Credit card blocker',
        action: 'REJECT',
        priority: 10,
      },
    ],
    invalidRules: [
      {
        ruleId: 'rule-bad',
        ruleName: 'Broken token detector',
        reason: 'Unterminated group',
      },
    ],
    ...overrides,
  }
}

function renderWithRouter() {
  const router = createMemoryRouter(
    [{ path: '/', element: <OutputGuardManager /> }],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

describe('OutputGuardManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'common.edit': 'Edit',
      'common.delete': 'Delete',
      'common.refresh': 'Refresh',
      'common.yes': 'yes',
      'common.no': 'no',
      'common.retry': 'Retry',
      'common.retrying': 'Retrying',
      'common.technicalDetails': 'Technical details',
      'common.releaseWorkflowBacklink': 'Release workflow',
      'common.releaseWorkflowBacklinkStep': 'Release workflow step {{step}}',
      'nav.outputGuard': 'Response Filters',
      'nav.help.outputGuard': 'Set rules to filter or block unsafe AI responses.',
      'outputGuardPage.newRule': 'New Rule',
      'outputGuardPage.ruleCount': 'Rules',
      'outputGuardPage.auditCount': 'Audits',
      'outputGuardPage.opsTitle': 'Guard Coverage',
      'outputGuardPage.totalRulesCard': 'Total Rules',
      'outputGuardPage.activeRulesCard': 'Active Rules',
      'outputGuardPage.rejectRulesCard': 'Reject Rules',
      'outputGuardPage.auditChannelCard': 'Audit Channel',
      'outputGuardPage.auditUnavailableShort': 'Down',
      'outputGuardPage.unavailableTitle': 'Answer protection unavailable',
      'outputGuardPage.unavailableDescription': 'Changes and tests are paused until rules can be verified.',
      'outputGuardPage.recoveryTitle': 'How to check',
      'outputGuardPage.recoveryAccount': 'Check account access.',
      'outputGuardPage.recoveryConnection': 'Check Reactor status.',
      'common.openStatusPage': 'Open status',
      'outputGuardPage.simulation': 'Simulation',
      'outputGuardPage.auditLog': 'Audit Log',
      'outputGuardPage.simulationTitle': 'Simulation Console',
      'outputGuardPage.simulationContent': 'Simulation Content',
      'outputGuardPage.includeDisabled': 'Include disabled rules',
      'outputGuardPage.runSimulation': 'Run Simulation',
      'outputGuardPage.simulationOutcome': 'Simulation Outcome',
      'outputGuardPage.blocked': 'Blocked',
      'outputGuardPage.modified': 'Modified',
      'outputGuardPage.matchedRules': 'Matched Rules',
      'outputGuardPage.invalidRules': 'Invalid Rules',
      'outputGuardPage.blockedBy': 'Blocked By',
      'outputGuardPage.matchedRuleList': 'Applied Rules',
      'outputGuardPage.invalidRuleList': 'Rules to fix',
      'outputGuardPage.ruleAction': 'Action',
      'outputGuardPage.rulePriority': 'Priority',
      'outputGuardPage.ruleStatus': 'Status',
      'outputGuardPage.ruleId': 'Rule ID',
      'outputGuardPage.ruleCreated': 'Created',
      'outputGuardPage.ruleUpdated': 'Updated',
      'outputGuardPage.regexPattern': 'Regex Pattern',
      'outputGuardPage.filterPattern': 'Filter Pattern',
      'outputGuardPage.ruleDescriptionReject': 'Responses matching this pattern will be blocked.',
      'outputGuardPage.ruleDescriptionMask': 'Matching parts in responses will be masked.',
      'outputGuardPage.patternError': 'Pattern error',
      'outputGuardPage.patternNeedsFix': 'The specialist expression needs attention.',
      'outputGuardPage.refreshFailed': 'Showing the last verified rules.',
      'outputGuardPage.priorityValue': 'Priority {{priority}}',
      'outputGuardPage.invalidRuleNeedsFix': 'The specialist expression needs attention',
      'outputGuardPage.simulationStatus.passed': 'No issues found',
      'outputGuardPage.simulationStatus.needsReview': 'Needs review',
      'outputGuardPage.simulationStatus.blocked': 'Blocked by policy',
      'outputGuardPage.auditTitle': 'Recent Audits',
      'outputGuardPage.auditUnavailable': 'Audit endpoint is unavailable right now. Review backend logs before assuming policy history is intact.',
      'outputGuardPage.auditEmpty': 'No audit rows',
      'outputGuardPage.actionLabels.mask': 'Mask',
      'outputGuardPage.actionLabels.block': 'Block',
      'outputGuardPage.actionLabels.redact': 'Redact',
      'outputGuardPage.actionLabels.allow': 'Allow',
      'outputGuardPage.statusLabels.enabled': 'Enabled',
      'outputGuardPage.statusLabels.disabled': 'Disabled',
      'outputGuardPage.statusLabels.paused': 'Paused',
    }, true, true)

    listRulesMock.mockResolvedValue([
      buildRule(),
      buildRule({
        id: 'rule-2',
        name: 'Phone masker',
        pattern: '\\b\\d{3}-\\d{3}-\\d{4}\\b',
        action: 'MASK',
        priority: 100,
        enabled: false,
      }),
    ])
    listRuleAuditsMock.mockResolvedValue([
      buildAudit(),
    ])
    simulateGuardMock.mockResolvedValue(buildSimulation())
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders operator summary counts and selected rule details after a row is chosen', async () => {
    renderWithRouter()

    await waitFor(() => {
      expect(screen.getByText('Credit card blocker')).toBeInTheDocument()
    })

    expect(screen.getByText(/Rules: 2/)).toBeInTheDocument()
    expect(screen.getByText(/Audits: 1/)).toBeInTheDocument()
    expect(screen.getByText(/total rules/i)).toBeInTheDocument()
    expect(screen.getByText(/active rules/i)).toBeInTheDocument()
    expect(screen.getByText(/reject rules/i)).toBeInTheDocument()
    expect(screen.getByText(/audit channel/i)).toBeInTheDocument()

    fireEvent.click(screen.getByText('Phone masker'))

    await waitFor(() => {
      expect(screen.getByText('Matching parts in responses will be masked.')).toBeInTheDocument()
    })

    // The open detail retains the operator-facing action, priority, state, and
    // timestamps. Identifiers and expressions stay behind technical details.
    const detailPanel = screen
      .getByText('Matching parts in responses will be masked.')
      .closest('.detail-panel') as HTMLElement
    expect(detailPanel).not.toBeNull()
    const metaGrid = detailPanel.querySelector('.meta-grid') as HTMLElement
    expect(metaGrid).not.toBeNull()
    expect(within(metaGrid).getByText(/Action:/)).toBeInTheDocument()
    // Action label is now localized via `localizeAction` (MASK -> "Mask"
    // in the test fixture). The raw enum value is no longer rendered.
    expect(within(metaGrid).getByText('Mask')).toBeInTheDocument()
    expect(within(metaGrid).getByText(/Priority:\s*100/)).toBeInTheDocument()
    expect(within(metaGrid).getByText(/Status:/)).toBeInTheDocument()
    expect(within(metaGrid).queryByText(/Rule ID:/)).not.toBeInTheDocument()
    expect(within(metaGrid).queryByText('rule-2')).not.toBeInTheDocument()
    expect(within(metaGrid).getByText(/Created:/)).toBeInTheDocument()
    expect(within(metaGrid).getByText(/Updated:/)).toBeInTheDocument()
    const technicalDetails = within(detailPanel).getByText('Technical details').closest('details')
    expect(technicalDetails).not.toHaveAttribute('open')
    fireEvent.click(within(technicalDetails as HTMLElement).getByText('Technical details'))
    expect(within(technicalDetails as HTMLElement).getByText('rule-2')).toBeInTheDocument()
    expect(within(technicalDetails as HTMLElement).getByText('\\b\\d{3}-\\d{3}-\\d{4}\\b')).toBeInTheDocument()
    expect(document.querySelectorAll('.row-actions')).toHaveLength(0)
    expect(within(detailPanel).getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(within(detailPanel).getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    expect(detailPanel.querySelector('.safety-policy-state')).toHaveTextContent('Disabled')
  })

  it('keeps the answer-protection summary focused on policy state', async () => {
    renderWithRouter()

    await waitFor(() => {
      expect(screen.getByText('Guard Coverage')).toBeInTheDocument()
    })

    expect(screen.queryByRole('link', { name: /Release workflow step/i })).not.toBeInTheDocument()
    expect(screen.getByText('Total Rules')).toBeVisible()
  })

  it('keeps rule coverage visible when audit loading fails', async () => {
    listRuleAuditsMock.mockRejectedValueOnce(new Error('HTTP 503'))

    renderWithRouter()

    await waitFor(() => {
      expect(screen.getByText('Credit card blocker')).toBeInTheDocument()
    })

    expect(screen.getByText(/Rules: 2/)).toBeInTheDocument()
    expect(screen.getByText(/Audits: 0/)).toBeInTheDocument()
    expect(screen.getByText('Down')).toBeInTheDocument()
    expect(listRuleAuditsMock).toHaveBeenCalledWith(50)
  })

  it('shows simulation feedback and refreshes operator data after a dry run', async () => {
    renderWithRouter()

    await waitFor(() => {
      expect(screen.getByText('Credit card blocker')).toBeInTheDocument()
    })

    // Expand the simulation collapsible section (title is "Simulation Console")
    fireEvent.click(screen.getByText('Simulation Console'))

    fireEvent.change(screen.getByLabelText('Simulation Content'), {
      target: { value: 'card number: 4111-1111-1111-1111' },
    })
    fireEvent.click(screen.getByLabelText('Include disabled rules'))
    fireEvent.click(screen.getByRole('button', { name: 'Run Simulation' }))

    await waitFor(() => {
      expect(screen.getByText('Simulation Outcome')).toBeInTheDocument()
    })

    expect(simulateGuardMock).toHaveBeenCalledWith({
      content: 'card number: 4111-1111-1111-1111',
      includeDisabled: true,
    })
    const simulationSummary = document.querySelector('.output-guard-simulation-result__summary')
    expect(simulationSummary).toHaveTextContent('Blockedyes')
    expect(simulationSummary).toHaveTextContent('Modifiedyes')
    expect(simulationSummary).toHaveTextContent('Matched Rules1')
    expect(simulationSummary).toHaveTextContent('Invalid Rules1')
    expect(simulationSummary).toHaveTextContent('Blocked ByCredit card blocker')
    expect(screen.getByText('Blocked by policy')).toBeInTheDocument()
    expect(screen.getByText('Applied Rules')).toBeInTheDocument()
    expect(screen.getByText('Priority 10')).toBeInTheDocument()
    expect(document.querySelectorAll('.tag')).toHaveLength(0)
    expect(screen.getByText('Rules to fix')).toBeInTheDocument()
    expect(screen.getByText('Broken token detector')).toBeInTheDocument()
    expect(screen.queryByText('Unterminated group')).not.toBeInTheDocument()
    expect(screen.getByText('card number: [redacted]')).toBeInTheDocument()

    await waitFor(() => {
      expect(listRulesMock).toHaveBeenCalledTimes(2)
      expect(listRuleAuditsMock).toHaveBeenCalledTimes(2)
    })
  })

  it('fails closed instead of rendering zero counts and mutation actions when rules cannot load', async () => {
    listRulesMock.mockRejectedValueOnce(new Error('HTTP 503'))

    renderWithRouter()

    expect(await screen.findByRole('heading', { name: 'Answer protection unavailable' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'New Rule' })).not.toBeInTheDocument()
    expect(screen.queryByText('Guard Coverage')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open status' })).toHaveAttribute('href', '/health')
  })
})

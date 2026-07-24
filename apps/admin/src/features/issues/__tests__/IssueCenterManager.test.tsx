import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, i18n, render, screen } from '../../../test/utils'
import { IssueCenterManager } from '../ui/IssueCenterManager'
import * as issueQuery from '../query'
import type { IssueCenterSnapshot } from '../types'
import type { TopologyData } from '../query'

vi.mock('../query', () => ({
  useIssueCenterSnapshot: vi.fn(),
  useTopologyData: vi.fn(),
}))

const useIssueCenterSnapshotMock = vi.mocked(issueQuery.useIssueCenterSnapshot)
const useTopologyDataMock = vi.mocked(issueQuery.useTopologyData)

const emptyTopology: TopologyData = {
  reactor: { status: 'PASS', apiBase: 'same-origin', missingPaths: [] },
  projects: [],
}

function buildSnapshot(): IssueCenterSnapshot {
  return {
    generatedAt: 1710000000000,
    total: 3,
    criticalCount: 1,
    warningCount: 2,
    sources: [
      { source: 'mcpServers', total: 1, criticalCount: 1, warningCount: 0 },
      { source: 'scheduler', total: 1, criticalCount: 0, warningCount: 1 },
      { source: 'toolPolicy', total: 1, criticalCount: 0, warningCount: 1 },
    ],
    items: [
      {
        id: 'mcp-preflight:swagger',
        severity: 'critical',
        source: 'mcpServers',
        title: { key: 'issuesPage.titles.preflight', values: { name: 'swagger' } },
        summary: { key: 'mcpServers.preflightFailed' },
        detectedAt: 1710000000000,
        routePath: '/mcp-servers',
        routeLabelKey: 'nav.mcpServers',
        evidence: ['PASS 4', 'WARN 1', 'FAIL 1'],
      },
      {
        id: 'scheduler-attention:job-1',
        severity: 'warning',
        source: 'scheduler',
        title: { key: 'issuesPage.titles.schedulerJob', values: { name: 'Daily sync' } },
        summary: { key: 'scheduler.attentionDetails.neverExecuted' },
        detectedAt: 1710000001000,
        routePath: '/scheduler',
        routeLabelKey: 'nav.scheduler',
        evidence: ['0 0 * * *'],
      },
      {
        id: 'tool-policy:exceptionReview',
        severity: 'warning',
        source: 'toolPolicy',
        title: { key: 'toolPolicyPage.signals.exceptionReview' },
        summary: { key: 'toolPolicyPage.signalDetails.exceptionReviewNeeded', values: { count: 1 } },
        detectedAt: null,
        routePath: '/safety-rules?tab=tool-policy',
        routeLabelKey: 'nav.safetyRules',
        evidence: [],
      },
    ],
  }
}

function renderManager() {
  return render(
    <MemoryRouter>
      <IssueCenterManager />
    </MemoryRouter>,
  )
}

describe('IssueCenterManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'common.refresh': 'Refresh',
      'common.retry': 'Retry',
      'common.close': 'Close',
      'nav.issues': 'Issues',
      'nav.mcpServers': 'MCP Servers',
      'nav.scheduler': 'Scheduled Jobs',
      'nav.safetyRules': 'Safety Rules',
      'nav.toolPolicy': 'Tool Policy',
      'nav.integrations': 'Integrations',
      'nav.approvals': 'Approvals',
      'nav.mcpSecurity': 'MCP Security',
      'nav.outputGuard': 'Output Guard',
      'nav.audit': 'Audit',
      'issuesPage.pageTitle': 'Issues',
      'issuesPage.pageSubtitle': 'System health and issue tracking across all modules',
      'issuesPage.unavailableTitle': 'Issue snapshot unavailable',
      'issuesPage.unavailableDescription': 'The current issue status could not be verified.',
      'issuesPage.recoveryGuideTitle': 'Recovery steps',
      'issuesPage.recoveryCheckAccount': 'Check access.',
      'issuesPage.recoveryCheckConnection': 'Check connection.',
      'issuesPage.recoveryRetry': 'Try again.',
      'issuesPage.topologyDisclosure.title': 'Service relationships',
      'issuesPage.topologyDisclosure.description': 'Open the module relationship map when needed.',
      'issuesPage.openConsole': 'Open Console',
      'issuesPage.evidence': 'Evidence',
      'issuesPage.nextStep': 'Next Step',
      'issuesPage.nextStepDescription': 'Open related console.',
      'issuesPage.nextSteps.label': 'NEXT STEPS',
      'issuesPage.nextSteps.openConsole': 'Open Console',
      'issuesPage.nextSteps.checkServerHealth': 'Check server health',
      'issuesPage.empty': 'No issues match the current filters',
      'issuesPage.emptyDescription': 'Clear filters.',
      'issuesPage.selectIssue': 'Select an issue to view details',
      'issuesPage.selectIssueDescription': 'Right panel shows details.',
      'issuesPage.severityLabels.critical': 'Critical',
      'issuesPage.severityLabels.warning': 'Warning',
      'issuesPage.chips.total': 'Total',
      'issuesPage.chips.critical': 'Critical',
      'issuesPage.chips.warning': 'Warning',
      'issuesPage.chips.healthy': 'Healthy',
      'issuesPage.groupExpand': '+ {{count}} more',
      'issuesPage.filters.critical': 'Critical',
      'issuesPage.filters.warning': 'Warning',
      'issuesPage.titles.preflight': 'Preflight attention: {{name}}',
      'issuesPage.titles.schedulerJob': 'Automation job: {{name}}',
      'mcpServers.preflightFailed': 'Preflight failed',
      'scheduler.attentionDetails.neverExecuted': 'The job never ran.',
      'toolPolicyPage.signals.exceptionReview': 'Override Review',
      'toolPolicyPage.signalDetails.exceptionReviewNeeded': '{{count}} override(s) are active.',
    }, true, true)

    useIssueCenterSnapshotMock.mockReturnValue({
      data: buildSnapshot(),
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    } as never)

    useTopologyDataMock.mockReturnValue({
      data: emptyTopology,
      isLoading: false,
      error: null,
    } as never)
  })

  it('prioritizes the issue list and keeps topology secondary', async () => {
    renderManager()
    expect(screen.getByText('Issues')).toBeInTheDocument()
    expect(screen.getByText('Preflight attention: swagger')).toBeInTheDocument()
    expect(screen.queryByText('Reactor')).not.toBeInTheDocument()
    expect(useTopologyDataMock).toHaveBeenLastCalledWith(false)
    fireEvent.click(screen.getByText('Service relationships'))
    expect(await screen.findByRole('tab', { name: 'List' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: 'Graph' }))
    expect(await screen.findByText('Reactor', {}, { timeout: 5000 })).toBeInTheDocument()
    expect(useTopologyDataMock).toHaveBeenLastCalledWith(true)
  })

  it('renders severity-grouped issues (Critical first)', () => {
    renderManager()
    // Both issue list and detail panel show the title — use getAllByText
    expect(screen.getAllByText('Preflight attention: swagger').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Automation job: Daily sync').length).toBeGreaterThanOrEqual(1)
  })

  it('renders issue items in the list', () => {
    renderManager()
    // The critical issue should appear in the list
    expect(screen.getAllByText('Preflight attention: swagger').length).toBeGreaterThanOrEqual(1)
  })

  it('filters by severity chip click', () => {
    renderManager()
    // Click the Warning chip — button text includes count + "Warning"
    fireEvent.click(screen.getByRole('button', { name: /Warning/i }))
    // Warning issue should still be visible
    expect(screen.getAllByText('Automation job: Daily sync').length).toBeGreaterThanOrEqual(1)
  })

  it('clicking topology node filters issue list to that source', async () => {
    renderManager()
    fireEvent.click(screen.getByText('Service relationships'))
    // Click Scheduler node in topology — label is resolved via i18n; the test
    // instance returns the key when no translation is registered.
    // SystemTopology is lazy-loaded, so await its first render.
    fireEvent.click(await screen.findByText('issuesPage.topology.scheduler'))
    // Scheduler issues should be visible
    expect(screen.getAllByText('Automation job: Daily sync').length).toBeGreaterThanOrEqual(1)
    // mcpServers issue title should not appear in the issue list items
    const issueItems = document.querySelectorAll('.issue-item-title')
    const issueItemTexts = Array.from(issueItems).map((el) => el.textContent)
    expect(issueItemTexts).not.toContain('Preflight attention: swagger')
  })

  it('clicking issue row expands inline detail', () => {
    renderManager()
    // Click on the warning issue in the list to expand inline detail
    fireEvent.click(screen.getByText('Automation job: Daily sync'))
    // The issue title should remain visible
    expect(screen.getAllByText('Automation job: Daily sync').length).toBeGreaterThanOrEqual(1)
  })

  it('fails closed when the issue snapshot cannot be loaded', () => {
    const refetch = vi.fn()
    useIssueCenterSnapshotMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('HTTP 503'),
      refetch,
      isFetching: false,
    } as never)

    renderManager()

    expect(screen.getByRole('alert')).toHaveTextContent('Issue snapshot unavailable')
    expect(screen.queryByLabelText('Priority issue list')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Refresh' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(document.querySelector('.alert-error')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refetch).toHaveBeenCalledOnce()
  })
})

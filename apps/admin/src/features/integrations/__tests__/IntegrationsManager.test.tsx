import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within } from '../../../test/utils'
import { IntegrationsManager } from '../ui/IntegrationsManager'
import * as integrationsApi from '../api'
import * as capabilitiesApi from '../../capabilities/api'
import * as mcpApi from '../../mcp-servers/api'
import * as slackFaqApi from '../../slack-faq/api'
import { ApiError } from '../../../shared/api/errors'
import {
  RELEASE_SLACK_GATEWAY_PATH,
  RELEASE_WORKFLOW_ANCHOR_PATH,
} from '../../../shared/releaseWorkflow'

vi.mock('../api', () => ({
  probeEndpoint: vi.fn(),
  sendSlackCommand: vi.fn(),
  sendSlackEvent: vi.fn(),
  sendErrorReport: vi.fn(),
  runSlackLiveSmoke: vi.fn(),
  runA2aLiveSmoke: vi.fn(),
}))

vi.mock('../../capabilities/api', () => ({
  getCapabilityManifest: vi.fn(),
}))

vi.mock('../../mcp-servers/api', () => ({
  listMcpServers: vi.fn(),
  getMcpPreflight: vi.fn(),
  listSwaggerSpecSources: vi.fn(),
  getMcpServer: vi.fn(),
  registerMcpServer: vi.fn(),
  updateMcpServer: vi.fn(),
  deleteMcpServer: vi.fn(),
  connectMcpServer: vi.fn(),
  disconnectMcpServer: vi.fn(),
  emergencyDenyAll: vi.fn(),
  getMcpAccessPolicy: vi.fn(),
  updateMcpAccessPolicy: vi.fn(),
  clearMcpAccessPolicy: vi.fn(),
  createSwaggerSpecSource: vi.fn(),
  updateSwaggerSpecSource: vi.fn(),
  syncSwaggerSpecSource: vi.fn(),
  listSwaggerSpecRevisions: vi.fn(),
  getSwaggerSpecDiff: vi.fn(),
  publishSwaggerSpecRevision: vi.fn(),
}))

const probeEndpointMock = vi.mocked(integrationsApi.probeEndpoint)
const sendSlackCommandMock = vi.mocked(integrationsApi.sendSlackCommand)
const getCapabilityManifestMock = vi.mocked(capabilitiesApi.getCapabilityManifest)
const listMcpServersMock = vi.mocked(mcpApi.listMcpServers)

function renderManager(initialEntries = ['/']) {
  const router = createMemoryRouter(
    [{ path: '/', element: <IntegrationsManager /> }],
    { initialEntries },
  )
  return { ...render(<RouterProvider router={router} />), router }
}

describe('IntegrationsManager', () => {
  beforeEach(() => {
    getCapabilityManifestMock.mockResolvedValue(new Set(['/api/slack/commands', '/api/slack/events']))
    probeEndpointMock.mockResolvedValue({ status: 200, body: { ok: true }, durationMs: 50 })
    listMcpServersMock.mockResolvedValue([])
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders page title and mode tabs on initial render', () => {
    renderManager()
    // t('nav.integrations') resolves to 'Integrations' from test i18n setup
    expect(screen.getByText('Integrations')).toBeInTheDocument()
  })

  it('separates overview, live run, evidence, and tools in URL-addressable local navigation', async () => {
    const { router } = renderManager()

    expect(screen.getByRole('button', { name: 'integrationsPage.operationsViews.overview' }))
      .toHaveAttribute('aria-current', 'page')
    await userEvent.click(screen.getByRole('button', { name: 'integrationsPage.operationsViews.run' }))
    expect(router.state.location.search).toBe('?view=run')
    expect(document.querySelector('.integrations-operations')).toHaveAttribute('data-view', 'run')

    await userEvent.click(screen.getByRole('button', { name: 'integrationsPage.operationsViews.tools' }))
    expect(router.state.location.search).toBe('?view=tools')
    expect(await screen.findByRole('tab', { name: 'integrationsPage.testerTabSlack' })).toBeInTheDocument()
  })

  it('renders top-level tester tabs and slack sub-tabs', async () => {
    renderManager(['/?view=tools'])
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'integrationsPage.testerTabSlack' })).toBeInTheDocument()
    })
    expect(screen.getByRole('tab', { name: 'integrationsPage.testerTabError' })).toBeInTheDocument()
    // Slack sub-tabs live inside the lazy-loaded IntegrationsSlackTab — wait for it to mount.
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'integrationsPage.modeCommand' })).toBeInTheDocument()
    })
    expect(screen.getByRole('tab', { name: 'integrationsPage.modeEvent' })).toBeInTheDocument()
  })

  it('shows send command button in command tab', async () => {
    renderManager(['/?view=tools'])
    // Send button lives inside the lazy IntegrationsSlackTab.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'integrationsPage.sendCommand' })).toBeInTheDocument()
    })
  })

  it('keeps a manual test result readable and hides raw response data by default', async () => {
    sendSlackCommandMock.mockResolvedValue({ status: 200, body: { ok: true } })
    renderManager(['/?view=tools'])

    const sendButton = await screen.findByRole('button', { name: 'integrationsPage.sendCommand' })
    await userEvent.click(sendButton)

    expect(await screen.findByText('integrationsPage.toolResult.successLabel')).toBeInTheDocument()
    expect(screen.getByText('integrationsPage.toolResult.successDescription')).toBeInTheDocument()
    const technicalResponse = screen.getByText('integrationsPage.toolResult.technicalDetails').closest('details')
    expect(technicalResponse).toBeInTheDocument()
    expect(technicalResponse).not.toHaveAttribute('open')
    expect(document.querySelector('.integration-tool-workspace .detail-panel')).not.toBeInTheDocument()
  })

  it('links the Slack tester back to release smoke evidence', async () => {
    renderManager(['/?view=tools'])

    expect(await screen.findByRole('tab', { name: 'integrationsPage.modeCommand' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'integrationsPage.releaseSmoke.workflowSlack' }))
      .toHaveAttribute('href', RELEASE_SLACK_GATEWAY_PATH)
    expect(screen.getByText('integrationsPage.slackSmokeHandoff.title')).toBeInTheDocument()
    const technicalDetails = screen.getByText('integrationsPage.slackTechnicalDetails').closest('details')
    expect(technicalDetails).toBeInTheDocument()
    expect(technicalDetails).not.toHaveAttribute('open')
    expect(technicalDetails).toHaveTextContent('integrationsPage.slackSmokeHandoff.description')
    expect(technicalDetails).toHaveTextContent('integrationsPage.slackSmokeHandoff.env')
    expect(technicalDetails).toHaveTextContent('integrationsPage.slackSmokeHandoff.evidence')
  })

  it('links the Slack tester panel back to the release workflow cockpit', async () => {
    renderManager(['/?view=tools'])

    expect(await screen.findByRole('tab', { name: 'integrationsPage.modeCommand' })).toBeInTheDocument()
    const slackTesterPanel = screen
      .getAllByRole('tabpanel')
      .find((panel) => panel.id === 'integrations-slack-tabpanel')
    expect(slackTesterPanel).toBeDefined()
    expect(within(slackTesterPanel).getByRole('link', { name: 'common.releaseWorkflowBacklinkStep' }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_ANCHOR_PATH)
  })

  it('calls probeEndpoint to load control plane probes', async () => {
    renderManager(['/?view=tools'])
    await waitFor(() => {
      expect(getCapabilityManifestMock).toHaveBeenCalled()
    })
  })

  it('keeps release-stage navigation in the LNB when integrations access is forbidden', async () => {
    const forbidden = new ApiError(403, 'FORBIDDEN', 'Forbidden')
    getCapabilityManifestMock.mockRejectedValue(forbidden)
    listMcpServersMock.mockRejectedValue(forbidden)

    renderManager()

    expect(await screen.findByText('접근 권한이 없어요')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
  })

  it('shows control plane section title after probes load', async () => {
    renderManager()
    await waitFor(() => {
      expect(screen.getByText('integrationsPage.controlPlaneTitle')).toBeInTheDocument()
    })
  })

  it('keeps project connection status in a flat local section', async () => {
    renderManager()

    const projectConnectionsTitle = await screen.findByText('integrationsPage.projectConnectionsTitle')
    const projectConnectionsPanel = projectConnectionsTitle.closest('.project-connections')
    expect(projectConnectionsPanel).toBeInTheDocument()
    expect(projectConnectionsPanel?.querySelector('.info-card')).not.toBeInTheDocument()
    expect(projectConnectionsPanel?.querySelector('.badge')).not.toBeInTheDocument()
  })

  it('does not repeat release workflow links inside project connections', async () => {
    renderManager()

    const projectConnectionsTitle = await screen.findByText('integrationsPage.projectConnectionsTitle')
    const projectConnectionsPanel = projectConnectionsTitle.closest('.project-connections')
    expect(projectConnectionsPanel).toBeInTheDocument()
    expect(within(projectConnectionsPanel).queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
    expect(within(projectConnectionsPanel).queryByRole('link', { name: 'integrationsPage.releaseSmoke.title' })).not.toBeInTheDocument()
  })

  it('opens the requested tester tab from the URL query', async () => {
    renderManager(['/?tab=error'])

    const errorTab = await screen.findByRole('tab', { name: 'integrationsPage.testerTabError' })
    expect(errorTab).toHaveAttribute('aria-selected', 'true')
  })

  it('keeps the error alert test in the same flat operation layout', async () => {
    renderManager(['/?tab=error'])

    expect(await screen.findByRole('button', { name: 'integrationsPage.sendError' })).toBeInTheDocument()
    expect(document.querySelector('.integration-tool-workspace .detail-panel')).not.toBeInTheDocument()
    expect(document.querySelector('.integration-tool-form__field-heading .btn')).toHaveTextContent('integrationsPage.applyPreset')
  })

  it('renders the new FAQ sub-tab and mounts SlackFaqTab when activated', async () => {
    vi.spyOn(slackFaqApi, 'listFaqChannels').mockResolvedValue([])
    vi.spyOn(slackFaqApi, 'getFaqOrgStats').mockResolvedValue({
      totalChannels: 0,
      totalQueries7d: 0,
      avgHitRate7d: 0,
    })
    vi.spyOn(slackFaqApi, 'getFaqSchedulerHealth').mockResolvedValue({
      enabled: true,
      status: 'OK',
    })
    renderManager(['/?view=tools'])
    const faqTab = await screen.findByRole('tab', { name: 'integrationsPage.tabSlackFaq' })
    expect(faqTab).toBeInTheDocument()
    await userEvent.click(faqTab)
    expect(await screen.findByTestId('slack-faq-tab', {}, { timeout: 5000 })).toBeInTheDocument()
  })
})

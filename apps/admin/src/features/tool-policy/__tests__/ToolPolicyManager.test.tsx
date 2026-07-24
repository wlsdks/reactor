import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, i18n, render, screen, waitFor } from '../../../test/utils'
import { ToolPolicyManager } from '../ui/ToolPolicyManager'
import * as toolPolicyApi from '../api'
import type { ToolPolicyState } from '../types'

vi.mock('../api', () => ({
  getPolicy: vi.fn(),
  updatePolicy: vi.fn(),
  deletePolicy: vi.fn(),
}))

const getPolicyMock = vi.mocked(toolPolicyApi.getPolicy)
const updatePolicyMock = vi.mocked(toolPolicyApi.updatePolicy)

function buildState(overrides: Partial<ToolPolicyState> = {}): ToolPolicyState {
  return {
    configEnabled: true,
    dynamicEnabled: true,
    effective: {
      enabled: true,
      writeToolNames: ['write_file', 'apply_patch'],
      denyWriteChannels: ['commentary'],
      allowWriteToolNamesInDenyChannels: ['apply_patch'],
      allowWriteToolNamesByChannel: {
        summary: ['write_file'],
      },
      denyWriteMessage: 'Denied',
      createdAt: 1710000000000,
      updatedAt: 1710003600000,
    },
    stored: {
      enabled: true,
      writeToolNames: ['write_file'],
      denyWriteChannels: ['commentary'],
      allowWriteToolNamesInDenyChannels: [],
      allowWriteToolNamesByChannel: {},
      denyWriteMessage: 'Denied',
      createdAt: 1710000000000,
      updatedAt: 1710000000000,
    },
    ...overrides,
  }
}

function renderManager() {
  const router = createMemoryRouter(
    [{ path: '/', element: <ToolPolicyManager /> }],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

describe('ToolPolicyManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'nav.toolPolicy': 'Tool Policy',
      'nav.help.toolPolicy': 'Control which tools are available per channel.',
      'common.refresh': 'Refresh',
      'common.save': 'Save',
      'common.yes': 'yes',
      'common.no': 'no',
      'toolPolicyPage.bannerTitle': 'Tool Policy',
      'toolPolicyPage.lastSync': 'Last successful sync: {{time}}',
      'toolPolicyPage.lastSyncUnknown': 'No successful tool-policy snapshot loaded yet',
      'common.retry': 'Retry',
      'common.retrying': 'Retrying',
      'common.technicalDetails': 'Technical details',
      'toolPolicyPage.refreshFailed': 'Showing the last verified policy.',
      'toolPolicyPage.saveFailed': 'Could not save tool access.',
      'toolPolicyPage.resetFailed': 'Could not reset stored policy.',
      'toolPolicyPage.unavailableTitle': 'Tool access unavailable',
      'toolPolicyPage.unavailableDescription': 'Changes are paused until the current policy can be verified.',
      'toolPolicyPage.accessDeniedTitle': 'Tool access denied',
      'toolPolicyPage.accessDeniedDescription': 'Check your administrator access.',
      'toolPolicyPage.recoveryTitle': 'How to check',
      'toolPolicyPage.recoveryAccount': 'Check account access.',
      'toolPolicyPage.recoveryConnection': 'Check Reactor status.',
      'common.openStatusPage': 'Open status',
      'toolPolicyPage.empty.notAdvertised': 'Tool-policy contract unavailable',
      'toolPolicyPage.empty.accessDenied': 'Tool-policy access denied',
      'toolPolicyPage.empty.transportFailure': 'Tool-policy transport failure',
      'toolPolicyPage.empty.httpError': 'Tool-policy contract unavailable',
      'toolPolicyPage.empty.unknown': 'Tool-policy contract unavailable',
      'toolPolicyPage.emptyDescription': 'Use the recovery runbook before changing write-tool settings from memory.',
      'toolPolicyPage.opsTitle': 'Policy Guardrail Readiness',
      'toolPolicyPage.opsDescription': 'Confirm that the write-tool policy endpoint is reachable, runtime enforcement is active, and overrides are small enough to review safely.',
      'toolPolicyPage.activeWriteToolsCard': 'Write Tools',
      'toolPolicyPage.denyChannelsCard': 'Denied Channels',
      'toolPolicyPage.allowOverridesCard': 'Allow Overrides',
      'toolPolicyPage.diffFieldsCard': 'Drifted Fields',
      'toolPolicyPage.signals.policyContract': 'Policy Contract',
      'toolPolicyPage.signals.runtimeEnforcement': 'Runtime Enforcement',
      'toolPolicyPage.signals.writeCoverage': 'Write Coverage',
      'toolPolicyPage.signals.channelCoverage': 'Channel Coverage',
      'toolPolicyPage.signals.exceptionReview': 'Override Review',
      'toolPolicyPage.signals.storedDrift': 'Stored Drift',
      'toolPolicyPage.signalDetails.contractHealthy': 'The tool-policy endpoint is responding and can be used for live operator checks.',
      'toolPolicyPage.signalDetails.contractMissing': 'The backend is not exposing `/api/tool-policy` in this environment. Confirm feature wiring before relying on the page.',
      'toolPolicyPage.signalDetails.contractDenied': 'The endpoint is reachable, but the caller is not authorized. Review admin credentials and proxy auth settings.',
      'toolPolicyPage.signalDetails.contractTransport': 'The endpoint failed before a response returned. Inspect upstream logs and proxy health before assuming policy state is current.',
      'toolPolicyPage.signalDetails.contractError': 'The endpoint returned an unexpected HTTP error. Treat policy state as degraded until the contract recovers.',
      'toolPolicyPage.signalDetails.runtimeEnforced': 'Write-tool policy is enabled in the current effective runtime.',
      'toolPolicyPage.signalDetails.runtimeDisabled': 'Write-tool policy is disabled in the effective runtime. Mutating tools may no longer be gated.',
      'toolPolicyPage.signalDetails.runtimeConfigFallback': 'Runtime policy is enabled, but the server is falling back to static config instead of a stored operator override.',
      'toolPolicyPage.signalDetails.writeCoverageReady': '{{count}} write tool(s) are explicitly tracked by the effective policy.',
      'toolPolicyPage.signalDetails.writeCoverageMissing': 'No write tools are explicitly listed. Review whether the runtime is depending on broad defaults instead.',
      'toolPolicyPage.signalDetails.channelCoverageReady': '{{count}} deny channel(s) are explicitly blocked by the effective policy.',
      'toolPolicyPage.signalDetails.channelCoverageMissing': 'No deny channels are configured. Confirm whether write tools are intentionally allowed everywhere.',
      'toolPolicyPage.signalDetails.exceptionReviewClean': 'No allow overrides are active in the effective policy.',
      'toolPolicyPage.signalDetails.exceptionReviewNeeded': '{{count}} allow override(s) are active. Reconfirm that each exception is still required.',
      'toolPolicyPage.signalDetails.storedDriftNone': 'Stored policy and effective runtime policy match on the tracked fields.',
      'toolPolicyPage.signalDetails.storedDriftDetected': '{{count}} tracked field(s) differ between stored policy and the effective runtime state.',
      'toolPolicyPage.signalDetails.storedDriftNoStored': 'No stored operator override exists. Runtime policy is coming from baseline config only.',
      'toolPolicyPage.resetStoredPolicy': 'Reset Stored Policy',
      'toolPolicyPage.editorTitle': 'Policy Editor',
      'toolPolicyPage.editorDescription': 'Use stored policy for explicit operator overrides.',
      'toolPolicyPage.configEnabled': 'Config enabled',
      'toolPolicyPage.dynamicEnabled': 'Dynamic enabled',
      'toolPolicyPage.storedPolicy': 'Stored policy',
      'toolPolicyPage.enabled': 'Enabled',
      'toolPolicyPage.writeToolNames': 'Write Tool Names',
      'toolPolicyPage.denyWriteChannels': 'Deny Write Channels',
      'toolPolicyPage.allowWriteToolsInDenyChannels': 'Allow Write Tools In Deny Channels',
      'toolPolicyPage.allowWriteToolsByChannel': 'Allow Write Tools By Channel (JSON)',
      'toolPolicyPage.denyMessage': 'Deny Message',
      'toolPolicyPage.advancedRules': 'Advanced exceptions',
      'toolPolicyPage.advancedRulesDescription': 'Use this only when a channel needs a different exception.',
      'toolPolicyPage.technicalDetails': 'Developer details',
      'toolPolicyPage.technicalDescription': 'Inspect backend policy values only when needed.',
      'toolPolicyPage.maintenance': 'Maintenance',
      'toolPolicyPage.maintenanceDescription': 'Reset the stored override.',
      'toolPolicyPage.help.writeToolNames': 'Tool help',
      'toolPolicyPage.help.denyWriteChannels': 'Channel help',
      'toolPolicyPage.help.allowWriteToolsInDenyChannels': 'Override help',
      'toolPolicyPage.help.allowWriteToolsByChannel': 'JSON help',
      'toolPolicyPage.help.denyMessage': 'Message help',
      'toolPolicyPage.configDiff': 'Config Diff',
      'toolPolicyPage.effectiveRaw': 'Effective Policy (Raw)',
      'toolPolicyPage.storedRaw': 'Stored Policy (Raw)',
      'toolPolicyPage.diffTitle': 'Stored vs Effective Drift',
      'toolPolicyPage.diffDescription': 'These fields differ between the stored operator override and the effective runtime policy.',
      'toolPolicyPage.diffFields.enabled': 'Enabled',
      'toolPolicyPage.diffFields.writeToolNames': 'Write Tool Names',
      'toolPolicyPage.diffFields.denyWriteChannels': 'Deny Write Channels',
      'toolPolicyPage.diffFields.allowWriteToolNamesInDenyChannels': 'Allow Write Tools In Deny Channels',
      'toolPolicyPage.diffFields.allowWriteToolNamesByChannel': 'Allow Write Tools By Channel (JSON)',
      'toolPolicyPage.diffFields.denyWriteMessage': 'Deny Message',
      'toolPolicyPage.effectivePolicyTitle': 'Effective Policy',
      'toolPolicyPage.storedPolicyTitle': 'Stored Policy',
      'toolPolicyPage.validation.allowByChannelObject': 'Allow Write Tools By Channel must be a JSON object',
      'toolPolicyPage.validation.invalidChannelValue': 'Invalid channel value for {{key}}',
    }, true, true)

    getPolicyMock.mockResolvedValue(buildState())
    updatePolicyMock.mockResolvedValue(buildState().effective)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders operator readiness, drift summary, and stored vs effective details', async () => {
    const view = renderManager()

    await waitFor(() => {
      expect(screen.getByText('Policy Guardrail Readiness')).toBeInTheDocument()
    })

    expect(screen.getByText('Config Diff')).toBeInTheDocument()
    expect(screen.getByText('Policy Editor')).toBeInTheDocument()
    expect(screen.getByLabelText('Allow Write Tools In Deny Channels')).toBeInTheDocument()
    expect(screen.getByLabelText(/^Allow Write Tools By Channel \(JSON\)/i)).toBeInTheDocument()
    expect(view.container.querySelector('.safety-policy-overview')).toBeInTheDocument()
    expect(view.container.querySelector('.safety-policy-overview .stat-grid')).not.toBeInTheDocument()
    expect(view.container.querySelector('.safety-policy-overview .safety-policy-state')).toBeInTheDocument()
  })

  it('keeps advanced policy internals and destructive maintenance out of the default editing flow', async () => {
    const view = renderManager()

    await waitFor(() => {
      expect(screen.getByText('Policy Guardrail Readiness')).toBeInTheDocument()
    })

    expect(screen.getByText('Advanced exceptions').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('Developer details').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('Maintenance').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByRole('button', { name: 'Tool help' })).toBeInTheDocument()
    expect(view.container.querySelector('.release-workflow-backlink')).not.toBeInTheDocument()
  })

  it('fails closed without exposing internal recovery instructions when the first load fails', async () => {
    getPolicyMock.mockRejectedValueOnce(new Error('HTTP 404'))

    renderManager()

    expect(await screen.findByRole('heading', { name: 'Tool access unavailable' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Open status' })).toHaveAttribute('href', '/health')
    expect(screen.queryByText('Troubleshooting Guide')).not.toBeInTheDocument()
    expect(screen.queryByText('/api/tool-policy')).not.toBeInTheDocument()
  })

  it('keeps the last successful snapshot visible when refresh fails later', async () => {
    getPolicyMock
      .mockResolvedValueOnce(buildState())
      .mockRejectedValueOnce(new Error('socket hang up'))

    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Policy Editor')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => {
      expect(screen.getByText('Showing the last verified policy.')).toBeInTheDocument()
    })

    const technicalDetails = screen.getByText('Technical details').closest('details')
    expect(technicalDetails).not.toHaveAttribute('open')
    expect(technicalDetails).toHaveTextContent('socket hang up')
    expect(screen.getByText('Config Diff')).toBeInTheDocument()
    expect(screen.getByLabelText('Allow Write Tools In Deny Channels')).toBeInTheDocument()
  })

  it('blocks save when channel overrides JSON is not an object', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Policy Editor')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByLabelText(/^Allow Write Tools By Channel \(JSON\)/i), {
      target: { value: '[]' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(screen.getByText('Allow Write Tools By Channel must be a JSON object')).toBeInTheDocument()
    expect(updatePolicyMock).not.toHaveBeenCalled()
  })
})

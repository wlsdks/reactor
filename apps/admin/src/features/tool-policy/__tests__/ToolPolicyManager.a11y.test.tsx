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

function buildState(): ToolPolicyState {
  return {
    configEnabled: true,
    dynamicEnabled: true,
    effective: {
      enabled: true,
      writeToolNames: ['write_file'],
      denyWriteChannels: [],
      allowWriteToolNamesInDenyChannels: [],
      allowWriteToolNamesByChannel: {},
      denyWriteMessage: 'Denied',
      createdAt: 1710000000000,
      updatedAt: 1710003600000,
    },
    stored: null,
  }
}

function renderManager() {
  const router = createMemoryRouter(
    [{ path: '/', element: <ToolPolicyManager /> }],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

describe('ToolPolicyManager — form a11y', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'nav.toolPolicy': 'Tool Policy',
      'nav.help.toolPolicy': 'help',
      'common.refresh': 'Refresh',
      'common.retry': 'Retry',
      'common.retrying': 'Retrying',
      'common.technicalDetails': 'Technical details',
      'common.save': 'Save',
      'common.yes': 'yes',
      'common.no': 'no',
      'toolPolicyPage.lastSync': 'last sync',
      'toolPolicyPage.lastSyncUnknown': 'unknown',
      'toolPolicyPage.refreshFailed': 'Showing the last verified policy.',
      'toolPolicyPage.saveFailed': 'Could not save tool access.',
      'toolPolicyPage.resetFailed': 'Could not reset stored policy.',
      'toolPolicyPage.editorTitle': 'Policy Editor',
      'toolPolicyPage.editorDescription': 'desc',
      'toolPolicyPage.opsTitle': 'Ops',
      'toolPolicyPage.opsDescription': 'ops desc',
      'toolPolicyPage.activeWriteToolsCard': 'Write Tools',
      'toolPolicyPage.denyChannelsCard': 'Deny Channels',
      'toolPolicyPage.allowOverridesCard': 'Allow Overrides',
      'toolPolicyPage.diffFieldsCard': 'Drifted Fields',
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
      'toolPolicyPage.advancedRulesDescription': 'advanced desc',
      'toolPolicyPage.technicalDetails': 'Developer details',
      'toolPolicyPage.technicalDescription': 'technical desc',
      'toolPolicyPage.maintenance': 'Maintenance',
      'toolPolicyPage.maintenanceDescription': 'maintenance desc',
      'toolPolicyPage.help.writeToolNames': 'Tool help',
      'toolPolicyPage.help.denyWriteChannels': 'Channel help',
      'toolPolicyPage.help.allowWriteToolsInDenyChannels': 'Override help',
      'toolPolicyPage.help.allowWriteToolsByChannel': 'JSON help',
      'toolPolicyPage.help.denyMessage': 'Message help',
      'toolPolicyPage.configDiff': 'Config Diff',
      'toolPolicyPage.effectiveRaw': 'Effective Raw',
      'toolPolicyPage.storedRaw': 'Stored Raw',
      'toolPolicyPage.diffDescription': 'diff',
      'toolPolicyPage.signalDetails.driftNone': 'no drift',
      'toolPolicyPage.resetStoredPolicy': 'Reset Stored Policy',
      'toolPolicyPage.validation.allowByChannelObject': 'Allow Write Tools By Channel must be a JSON object',
      'toolPolicyPage.validation.invalidChannelValue': 'invalid {{key}}',
    }, true, true)

    getPolicyMock.mockResolvedValue(buildState())
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('marks Allow Write Tools By Channel as required + toggles aria-invalid on save failure', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Policy Editor')).toBeInTheDocument()
    })

    const allowByChannel = document.getElementById('policy-allow-by-channel') as HTMLTextAreaElement
    expect(allowByChannel.getAttribute('aria-required')).toBe('true')
    expect(allowByChannel.getAttribute('aria-invalid')).toBe('false')

    // Force a parse error
    fireEvent.change(allowByChannel, { target: { value: '[]' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(screen.getByText('Allow Write Tools By Channel must be a JSON object')).toBeInTheDocument()
      expect(allowByChannel.getAttribute('aria-invalid')).toBe('true')
      expect(allowByChannel.getAttribute('aria-describedby')).toBe('tool-policy-action-error')
    })

    const errEl = document.getElementById('tool-policy-action-error')
    expect(errEl?.getAttribute('role')).toBe('alert')
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n, render, screen, waitFor } from '../../../test/utils'
import { GlobalSettingsModal } from '../ui/GlobalSettingsModal'
import * as mcpSecurityApi from '../../mcp-security'
import type { McpSecurityPolicyState } from '../../mcp-security'

vi.mock('../../mcp-security', () => ({
  getMcpSecurityPolicy: vi.fn(),
  updateMcpSecurityPolicy: vi.fn(),
  deleteMcpSecurityPolicy: vi.fn(),
}))

const getMcpSecurityPolicyMock = vi.mocked(mcpSecurityApi.getMcpSecurityPolicy)

const mockPolicy: McpSecurityPolicyState = {
  effective: {
    allowedServerNames: ['atlassian', 'swagger'],
    maxToolOutputLength: 50000,
    createdAt: 1000,
    updatedAt: 2000,
  },
  stored: {
    allowedServerNames: ['atlassian', 'swagger'],
    maxToolOutputLength: 50000,
    createdAt: 1000,
    updatedAt: 2000,
  },
  configDefault: {
    allowedServerNames: ['atlassian'],
    maxToolOutputLength: 30000,
    createdAt: 0,
    updatedAt: 0,
  },
}

const noop = () => {}

describe('GlobalSettingsModal', () => {
  beforeEach(() => {
    i18n.addResourceBundle(
      'en',
      'translation',
      {
        'common.cancel': 'Cancel',
        'common.confirm': 'Confirm',
        'mcpServers.globalSettings.title': 'Global MCP Settings',
        'mcpServers.globalSettings.securityPolicy': 'Security Policy',
        'mcpServers.globalSettings.outputLimitLabel': 'Max Tool Output Length',
        'mcpServers.globalSettings.outputLimitHint': 'Maximum bytes MCP tools can return (1,024 ~ 500,000)',
        'mcpServers.globalSettings.bulkActions': 'Bulk Security Actions',
        'mcpServers.globalSettings.allowAll': 'Allow All Servers',
        'mcpServers.globalSettings.allowAllDesc': 'Add all registered servers to allowlist',
        'mcpServers.globalSettings.blockAll': 'Block All Servers',
        'mcpServers.globalSettings.blockAllDesc': 'Remove all servers from allowlist',
        'mcpServers.globalSettings.resetDefaults': 'Reset to Defaults',
        'mcpServers.globalSettings.resetDefaultsDesc': 'Restore security policy to config defaults',
        'mcpServers.globalSettings.reset': 'Reset',
        'mcpServers.globalSettings.saveChanges': 'Save Changes',
        'mcpServers.globalSettings.cancel': 'Cancel',
        'mcpServers.confirm.allowAll': 'Allow all registered servers?',
        'mcpServers.confirm.blockAll': 'Block all servers from the allowlist?',
        'mcpServers.confirm.resetDefaults': 'Reset security policy to config defaults?',
        'mcpServers.toast.settingsSaved': 'Global settings saved',
        'mcpServers.toast.allowAll': 'All servers allowed',
        'mcpServers.toast.blockAll': 'All servers blocked',
        'mcpServers.toast.policyReset': 'Security policy reset to defaults',
        'mcpSecurityPage.validation.outputLengthRange': 'Output length must be between 1024 and 500000',
      },
      true,
      true,
    )

    getMcpSecurityPolicyMock.mockResolvedValue(mockPolicy)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when closed', () => {
    render(
      <GlobalSettingsModal open={false} onClose={noop} serverNames={['atlassian']} />,
    )
    expect(screen.queryByText('Global MCP Settings')).not.toBeInTheDocument()
  })

  it('renders title when open', async () => {
    render(
      <GlobalSettingsModal open={true} onClose={noop} serverNames={['atlassian', 'swagger']} />,
    )
    await waitFor(() => {
      expect(screen.getByText(/Global MCP Settings/)).toBeInTheDocument()
    })
  })

  it('renders output limit input', async () => {
    render(
      <GlobalSettingsModal open={true} onClose={noop} serverNames={['atlassian']} />,
    )
    await waitFor(() => {
      expect(screen.getByLabelText('Max Tool Output Length')).toBeInTheDocument()
    })
  })

  it('renders Allow All and Block All buttons', async () => {
    render(
      <GlobalSettingsModal open={true} onClose={noop} serverNames={['atlassian', 'swagger']} />,
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Allow All Servers' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Block All Servers' })).toBeInTheDocument()
    })
  })

  it('renders Reset to Defaults', async () => {
    render(
      <GlobalSettingsModal open={true} onClose={noop} serverNames={['atlassian']} />,
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
    })
  })

  it('calls onClose when Cancel clicked', async () => {
    const onClose = vi.fn()
    render(
      <GlobalSettingsModal open={true} onClose={onClose} serverNames={['atlassian']} />,
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    })

    screen.getByRole('button', { name: 'Cancel' }).click()
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

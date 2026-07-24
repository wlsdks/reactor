import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '../../../test/utils'
import { McpServersListView } from '../ui/McpServersListView'
import * as mcpApi from '../api'
import * as mcpSecurityApi from '../../mcp-security'
import type { McpServerResponse } from '../types'
import type { McpSecurityPolicyState } from '../../mcp-security'

vi.mock('../api', () => ({
  listMcpServers: vi.fn(),
  getMcpServer: vi.fn(),
  connectMcpServer: vi.fn(),
  disconnectMcpServer: vi.fn(),
  emergencyDenyAll: vi.fn(),
  registerMcpServer: vi.fn(),
  updateMcpServer: vi.fn(),
}))

vi.mock('../../mcp-security', () => ({
  getMcpSecurityPolicy: vi.fn(),
  updateMcpSecurityPolicy: vi.fn(),
  deleteMcpSecurityPolicy: vi.fn(),
}))

const listMcpServersMock = vi.mocked(mcpApi.listMcpServers)
const getMcpSecurityPolicyMock = vi.mocked(mcpSecurityApi.getMcpSecurityPolicy)

const mockServers: McpServerResponse[] = [
  {
    id: '1',
    tenantId: 'tenant-1',
    name: 'atlassian',
    status: 'CONNECTED',
    backendStatus: 'healthy',
    command: null,
    url: 'http://localhost:8085/mcp',
    authType: 'none',
    timeoutMs: 15000,
    transportType: 'SSE',
    description: 'Atlassian MCP server',
    autoConnect: true,
    toolCount: 12,
    createdAt: 1710000000000,
    updatedAt: 1710000000000,
  },
  {
    id: '2',
    tenantId: 'tenant-1',
    name: 'swagger',
    status: 'DISCONNECTED',
    backendStatus: 'disabled',
    command: null,
    url: 'http://localhost:8081/mcp',
    authType: 'none',
    timeoutMs: 15000,
    transportType: 'SSE',
    description: 'Swagger MCP server',
    autoConnect: false,
    toolCount: 4,
    createdAt: 1710000000000,
    updatedAt: 1710000000000,
  },
  {
    id: '3',
    tenantId: 'tenant-1',
    name: 'github',
    status: 'FAILED',
    backendStatus: 'degraded',
    command: 'mcp-github',
    url: null,
    authType: 'none',
    timeoutMs: 15000,
    transportType: 'STDIO',
    description: null,
    autoConnect: false,
    toolCount: 0,
    createdAt: 1710000000000,
    updatedAt: 1710000000000,
  },
]

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
    maxToolOutputLength: 50000,
    createdAt: 0,
    updatedAt: 0,
  },
}

function renderListView() {
  const router = createMemoryRouter(
    [
      { path: '/', element: <McpServersListView /> },
      { path: '/mcp-servers/:name', element: <div>Detail</div> },
    ],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

describe('McpServersListView', () => {
  beforeEach(() => {
    listMcpServersMock.mockResolvedValue(mockServers)
    getMcpSecurityPolicyMock.mockResolvedValue(mockPolicy)
    vi.mocked(mcpApi.getMcpServer).mockResolvedValue({
      id: '1',
      tenantId: 'tenant-1',
      name: 'atlassian',
      description: 'Atlassian MCP server',
      transportType: 'SSE',
      config: {},
      version: '1.0.0',
      autoConnect: true,
      status: 'CONNECTED',
      backendStatus: 'healthy',
      command: null,
      url: 'http://localhost:8085/mcp',
      authType: 'none',
      timeoutMs: 15000,
      tools: ['jira_search', 'confluence_search'],
      createdAt: 1710000000000,
      updatedAt: 1710000000000,
    })
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  it('renders page title', async () => {
    renderListView()
    await waitFor(() => {
      expect(screen.getByText('mcpServers.list.title')).toBeInTheDocument()
    })
  })

  it('renders server rows after loading', async () => {
    renderListView()
    await waitFor(() => {
      expect(screen.getByText('Atlassian')).toBeInTheDocument()
    })
    expect(screen.getByText('API 문서 도구')).toBeInTheDocument()
    expect(screen.getByText('GitHub')).toBeInTheDocument()
  })

  it('opens an external tool detail instead of placing connection actions in every table row', async () => {
    renderListView()

    const serverName = await screen.findByText('Atlassian')
    fireEvent.click(serverName)

    expect(await screen.findByText('Detail')).toBeInTheDocument()
    expect(screen.queryByText('mcpServers.list.disconnect')).toBeNull()
    expect(screen.queryByText('mcpServers.list.reconnect')).toBeNull()
  })

  it('renders search input', async () => {
    renderListView()
    await waitFor(() => {
      expect(screen.getByPlaceholderText('mcpServers.list.searchPlaceholder')).toBeInTheDocument()
    })
  })

  it('keeps fleet-wide recovery and blocking controls in a closed maintenance disclosure', async () => {
    renderListView()
    await waitFor(() => {
      expect(screen.getByText('mcpServers.list.connectionActions')).toBeInTheDocument()
    })

    const maintenance = document.querySelector('details.mcp-fleet-maintenance')
    expect(maintenance).toBeInTheDocument()
    expect(maintenance).not.toHaveAttribute('open')
    expect(maintenance).toContainElement(screen.getByText('mcpServers.list.connectAllDisconnected'))
    expect(maintenance).toContainElement(screen.getByText('mcpServers.list.emergencyBlockAll'))
  })

  it('renders summary stat cards', async () => {
    renderListView()
    await waitFor(() => {
      expect(screen.getByText('mcpServers.list.totalServers')).toBeInTheDocument()
    })
    expect(screen.getByText('mcpServers.list.connected')).toBeInTheDocument()
    expect(screen.getByText('mcpServers.list.failed')).toBeInTheDocument()
    expect(screen.getByText('mcpServers.list.blocked')).toBeInTheDocument()
  })

  it('renders correct stat card values', async () => {
    renderListView()
    // Total = 3, Connected = 1, Failed = 1, Blocked = 1 (github not in allowed)
    await waitFor(() => {
      expect(screen.getByText('Atlassian')).toBeInTheDocument()
    })
    // The stat card renders the value as text content
    const values = Array.from(document.querySelectorAll('.mcp-fleet-summary strong')).map((el) => el.textContent)
    expect(values).toContain('3')  // total
    expect(values).toContain('1')  // connected, or failed, or blocked
  })

  it('renders status filter dropdown', async () => {
    renderListView()
    await waitFor(() => {
      expect(screen.getByRole('combobox', { name: 'mcpServers.list.allStatus' })).toBeInTheDocument()
    })
  })

  it('keeps registration as the header action and moves global settings into maintenance', async () => {
    renderListView()
    await waitFor(() => {
      expect(screen.getByText('mcpServers.list.registerServer')).toBeInTheDocument()
    })

    const maintenance = document.querySelector('details.mcp-fleet-maintenance')
    expect(maintenance).toContainElement(screen.getByText('mcpServers.list.globalSettings'))
  })

  it('does not duplicate release-workflow navigation in the page header', async () => {
    renderListView()
    await waitFor(() => {
      expect(screen.getByText('mcpServers.list.globalSettings')).toBeInTheDocument()
    })

    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
  })

  it('shows empty state when no servers', async () => {
    listMcpServersMock.mockResolvedValue([])
    renderListView()
    await waitFor(() => {
      expect(screen.getByText('mcpServers.empty')).toBeInTheDocument()
    })
  })

  it('fails closed when the connection inventory cannot be verified', async () => {
    listMcpServersMock.mockRejectedValue(new Error('backend unavailable'))
    renderListView()

    await waitFor(() => {
      expect(screen.getByText('mcpServers.list.loadErrorTitle')).toBeInTheDocument()
    })
    expect(screen.queryByText('mcpServers.empty')).not.toBeInTheDocument()
    expect(screen.queryByText('mcpServers.list.totalServers')).not.toBeInTheDocument()
    expect(screen.queryByText('mcpServers.list.registerServer')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByText('common.openStatusPage')).toBeInTheDocument()
  })

  it('does not expose unknown backend status or transport identifiers', async () => {
    listMcpServersMock.mockResolvedValue([
      { ...mockServers[0], status: 'NEW_BACKEND_STATE', transportType: 'CUSTOM_PIPE' },
    ])
    renderListView()

    await waitFor(() => {
      expect(screen.getByText('mcpServersPage.connectionStatus.unknown')).toBeInTheDocument()
    })
    expect(screen.getByText('mcpServersPage.transport.unknown')).toBeInTheDocument()
    expect(screen.queryByText('NEW_BACKEND_STATE')).not.toBeInTheDocument()
    expect(screen.queryByText('CUSTOM_PIPE')).not.toBeInTheDocument()
  })
})

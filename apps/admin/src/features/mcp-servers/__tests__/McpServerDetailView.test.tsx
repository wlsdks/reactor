import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '../../../test/utils'
import { McpServerDetailView } from '../ui/McpServerDetailView'
import * as mcpApi from '../api'
import * as mcpSecurityApi from '../../mcp-security'
import type { McpServerDetailResponse } from '../types'
import type { McpSecurityPolicyState } from '../../mcp-security'

vi.mock('../api', () => ({
  getMcpServer: vi.fn(),
  connectMcpServer: vi.fn(),
  disconnectMcpServer: vi.fn(),
  deleteMcpServer: vi.fn(),
  getMcpAccessPolicy: vi.fn(),
  getMcpPreflight: vi.fn(),
  listSwaggerSpecSources: vi.fn(),
  registerMcpServer: vi.fn(),
  updateMcpServer: vi.fn(),
}))

vi.mock('../../mcp-security', () => ({
  getMcpSecurityPolicy: vi.fn(),
  updateMcpSecurityPolicy: vi.fn(),
}))

const getMcpServerMock = vi.mocked(mcpApi.getMcpServer)
const getMcpSecurityPolicyMock = vi.mocked(mcpSecurityApi.getMcpSecurityPolicy)

const mockServerDetail: McpServerDetailResponse = {
  id: '1',
  tenantId: 'tenant-1',
  name: 'atlassian',
  description: 'Atlassian MCP server for Jira, Confluence, and Bitbucket',
  transportType: 'SSE',
  config: {
    url: 'http://localhost:8085/sse',
    adminUrl: 'http://localhost:8085',
    adminToken: 'secret-token-123',
  },
  version: '2.1.0',
  autoConnect: true,
  status: 'CONNECTED',
  backendStatus: 'healthy',
  command: null,
  url: 'http://localhost:8085/sse',
  authType: 'none',
  timeoutMs: 15000,
  tools: ['jira_search', 'confluence_search', 'bitbucket_list_repos', 'work_context'],
  createdAt: 1710000000000,
  updatedAt: 1710100000000,
}

const mockPolicy: McpSecurityPolicyState = {
  effective: {
    allowedServerNames: ['atlassian'],
    maxToolOutputLength: 50000,
    createdAt: 1000,
    updatedAt: 2000,
  },
  stored: {
    allowedServerNames: ['atlassian'],
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

function renderDetailView() {
  const router = createMemoryRouter(
    [
      { path: '/mcp-servers/:name', element: <McpServerDetailView /> },
      { path: '/mcp-servers', element: <div>List Page</div> },
    ],
    { initialEntries: ['/mcp-servers/atlassian'] },
  )
  return render(<RouterProvider router={router} />)
}

describe('McpServerDetailView', () => {
  beforeEach(() => {
    getMcpServerMock.mockResolvedValue(mockServerDetail)
    getMcpSecurityPolicyMock.mockResolvedValue(mockPolicy)
    vi.mocked(mcpApi.getMcpAccessPolicy).mockResolvedValue({
      allowedJiraProjectKeys: ['PROJ'],
      allowedConfluenceSpaceKeys: [],
      allowedBitbucketRepositories: [],
      allowedSourceNames: [],
      allowPreviewReads: false,
      allowPreviewWrites: false,
      allowDirectUrlLoads: false,
      publishedOnly: true,
    })
    vi.mocked(mcpApi.listSwaggerSpecSources).mockResolvedValue([])
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  it('renders server name and status badge', async () => {
    renderDetailView()
    await waitFor(() => {
      expect(screen.getByText('Atlassian')).toBeInTheDocument()
    })
    // Status badge now renders the localized label key (i18n test fixture
    // returns the key string as-is).
    expect(
      screen.getByText('mcpServersPage.connectionStatus.connected'),
    ).toBeInTheDocument()
  })

  it('renders an operator overview and keeps backend identifiers collapsed', async () => {
    renderDetailView()
    await waitFor(() => {
      // Transport now renders the localized label key (i18n test fixture
      // returns the key string as-is).
      expect(screen.getByText('mcpServersPage.transport.sse')).toBeInTheDocument()
    })
    expect(screen.getByText('mcpServers.detail.runtimeStatus.healthy')).toBeInTheDocument()
    expect(screen.queryByText('healthy')).not.toBeInTheDocument()
    const technicalSummary = screen.getByText('mcpServers.detail.technicalDetails')
    expect(technicalSummary).toBeInTheDocument()
    expect(technicalSummary.closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('tenant-1')).toBeInTheDocument()
  })

  it('renders tools list', async () => {
    renderDetailView()
    await waitFor(() => {
      expect(screen.getByText('Jira 검색')).toBeInTheDocument()
    })
    expect(screen.getByText('Confluence 검색')).toBeInTheDocument()
    expect(screen.getByText('Bitbucket 목록 저장소')).toBeInTheDocument()
    expect(screen.getByText('업무 맥락')).toBeInTheDocument()
  })

  it('renders back link to list page', async () => {
    renderDetailView()
    await waitFor(() => {
      expect(screen.getByText(/mcpServers\.detail\.backToList/)).toBeInTheDocument()
    })
  })

  it('renders server description', async () => {
    renderDetailView()
    await waitFor(() => {
      expect(screen.getByText('Jira, Confluence, Bitbucket 업무 도구를 연결합니다.')).toBeInTheDocument()
    })
  })

  it('keeps detailed connection configuration closed and masks sensitive values', async () => {
    renderDetailView()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'mcpServers.detail.configuration' })).toBeInTheDocument()
    })

    const technical = screen.getByText('mcpServers.detail.configurationTechnical')
    expect(technical.closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('mcpServers.detail.connectionTargetLocal')).toBeVisible()
    expect(screen.getByText('http://localhost:8085/sse')).not.toBeVisible()
    expect(screen.queryByText('secret-token-123')).toBeNull()

    fireEvent.click(technical)
    expect(screen.getByText('http://localhost:8085/sse')).toBeVisible()
    expect(screen.getByText('\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022')).toBeVisible()
    expect(screen.queryByText('secret-token-123')).toBeNull()
  })

  it('keeps the raw connection error inside a closed technical disclosure', async () => {
    getMcpServerMock.mockResolvedValue({
      ...mockServerDetail,
      lastConnectionError: 'dial tcp 10.0.0.8: connection refused',
    })
    renderDetailView()

    expect(await screen.findByText('mcpServers.detail.lastConnectionError')).toBeInTheDocument()
    expect(screen.queryByText('dial tcp 10.0.0.8: connection refused')).not.toBeVisible()

    const technicalSummary = document.querySelector('.mcp-runtime-notice__technical summary')
    expect(technicalSummary).toBeTruthy()
    fireEvent.click(technicalSummary!)
    expect(screen.getByText('dial tcp 10.0.0.8: connection refused')).toBeVisible()
  })

  it('renders disconnect button when server is connected', async () => {
    renderDetailView()
    await waitFor(() => {
      expect(screen.getByText('mcpServers.disconnect')).toBeInTheDocument()
    })
  })

  it('renders connect button when server is disconnected', async () => {
    getMcpServerMock.mockResolvedValue({
      ...mockServerDetail,
      status: 'DISCONNECTED',
    })
    renderDetailView()
    await waitFor(() => {
      expect(screen.getByText('mcpServers.connect')).toBeInTheDocument()
    })
  })

  it('renders tool count in the tools heading', async () => {
    renderDetailView()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'mcpServers.detail.tools (4)' })).toBeInTheDocument()
    })
  })

  it('does not duplicate release-workflow navigation in preflight', async () => {
    renderDetailView()
    await waitFor(() => {
      expect(screen.getByText('mcpServers.detail.preflightCheck')).toBeInTheDocument()
    })

    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
  })

  it('fails closed instead of presenting an unavailable detail as an empty connection', async () => {
    getMcpServerMock.mockRejectedValue(new Error('detail unavailable'))
    renderDetailView()

    await waitFor(() => {
      expect(screen.getByText('mcpServers.detail.loadErrorTitle')).toBeInTheDocument()
    })
    expect(screen.queryByText('mcpServers.empty')).not.toBeInTheDocument()
    expect(screen.queryByText('mcpServers.detail.configuration')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})

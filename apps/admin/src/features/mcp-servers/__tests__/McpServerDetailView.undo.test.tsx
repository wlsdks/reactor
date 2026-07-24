import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '../../../test/utils'
import { McpServerDetailView } from '../ui/McpServerDetailView'
import * as mcpApi from '../api'
import * as mcpSecurityApi from '../../mcp-security'
import { useToastStore } from '../../../shared/store/toast.store'
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
const deleteMcpServerMock = vi.mocked(mcpApi.deleteMcpServer)
const getMcpSecurityPolicyMock = vi.mocked(mcpSecurityApi.getMcpSecurityPolicy)

const mockServerDetail: McpServerDetailResponse = {
  id: '1',
  name: 'atlassian',
  description: 'Atlassian MCP server',
  transportType: 'SSE',
  config: { url: 'http://localhost:8085/sse' },
  version: '2.1.0',
  autoConnect: true,
  status: 'CONNECTED',
  tools: ['jira_search'],
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

describe('McpServerDetailView — undoable delete', () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] })
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
    deleteMcpServerMock.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.resetAllMocks()
    useToastStore.setState({ toasts: [] })
  })

  async function openDetailAndConfirmDelete() {
    renderDetailView()
    await waitFor(() => expect(screen.getByText('Atlassian')).toBeInTheDocument())

    // Click the server's "Delete" action button. There may be a row-level
    // actions area; here we use the visible label `mcpServers.detail.delete`
    // which is rendered by the detail view header.
    const deleteBtn = screen.getByText('mcpServers.detail.delete') as HTMLButtonElement
    fireEvent.click(deleteBtn)

    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())

    const confirmBtn = Array.from(
      screen.getByRole('dialog').querySelectorAll('button'),
    ).find((b) => /confirm|확인/i.test(b.textContent ?? '')) as HTMLButtonElement
    fireEvent.click(confirmBtn)
  }

  it('navigates back to the list immediately and shows a toast with an Undo action', async () => {
    await openDetailAndConfirmDelete()

    // Optimistic navigation — list page is rendered.
    await waitFor(() => expect(screen.getByText('List Page')).toBeInTheDocument())

    const undoToast = useToastStore
      .getState()
      .toasts.find((t) => t.action?.label === 'Undo')
    expect(undoToast).toBeDefined()
    expect(undoToast!.message).toContain('Atlassian')
    expect(undoToast!.type).toBe('success')
    expect(deleteMcpServerMock).not.toHaveBeenCalled()

    act(() => {
      undoToast!.action!.onAction()
    })
  }, 15_000)

  it('commits the deletion automatically after the grace window elapses', async () => {
    await openDetailAndConfirmDelete()
    await waitFor(() => expect(screen.getByText('List Page')).toBeInTheDocument())

    expect(deleteMcpServerMock).not.toHaveBeenCalled()

    await waitFor(
      () => {
        // TanStack Query may pass extra context as the second argument; we
        // only care that the API saw the server name as the first arg.
        expect(deleteMcpServerMock).toHaveBeenCalled()
        expect(deleteMcpServerMock.mock.calls[0]?.[0]).toBe('atlassian')
      },
      { timeout: 7_000 },
    )
  }, 15_000)

  it('clicking Undo within the grace window cancels the API call and navigates back to the detail page', async () => {
    await openDetailAndConfirmDelete()
    await waitFor(() => expect(screen.getByText('List Page')).toBeInTheDocument())

    const undoToast = useToastStore
      .getState()
      .toasts.find((t) => t.action?.label === 'Undo')
    expect(undoToast).toBeDefined()

    act(() => {
      undoToast!.action!.onAction()
    })

    // Re-mounted detail view re-fetches; assert the server name is rendered
    // again (i.e. user is back on the detail page).
    await waitFor(() => expect(screen.getByText('Atlassian')).toBeInTheDocument())

    // The API delete must not fire — assert immediately since the grace
    // window has not elapsed yet.
    expect(deleteMcpServerMock).not.toHaveBeenCalled()

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5_100))
    })
    expect(deleteMcpServerMock).not.toHaveBeenCalled()
  }, 15_000)
})

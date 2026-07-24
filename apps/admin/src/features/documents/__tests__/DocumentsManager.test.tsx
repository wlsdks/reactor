import type { ComponentProps } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { DocumentsManager } from '../ui/DocumentsManager'
import * as documentsApi from '../api'
import type { IngestionCandidate, RagIngestionPolicyState } from '../types'
import {
  RELEASE_DOCUMENT_INGESTION_ANCHOR_ID,
  RELEASE_WORKFLOW_PATHS_BY_ID,
} from '../../../shared/releaseWorkflow'

vi.mock('../api', () => ({
  listIngestionCandidates: vi.fn(),
  getRagIngestionPolicy: vi.fn(),
  addDocument: vi.fn(),
  addDocumentsBatch: vi.fn(),
  searchDocuments: vi.fn(),
  deleteDocuments: vi.fn(),
  acceptCandidate: vi.fn(),
  rejectCandidate: vi.fn(),
  updateRagIngestionPolicy: vi.fn(),
  resetRagIngestionPolicy: vi.fn(),
  listDocuments: vi.fn().mockResolvedValue([]),
  seedPolicyDocuments: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    Link: ({ to, ...props }: ComponentProps<typeof actual.Link>) => (
      <a {...props} href={typeof to === 'string' ? to : String(to)} data-router-link="true" />
    ),
  }
})

const listIngestionCandidatesMock = vi.mocked(documentsApi.listIngestionCandidates)
const getRagIngestionPolicyMock = vi.mocked(documentsApi.getRagIngestionPolicy)

function buildCandidate(overrides: Partial<IngestionCandidate> = {}): IngestionCandidate {
  return {
    id: 'cand-1',
    status: 'PENDING',
    channel: 'web',
    query: 'How do I reset my password?',
    response: 'You can reset your password from the account settings page.',
    runId: 'run-1',
    capturedAt: 1704103200000,
    reviewedAt: null,
    reviewedBy: null,
    reviewComment: null,
    ingestedDocumentId: null,
    ...overrides,
  }
}

function buildPolicy(): RagIngestionPolicyState {
  return {
    configEnabled: true,
    dynamicEnabled: true,
    stored: null,
    effective: {
      enabled: true,
      requireReview: true,
      allowedChannels: ['web'],
      minQueryChars: 10,
      minResponseChars: 20,
      blockedPatterns: [],
      createdAt: 1704067200000,
      updatedAt: 1704067200000,
    },
  }
}

function renderManager(initialEntries = ['/']) {
  const router = createMemoryRouter(
    [{ path: '/', element: <DocumentsManager /> }],
    { initialEntries },
  )
  return render(<RouterProvider router={router} />)
}

async function waitForSearchPreload() {
  await waitFor(() => {
    expect(vi.mocked(documentsApi.listDocuments)).toHaveBeenCalledWith(100)
  })
  await waitFor(() => {
    expect(screen.queryByLabelText(/common\.aria\.loading|로딩 중|loading/i)).not.toBeInTheDocument()
  })
}

describe('DocumentsManager', () => {
  beforeEach(() => {
    listIngestionCandidatesMock.mockResolvedValue([buildCandidate()])
    getRagIngestionPolicyMock.mockResolvedValue(buildPolicy())
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders page title and tab buttons on initial render', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    renderManager()
    try {
      await waitForSearchPreload()
      expect(screen.getByText('Documents')).toBeInTheDocument()
      expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' }))
        .not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Refresh' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Bulk seed policy/i })).not.toBeInTheDocument()
      // All five tabs should be visible inside the tabs container
      const tabButtons = screen.getAllByRole('tab')
      expect(tabButtons).toHaveLength(5)
      expect(tabButtons[0]).toHaveTextContent('Search')
      expect(tabButtons[1]).toHaveTextContent('Register')
      expect(tabButtons[2]).toHaveTextContent('Review Queue')
      expect(tabButtons[3]).toHaveTextContent('Policy')
      expect(tabButtons[4]).toHaveTextContent('Analytics')
      expect(consoleError).not.toHaveBeenCalledWith(
        expect.stringContaining('not wrapped in act'),
      )
    } finally {
      consoleError.mockRestore()
    }
  })

  it('shows search tab content by default', async () => {
    const user = userEvent.setup()
    renderManager()
    await waitForSearchPreload()
    // Search tab content is visible by default
    expect(screen.getByText('Knowledge documents')).toBeInTheDocument()
    // Register tab content should NOT be visible
    expect(screen.queryByText('Add Document')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Register document' }))
    expect(screen.getByRole('tab', { name: 'Register' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('Register knowledge document')).toBeInTheDocument()
  })

  it('keeps document scanning separate from detail and technical actions', async () => {
    vi.mocked(documentsApi.listDocuments).mockResolvedValueOnce([
      {
        id: 'doc-cited-1',
        content: 'The password reset policy requires a verified email.',
        metadata: {
          title: 'Password reset policy',
          source: 'handbook.md',
          citation_ids: ['doc-cited-1-0'],
        },
      },
      {
        id: 'doc-weak-1',
        content: 'A weak retrieved chunk without citation metadata.',
        metadata: {
          title: 'Weak retrieval',
        },
      },
    ])

    renderManager()
    await waitFor(() => {
      expect(screen.getByText('Password reset policy')).toBeInTheDocument()
    })

    expect(screen.queryByText('검색 결과 release handoff')).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'ID' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Password reset policy/ }))

    const dialog = await screen.findByRole('dialog', { name: 'Password reset policy' })
    expect(within(dialog).getByText('The password reset policy requires a verified email.')).toBeInTheDocument()
    expect(within(dialog).getByText('handbook.md')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Delete this document' })).toBeInTheDocument()
    expect(within(dialog).getByText('common.technicalDetails')).toBeInTheDocument()
  })

  it('switches to register tab and shows add document form', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'Register' }))

    expect(screen.getByText('Register knowledge document')).toBeInTheDocument()
    expect(screen.getByText('Register multiple documents')).toBeInTheDocument()
    // Search tab content should be hidden
    expect(screen.queryByText('Knowledge documents')).not.toBeInTheDocument()
  })

  it('switches to ingestion tab and shows candidates table after loading', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'Review Queue' }))

    await waitFor(() => {
      expect(screen.getByText('How do I reset my password?')).toBeInTheDocument()
    })
    expect(screen.getAllByText('documentsPage.ingestion.status.pending').length).toBeGreaterThan(0)
  })

  it('opens ingestion tab from a release workflow deep link', async () => {
    renderManager([RELEASE_WORKFLOW_PATHS_BY_ID.ingest.replace('/documents', '/')])

    expect(screen.getByRole('tab', { name: 'Review Queue' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', RELEASE_DOCUMENT_INGESTION_ANCHOR_ID)
    expect(RELEASE_WORKFLOW_PATHS_BY_ID.ingest).toBe(`/documents?tab=ingestion#${RELEASE_DOCUMENT_INGESTION_ANCHOR_ID}`)
    await waitFor(() => {
      expect(screen.getByText('How do I reset my password?')).toBeInTheDocument()
    })
  })

  it('separates queue scanning from candidate review actions', async () => {
    listIngestionCandidatesMock.mockResolvedValueOnce([
      buildCandidate({ id: 'cand-pending', status: 'PENDING' }),
      buildCandidate({ id: 'cand-ingested', status: 'INGESTED', ingestedDocumentId: 'doc-1' }),
      buildCandidate({ id: 'cand-rejected', status: 'REJECTED' }),
    ])

    renderManager([RELEASE_WORKFLOW_PATHS_BY_ID.ingest.replace('/documents', '/')])

    await waitFor(() => {
      expect(screen.getByText('Showing 3 of 3')).toBeInTheDocument()
    })
    expect(screen.queryByText('RAG 릴리즈 handoff')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()

    const pendingRow = screen.getAllByRole('button').find((element) =>
      element.textContent?.includes('documentsPage.ingestion.status.pending') &&
      element.textContent?.includes('How do I reset my password?'),
    )
    expect(pendingRow).toBeDefined()
    await userEvent.click(pendingRow as HTMLElement)

    expect(await screen.findByText('documentsPage.ingestion.reviewTitle')).toBeInTheDocument()
    expect(screen.getByText('You can reset your password from the account settings page.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'documentsPage.ingestion.rejectAction' })).toBeInTheDocument()
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Review Comment' }),
      'Verified for the knowledge base',
    )
    await userEvent.click(screen.getByRole('button', { name: 'documentsPage.ingestion.approveAction' }))

    await waitFor(() => {
      expect(documentsApi.acceptCandidate).toHaveBeenCalledWith(
        'cand-pending',
        'Verified for the knowledge base',
      )
    })
  })

  it('uses readable labels for known collection channels', async () => {
    listIngestionCandidatesMock.mockResolvedValueOnce([
      buildCandidate({ id: 'cand-slack', channel: 'slack' }),
      buildCandidate({ id: 'cand-web', channel: 'web' }),
    ])

    renderManager([RELEASE_WORKFLOW_PATHS_BY_ID.ingest.replace('/documents', '/')])

    expect(await screen.findByText('documentsPage.ingestion.channelLabels.slack')).toBeInTheDocument()
    expect(screen.getByText('documentsPage.ingestion.channelLabels.web')).toBeInTheDocument()
    expect(screen.queryByText('slack', { exact: true })).not.toBeInTheDocument()
    expect(screen.queryByText('web', { exact: true })).not.toBeInTheDocument()
  })

  it('shows empty state for candidates when none exist', async () => {
    listIngestionCandidatesMock.mockResolvedValueOnce([])
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'Review Queue' }))

    await waitFor(() => {
      expect(screen.getByText('No candidates')).toBeInTheDocument()
    })
  })

  it('keeps an unavailable review queue distinct from an empty queue and retries it', async () => {
    listIngestionCandidatesMock.mockRejectedValueOnce(new Error('HTTP 503'))
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'Review Queue' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.queryByText('No candidates')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => {
      expect(screen.getByText('How do I reset my password?')).toBeInTheDocument()
    })
  })

  it('switches to policy tab and shows policy form after loading', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'Policy' }))

    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Collect questions and answers' })).toBeChecked()
    })
    expect(screen.getByRole('switch', { name: 'Review before saving' })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Save collection rules' })).toBeDisabled()
    expect(screen.getByText('Restore default rules').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('Config Enabled').closest('details')).not.toHaveAttribute('open')
  })

  it('shows unavailable message on policy tab when policy API returns 404', async () => {
    getRagIngestionPolicyMock.mockRejectedValueOnce(new Error('HTTP 404'))
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'Policy' }))

    await waitFor(() => {
      expect(screen.getByText('Collection rules are unavailable')).toBeInTheDocument()
    })
  })

  it('shows page subtitle with help text', async () => {
    renderManager()
    await waitForSearchPreload()
    expect(screen.getByText('Manage documents used for knowledge search.')).toBeInTheDocument()
  })

  it('keeps the candidate refresh action with the ingestion queue', async () => {
    renderManager(['/?tab=ingestion'])
    await waitFor(() => {
      expect(screen.getByText('How do I reset my password?')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
  })

  it('exposes the bulk policy action only while editing collection policy', async () => {
    const user = userEvent.setup()
    renderManager()
    await user.click(screen.getByRole('tab', { name: 'Policy' }))
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Collect questions and answers' })).toBeInTheDocument()
    })
    expect(
      screen.getByRole('button', { name: /Bulk seed policy/i }),
    ).toBeInTheDocument()
  })

  it('opens BulkSeedModal from the policy action', async () => {
    const user = userEvent.setup()
    renderManager()
    await user.click(screen.getByRole('tab', { name: 'Policy' }))
    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Collect questions and answers' })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /Bulk seed policy/i }))
    expect(
      await screen.findByRole('dialog', { name: /Bulk seed policy documents/i }),
    ).toBeInTheDocument()
  })

  it('renders the DataTable bulk-action bar in the search tab when a result row is selected', async () => {
    vi.mocked(documentsApi.listDocuments).mockResolvedValueOnce([
      { id: 'doc-1', content: 'Hello', metadata: { title: 'Doc 1' } },
      { id: 'doc-2', content: 'World', metadata: { title: 'Doc 2' } },
    ])
    const { container } = renderManager()
    // Wait for the search-tab DataTable to mount with the seeded docs.
    await waitFor(() => {
      expect(container.querySelector('.data-table')).not.toBeNull()
    })
    const cb = container.querySelector(
      '.data-table-select-cell input[type="checkbox"]',
    ) as HTMLInputElement
    expect(cb).toBeTruthy()
    fireEvent.click(cb)
    await waitFor(() => {
      expect(screen.getByText(/1 selected/)).toBeInTheDocument()
    })
    expect(
      screen.getByRole('button', { name: /Bulk delete/i }),
    ).toBeInTheDocument()
  })
})

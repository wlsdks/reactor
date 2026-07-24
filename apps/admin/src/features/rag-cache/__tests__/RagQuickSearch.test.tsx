import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, i18n } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { RagQuickSearch } from '../ui/RagQuickSearch'
import * as ragCacheApi from '../api'

vi.mock('../api', () => ({
  searchDocuments: vi.fn(),
}))

const searchDocumentsMock = vi.mocked(ragCacheApi.searchDocuments)

const HISTORY_KEY = 'reactor-admin-rag-search-history'

function renderQuickSearch() {
  return render(
    <MemoryRouter>
      <RagQuickSearch />
    </MemoryRouter>,
  )
}

describe('RagQuickSearch', () => {
  beforeEach(() => {
    localStorage.clear()
    i18n.addResourceBundle(
      'en',
      'translation',
      {
        'ragCachePage.quickSearch': 'Quick Search',
        'ragCachePage.searchPlaceholder': 'Enter a query...',
        'ragCachePage.search': 'Search',
        'ragCachePage.resultsFound': '{{count}} results found',
        'ragCachePage.quickSearchExt.description': 'Search registered documents directly.',
        'ragCachePage.quickSearchExt.topK': 'Top-K results',
        'ragCachePage.quickSearchExt.history': 'Recent searches',
        'ragCachePage.quickSearchExt.clearHistory': 'Clear',
        'ragCachePage.quickSearchExt.exportCsv': 'Export CSV',
        'ragCachePage.quickSearchExt.scoreLabel': 'Score',
        'ragCachePage.quickSearchExt.citationEvidence': 'Search result citation evidence',
        'ragCachePage.quickSearchExt.citationIds': 'Citation ID',
        'ragCachePage.quickSearchExt.sourceUri': 'Source URI',
        'ragCachePage.quickSearchExt.documentId': 'Document ID',
        'ragCachePage.quickSearchExt.chunkIndex': 'Chunk',
        'ragCachePage.quickSearchExt.contentHash': 'Content hash',
        'ragCachePage.quickSearchExt.citationReady': 'Ready',
        'ragCachePage.quickSearchExt.citationNeedsReview': 'Needs review',
        'ragCachePage.quickSearchExt.citationMissing': 'Missing citation evidence: {{fields}}',
        'ragCachePage.quickSearchExt.technicalDetails': 'Developer search evidence',
        'ragCachePage.quickSearchExt.resultId': 'Result ID',
        'common.noData': 'No data',
      },
      true,
      true,
    )
  })

  afterEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders input, search button, and topK slider', () => {
    renderQuickSearch()
    expect(screen.getByPlaceholderText('Enter a query...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument()
    expect(screen.getByRole('slider')).toBeInTheDocument()
  })

  it('performs a search and shows results', async () => {
    searchDocumentsMock.mockResolvedValue([
      { id: 'doc-1', content: 'Alpha', metadata: {}, score: 0.92 },
      { id: 'doc-2', content: 'Beta', metadata: {}, score: 0.55 },
    ])
    const user = userEvent.setup()
    renderQuickSearch()

    await user.type(screen.getByPlaceholderText('Enter a query...'), 'hello')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => {
      expect(screen.getByText('2 results found')).toBeInTheDocument()
    })
    expect(searchDocumentsMock).toHaveBeenCalledWith('hello', 5)
  })

  it('surfaces safe citation metadata for cited-answer review', async () => {
    searchDocumentsMock.mockResolvedValue([
      {
        id: 'doc-1',
        content: 'Alpha',
        metadata: {
          citation_ids: ['cite-1', 'cite-2'],
          source_uri: 'kb://policy/alpha',
          document_id: 'document-1',
          chunk_index: 3,
          content_hash: 'sha256:abc',
          acl: 'raw-acl-should-not-render',
        },
        score: 0.92,
      },
    ])
    const user = userEvent.setup()
    renderQuickSearch()

    await user.type(screen.getByPlaceholderText('Enter a query...'), 'hello')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    const details = await screen.findByText('Developer search evidence')
    expect(details.closest('details')).not.toHaveAttribute('open')
    await user.click(details)
    expect(screen.getByText('cite-1, cite-2')).toBeInTheDocument()
    expect(screen.getByText('kb://policy/alpha')).toBeInTheDocument()
    expect(screen.getByText('document-1')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('sha256:abc')).toBeInTheDocument()
    expect(screen.queryByText('raw-acl-should-not-render')).not.toBeInTheDocument()
  })

  it('keeps release navigation out of document-search results', async () => {
    searchDocumentsMock.mockResolvedValue([
      {
        id: 'doc-ready',
        content: 'Ready citation result',
        metadata: {
          citation_ids: ['cite-ready'],
          source_uri: 'kb://policy/ready',
        },
        score: 0.92,
      },
      {
        id: 'doc-weak',
        content: 'Weak citation result',
        metadata: {
          document_id: 'document-weak',
        },
        score: 0.72,
      },
    ])
    const user = userEvent.setup()
    renderQuickSearch()

    await user.type(screen.getByPlaceholderText('Enter a query...'), 'release handoff')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Ready citation result')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Open cited answer contract/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Open feedback promotion/ })).not.toBeInTheDocument()
  })

  it('marks search results that are missing release citation evidence', async () => {
    searchDocumentsMock.mockResolvedValue([
      {
        id: 'doc-weak',
        content: 'Weak citation result',
        metadata: {
          document_id: 'document-weak',
          content_hash: 'sha256:weak',
        },
        score: 0.72,
      },
    ])
    const user = userEvent.setup()
    renderQuickSearch()

    await user.type(screen.getByPlaceholderText('Enter a query...'), 'weak citation')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Needs review')).toBeInTheDocument()
  })

  it('does not search when query is empty', async () => {
    const user = userEvent.setup()
    renderQuickSearch()
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(searchDocumentsMock).not.toHaveBeenCalled()
  })

  it('shows empty state when no results returned', async () => {
    searchDocumentsMock.mockResolvedValue([])
    const user = userEvent.setup()
    renderQuickSearch()
    await user.type(screen.getByPlaceholderText('Enter a query...'), 'empty')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => {
      expect(screen.getByText('No data')).toBeInTheDocument()
    })
  })

  it('changes topK via slider and uses new value in search', async () => {
    searchDocumentsMock.mockResolvedValue([])
    const user = userEvent.setup()
    renderQuickSearch()
    const slider = screen.getByRole('slider') as HTMLInputElement
    // Change slider value
    slider.focus()
    slider.value = '10'
    slider.dispatchEvent(new Event('input', { bubbles: true }))

    await user.type(screen.getByPlaceholderText('Enter a query...'), 'topk')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await waitFor(() => {
      expect(searchDocumentsMock).toHaveBeenCalled()
    })
  })

  it('persists history to localStorage', async () => {
    searchDocumentsMock.mockResolvedValue([
      { id: 'doc-1', content: 'c', metadata: {}, score: 0.9 },
    ])
    const user = userEvent.setup()
    renderQuickSearch()

    await user.type(screen.getByPlaceholderText('Enter a query...'), 'persist me')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => {
      expect(screen.getByText('Recent searches')).toBeInTheDocument()
    })

    const stored = localStorage.getItem(HISTORY_KEY)
    expect(stored).not.toBeNull()
    const parsed = JSON.parse(stored as string) as string[]
    expect(parsed).toContain('persist me')
  })

  it('loads history from localStorage on mount', () => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(['previous query']))
    renderQuickSearch()
    expect(screen.getByRole('button', { name: 'previous query' })).toBeInTheDocument()
  })

  it('clears history when clear button is clicked', async () => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(['q1', 'q2']))
    const user = userEvent.setup()
    renderQuickSearch()

    expect(screen.getByRole('button', { name: 'q1' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear' }))

    expect(screen.queryByRole('button', { name: 'q1' })).not.toBeInTheDocument()
    expect(screen.queryByText('Recent searches')).not.toBeInTheDocument()
  })

  it('runs search when history item is clicked', async () => {
    searchDocumentsMock.mockResolvedValue([
      { id: 'doc-x', content: 'x', metadata: {}, score: 0.7 },
    ])
    localStorage.setItem(HISTORY_KEY, JSON.stringify(['saved q']))
    const user = userEvent.setup()
    renderQuickSearch()

    await user.click(screen.getByRole('button', { name: 'saved q' }))

    await waitFor(() => {
      expect(searchDocumentsMock).toHaveBeenCalledWith('saved q', 5)
    })
  })

  it('shows export CSV button only when results exist', async () => {
    searchDocumentsMock.mockResolvedValue([
      { id: 'doc-1', content: 'abc', metadata: {}, score: 0.9 },
    ])
    const user = userEvent.setup()
    renderQuickSearch()

    expect(screen.queryByRole('button', { name: 'Export CSV' })).not.toBeInTheDocument()

    await user.type(screen.getByPlaceholderText('Enter a query...'), 'abc')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument()
    })
  })

  it('triggers download when export CSV button clicked', async () => {
    searchDocumentsMock.mockResolvedValue([
      { id: 'doc-1', content: 'abc', metadata: {}, score: 0.9 },
    ])
    const originalCreate = URL.createObjectURL
    const originalRevoke = URL.revokeObjectURL
    const createSpy = vi.fn(() => 'blob:mock')
    const revokeSpy = vi.fn()
    URL.createObjectURL = createSpy as unknown as typeof URL.createObjectURL
    URL.revokeObjectURL = revokeSpy as unknown as typeof URL.revokeObjectURL

    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})

    try {
      const user = userEvent.setup()
      renderQuickSearch()
      await user.type(screen.getByPlaceholderText('Enter a query...'), 'abc')
      await user.click(screen.getByRole('button', { name: 'Search' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Export CSV' })).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: 'Export CSV' }))

      expect(createSpy).toHaveBeenCalled()
      expect(clickSpy).toHaveBeenCalled()
      expect(revokeSpy).toHaveBeenCalled()
    } finally {
      URL.createObjectURL = originalCreate
      URL.revokeObjectURL = originalRevoke
      clickSpy.mockRestore()
    }
  })
})

// `buildSearchCsv` was removed as part of the DataTable export unification —
// CSV escaping / header logic now lives in `useTableExport` and is covered by
// `src/shared/lib/__tests__/useTableExport.test.ts`.

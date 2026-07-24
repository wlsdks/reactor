import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import i18n from 'i18next'
import { I18nextProvider, initReactI18next } from 'react-i18next'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import type { PaginatedResponse, SessionRow } from '../types'
import { SessionsFeed } from '../ui/Feed/SessionsFeed'
import { queryKeys } from '../../../shared/lib/queryKeys'

vi.mock('../api', () => ({ listSessionsFeed: vi.fn() }))

const session: SessionRow = {
  sessionId: 'run_ddc0e9a063ab40f4aa73703fb141f96d',
  threadId: 'thread_5de1ac390e3f4ddf',
  traceId: 'trace_c4800bcbe6f54a04',
  userId: 'local-user',
  status: 'completed',
  preview: 'Grounded answer with citations',
  channel: 'api',
  createdAt: Date.parse('2026-07-10T12:20:00Z'),
  updatedAt: Date.parse('2026-07-10T12:23:16Z'),
}

const response: PaginatedResponse<SessionRow> = {
  items: [session], total: 1, offset: 0, limit: 30,
}

const testI18n = i18n.createInstance()
testI18n.use(initReactI18next).init({
  lng: 'en',
  resources: { en: { translation: {
    'conversations.feed.search': 'Search conversations...',
    'conversations.feed.totalCount': '{{count}} sessions',
    'conversations.feed.noResults': 'No matching sessions',
    'conversations.feed.noData': 'No sessions yet',
    'conversations.feed.columns.session': 'Session',
    'conversations.feed.columns.preview': 'Preview',
    'conversations.feed.columns.user': 'User',
    'conversations.feed.columns.status': 'Status',
    'conversations.feed.columns.runtime': 'Runtime',
    'conversations.feed.columns.updatedAt': 'Updated',
    'conversations.status.completed': 'Completed',
    'conversations.users.localUser': 'Local user',
    'conversations.users.anonymousUser': 'User {{id}}',
    'conversations.filters.api': 'API',
    'conversations.revalidation.title': 'Latest session data needs another check',
    'conversations.revalidation.description': 'Showing the last verified records until the connection recovers.',
    'common.noData': 'No data',
  } } },
  interpolation: { escapeValue: false },
})

function renderFeed(initialEntry = '/sessions/feed') {
  const router = createMemoryRouter([
    { path: '/sessions/feed', element: <SessionsFeed /> },
    { path: '/sessions/:sessionId', element: <div>Detail</div> },
  ], { initialEntries: [initialEntry] })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={testI18n}><RouterProvider router={router} /></I18nextProvider>
      </QueryClientProvider>,
    ),
  }
}

describe('SessionsFeed', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listSessionsFeed).mockResolvedValue(response)
  })

  it('renders only backend-supported search and current session fields', async () => {
    renderFeed()
    await waitFor(() => expect(screen.getByText('1 sessions')).toBeInTheDocument())

    expect(screen.getByPlaceholderText('Search conversations...')).toBeInTheDocument()
    expect(screen.getByText('Grounded answer with citations')).toBeInTheDocument()
    expect(screen.getByText('Local user')).toBeInTheDocument()
    expect(screen.queryByText('local-user')).not.toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.queryByText('API')).not.toBeInTheDocument()
    expect(screen.queryByText('#DDC0E9A0')).not.toBeInTheDocument()
    expect(screen.queryByText('#5DE1AC39')).not.toBeInTheDocument()
    expect(screen.queryByText('#C4800BCB')).not.toBeInTheDocument()
    expect(document.querySelectorAll('.badge')).toHaveLength(0)
    expect(screen.queryByRole('button', { name: /channel|trust|feedback|persona/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/msgs/i)).not.toBeInTheDocument()
  })

  it('passes only supported query and pagination parameters', async () => {
    renderFeed('/sessions/feed?q=grounded')
    await waitFor(() => expect(api.listSessionsFeed).toHaveBeenCalledWith(
      { q: 'grounded' }, 0, 30,
    ))
  })

  it('distinguishes unfiltered and searched empty states', async () => {
    vi.mocked(api.listSessionsFeed).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 30 })
    const first = renderFeed()
    await waitFor(() => expect(screen.getByText('No sessions yet')).toBeInTheDocument())
    first.unmount()
    renderFeed('/sessions/feed?q=missing')
    await waitFor(() => expect(screen.getByText('No matching sessions')).toBeInTheDocument())
  })

  it('fails closed without showing an unverified zero count', async () => {
    vi.mocked(api.listSessionsFeed).mockRejectedValue(new Error('HTTP 503'))
    renderFeed()

    await waitFor(() => expect(screen.getByText('conversations.feed.loadErrorTitle')).toBeInTheDocument())
    expect(screen.queryByText('0 sessions')).not.toBeInTheDocument()
    expect(screen.getByText('HTTP 503')).toBeInTheDocument()
  })

  it('keeps the last verified feed visible when a later refresh fails', async () => {
    const view = renderFeed()
    await waitFor(() => expect(screen.getByText('1 sessions')).toBeInTheDocument())

    vi.mocked(api.listSessionsFeed).mockRejectedValueOnce(new Error('HTTP 503'))
    await act(async () => {
      await view.queryClient.invalidateQueries({ queryKey: queryKeys.sessions.feed({ q: undefined, offset: 0 }) })
    })

    await waitFor(() => expect(screen.getByText('Latest session data needs another check')).toBeInTheDocument())
    expect(screen.getByText('Grounded answer with citations')).toBeInTheDocument()
    expect(screen.queryByText('conversations.feed.loadErrorTitle')).not.toBeInTheDocument()
  })
})

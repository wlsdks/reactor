import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { i18n, render, screen, waitFor } from '../../../test/utils'
import { queryKeys } from '../../../shared/lib/queryKeys'
import * as api from '../api'
import { UserSessionsList } from '../ui/Users/UserSessionsList'

vi.mock('../api', () => ({ listUsers: vi.fn(), listUserSessions: vi.fn() }))
vi.mock('../../user-memory', () => ({ UserMemoryTab: ({ userId }: { userId: string }) => <div>Memory for {userId}</div> }))

function renderPage(entry = '/sessions/users/local-user') {
  const router = createMemoryRouter([
    { path: '/sessions/users/:userId', element: <UserSessionsList /> },
    { path: '/sessions/:sessionId', element: <div>Session detail</div> },
  ], { initialEntries: [entry] })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  }
}

describe('UserSessionsList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.addResourceBundle('en', 'translation', {
      'conversations.title': 'Conversations',
      'conversations.users.title': 'Users',
      'conversations.users.tabSessions': 'Sessions',
      'conversations.users.tablistLabel': 'User detail tabs',
      'conversations.users.detailSummary': '{{count}} sessions · Last active {{date}}',
      'conversations.users.detailDescription': 'Review user activity',
      'conversations.users.localUser': 'Local user',
      'conversations.users.anonymousUser': 'User {{id}}',
      'conversations.users.userKey': 'User identifier',
      'conversations.users.sessionsLedger': 'User sessions',
      'conversations.feed.search': 'Search sessions...',
      'conversations.feed.totalCount': '{{count}} sessions',
      'conversations.feed.columns.session': 'Session',
      'conversations.feed.columns.preview': 'Preview',
      'conversations.feed.columns.status': 'Status',
      'conversations.feed.columns.runtime': 'Runtime',
      'conversations.feed.columns.updatedAt': 'Updated',
      'conversations.status.completed': 'Completed',
      'conversations.filters.api': 'API',
      'conversations.revalidation.title': 'Latest session data needs another check',
      'conversations.revalidation.description': 'Showing the last verified sessions until the connection recovers.',
      'userMemoryTab.tabTitle': 'Memory',
      'common.noData': 'No data',
      'common.copy.aria': 'Copy {{label}}',
    }, true, true)
    vi.mocked(api.listUsers).mockResolvedValue({
      items: [{ userId: 'local-user', sessionCount: 1, lastActiveAt: 1 }],
      total: 1, offset: 0, limit: 1,
    })
    vi.mocked(api.listUserSessions).mockResolvedValue({
      items: [{
        sessionId: 'run_1234567890', userId: 'local-user', channel: 'api',
        status: 'completed', preview: 'Grounded answer', traceId: 'trace_abcdef1234', updatedAt: 1,
      }],
      total: 1, offset: 0, limit: 30,
    })
  })

  it('renders the backend-owned session ledger without unsupported filters', async () => {
    renderPage('/sessions/users/local-user?q=grounded')
    await waitFor(() => expect(screen.getByText('Grounded answer')).toBeInTheDocument())

    expect(screen.getByRole('heading', { level: 1, name: 'Local user' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'local-user' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /User identifier/ })).not.toBeInTheDocument()
    expect(screen.queryByText('#12345678')).not.toBeInTheDocument()
    expect(screen.queryByText('#ABCDEF12')).not.toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /channel|trust|persona|feedback/i })).not.toBeInTheDocument()
    expect(api.listUserSessions).toHaveBeenCalledWith('local-user', { q: 'grounded' }, 0, 30)
  })

  it('keeps the memory view URL-addressable', async () => {
    renderPage('/sessions/users/local-user?tab=memory')
    await waitFor(() => expect(screen.getByText('Memory for local-user')).toBeInTheDocument())
    expect(screen.getByRole('tab', { name: 'Memory' })).toHaveAttribute('aria-selected', 'true')
    expect(api.listUserSessions).not.toHaveBeenCalled()
  })

  it('keeps verified sessions visible when later revalidation fails', async () => {
    const view = renderPage()
    await screen.findByText('Grounded answer')

    vi.mocked(api.listUserSessions).mockRejectedValueOnce(new Error('HTTP 503'))
    await act(async () => {
      await view.queryClient.invalidateQueries({
        queryKey: queryKeys.sessions.userSessions('local-user', { q: undefined, offset: 0 }),
      })
    })

    await waitFor(() => expect(screen.getByText('Latest session data needs another check')).toBeInTheDocument())
    expect(screen.getByText('Grounded answer')).toBeInTheDocument()
    expect(screen.queryByText('conversations.feed.loadErrorTitle')).not.toBeInTheDocument()
  })
})

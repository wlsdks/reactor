import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { i18n, render, screen, waitFor } from '../../../test/utils'
import { queryKeys } from '../../../shared/lib/queryKeys'
import * as sessionsApi from '../api'
import { UsersList } from '../ui/Users/UsersList'

vi.mock('../api', () => ({ listUsers: vi.fn(), listUserSessions: vi.fn() }))

function renderUsersList(initialEntry = '/sessions/users') {
  const router = createMemoryRouter([
    { path: '/sessions/users', element: <UsersList /> },
    { path: '/sessions/users/:userId', element: <div>User detail</div> },
  ], { initialEntries: [initialEntry] })
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

describe('UsersList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.addResourceBundle('en', 'translation', {
      'conversations.users.search': 'Search users...',
      'conversations.users.userCount': '{{count}} users',
      'conversations.users.noUsers': 'No users',
      'conversations.users.localUser': 'Local user',
      'conversations.users.anonymousUser': 'User {{id}}',
      'conversations.users.columns.user': 'User',
      'conversations.users.columns.sessions': 'Sessions',
      'conversations.users.columns.lastActive': 'Last active',
      'conversations.users.columns.lastSession': 'Last session',
      'conversations.revalidation.title': 'Latest user data needs another check',
      'conversations.revalidation.description': 'Showing the last verified users until the connection recovers.',
      'common.noData': 'No data',
    }, true, true)
    vi.mocked(sessionsApi.listUsers).mockResolvedValue({
      items: [{
        userId: 'local-user',
        sessionCount: 2,
        lastActiveAt: Date.parse('2026-07-10T12:23:16Z'),
        lastSessionId: 'run_ddc0e9a063ab40f4aa73703fb141f96d',
      }],
      total: 1, offset: 0, limit: 30,
    })
  })

  it('renders the current backend user summary without invented metrics', async () => {
    renderUsersList()
    await waitFor(() => expect(screen.getByText('1 users')).toBeInTheDocument())

    expect(screen.getByPlaceholderText('Search users...')).toBeInTheDocument()
    expect(screen.getByText('Local user')).toBeInTheDocument()
    expect(screen.queryByText('#DDC0E9A0')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByText(/messages|trust issues/i)).not.toBeInTheDocument()
  })

  it('sends only the supported user query and pagination fields', async () => {
    renderUsersList('/sessions/users?users_q=local')
    await waitFor(() => expect(sessionsApi.listUsers).toHaveBeenCalledWith({
      q: 'local', offset: 0, limit: 30,
    }))
  })

  it('fails closed without showing an unverified zero count', async () => {
    vi.mocked(sessionsApi.listUsers).mockRejectedValue(new Error('HTTP 503'))
    renderUsersList()

    await waitFor(() => expect(screen.getByText('conversations.users.loadErrorTitle')).toBeInTheDocument())
    expect(screen.queryByText('0 users')).not.toBeInTheDocument()
    expect(screen.getByText('HTTP 503')).toBeInTheDocument()
  })

  it('keeps verified users visible when later revalidation fails', async () => {
    const view = renderUsersList()
    await screen.findByText('1 users')

    vi.mocked(sessionsApi.listUsers).mockRejectedValueOnce(new Error('HTTP 503'))
    await act(async () => {
      await view.queryClient.invalidateQueries({ queryKey: queryKeys.sessions.users({ q: '', offset: 0 }) })
    })

    await waitFor(() => expect(screen.getByText('Latest user data needs another check')).toBeInTheDocument())
    expect(screen.getByText('Local user')).toBeInTheDocument()
    expect(screen.queryByText('conversations.users.loadErrorTitle')).not.toBeInTheDocument()
  })
})

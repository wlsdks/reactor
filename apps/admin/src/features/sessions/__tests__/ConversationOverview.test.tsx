import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from 'i18next'
import { I18nextProvider, initReactI18next } from 'react-i18next'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { queryKeys } from '../../../shared/lib/queryKeys'
import * as sessionsApi from '../api'
import type { ConversationOverview as ConversationOverviewData } from '../types'
import { ConversationOverview } from '../ui/Overview/ConversationOverview'

const overview: ConversationOverviewData = {
  totalSessions: 150,
  activeUsers: 20,
  statusCounts: { completed: 145, failed: 5 },
}

const testI18n = i18n.createInstance()
testI18n.use(initReactI18next).init({
  lng: 'en',
  fallbackLng: 'en',
  resources: {
    en: {
      translation: {
        'conversations.overview.totalSessions': 'Total sessions',
        'conversations.overview.activeUsers': 'Active users',
        'conversations.overview.completed': 'Completed',
        'conversations.overview.needsAttention': 'Needs attention',
        'conversations.overview.summaryLabel': 'Conversation operations summary',
        'conversations.overview.periodLabel': 'Period',
        'conversations.overview.shortcutsLabel': 'Conversation shortcuts',
        'conversations.overview.viewSessions': 'Review all sessions',
        'conversations.overview.viewUsers': 'Review user activity',
        'conversations.overview.loadErrorTitle': 'Failed to load',
        'conversations.overview.loadErrorDescription': 'Check the overview API and retry.',
        'conversations.overview.noData': 'No conversation data yet',
        'conversations.overview.noDataDescription': 'Conversations will appear here once users start chatting.',
        'conversations.period.7d': 'Last 7 days',
        'conversations.period.30d': 'Last 30 days',
        'conversations.period.90d': 'Last 90 days',
        'conversations.revalidation.title': 'Latest session data needs another check',
        'conversations.revalidation.description': 'Showing the last verified records until the connection recovers.',
        'conversations.recovery.title': 'Recovery steps',
        'conversations.recovery.account': 'Check access',
        'conversations.recovery.connection': 'Check connection',
        'common.retry': 'Retry',
        'common.loading': 'Loading',
        'common.openStatusPage': 'Open status',
        'common.technicalDetails': 'Technical details',
      },
    },
  },
  interpolation: { escapeValue: false },
})

vi.mock('../api', () => ({ getConversationOverview: vi.fn() }))

function renderOverview() {
  const router = createMemoryRouter([
    { path: '/', element: <ConversationOverview /> },
    { path: '/sessions/feed', element: <div>Feed</div> },
    { path: '/sessions/users', element: <div>Users</div> },
  ], { initialEntries: ['/'] })
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

describe('ConversationOverview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(sessionsApi.getConversationOverview).mockResolvedValue(overview)
  })

  it('renders one compact summary from the current backend contract', async () => {
    renderOverview()

    await waitFor(() => expect(screen.getByText('Total sessions')).toBeInTheDocument())

    expect(screen.getByText('150')).toBeInTheDocument()
    expect(screen.getByText('20')).toBeInTheDocument()
    expect(screen.getByText('145')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0)
    expect(document.querySelector('.overview-charts-row')).not.toBeInTheDocument()
    expect(document.querySelector('.overview-cards-row')).not.toBeInTheDocument()
    expect(document.querySelector('.overview-lists-row')).not.toBeInTheDocument()
  })

  it('keeps the two supported operational destinations available', async () => {
    renderOverview()

    await screen.findByRole('button', { name: 'Review all sessions' })
    expect(screen.getByRole('button', { name: 'Review user activity' })).toBeInTheDocument()
  })

  it('shows loading skeletons before the overview resolves', () => {
    vi.mocked(sessionsApi.getConversationOverview).mockReturnValue(new Promise(() => {}))
    renderOverview()
    expect(document.querySelectorAll('.overview-skeleton').length).toBeGreaterThan(0)
  })

  it('fails closed without leaving inactive controls in the surface', async () => {
    vi.mocked(sessionsApi.getConversationOverview).mockRejectedValue(new Error('Network error'))
    renderOverview()

    await waitFor(() => expect(screen.getByText('Failed to load')).toBeInTheDocument())
    expect(screen.getByText('Retry')).toBeInTheDocument()
    expect(screen.queryByText('Period')).not.toBeInTheDocument()
  })

  it('keeps verified summary data visible when later revalidation fails', async () => {
    const view = renderOverview()
    await screen.findByText('Total sessions')

    vi.mocked(sessionsApi.getConversationOverview).mockRejectedValueOnce(new Error('Network error'))
    await act(async () => {
      await view.queryClient.invalidateQueries({ queryKey: queryKeys.sessions.overview('7d') })
    })

    await waitFor(() => expect(screen.getByText('Latest session data needs another check')).toBeInTheDocument())
    expect(screen.getByText('150')).toBeInTheDocument()
    expect(screen.queryByText('Failed to load')).not.toBeInTheDocument()
  })

  it('requests the selected supported period', async () => {
    renderOverview()
    await screen.findByText('Period')

    fireEvent.change(screen.getByRole('combobox'), { target: { value: '30d' } })

    await waitFor(() => expect(sessionsApi.getConversationOverview).toHaveBeenCalledWith('30d'))
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n from 'i18next'
import { I18nextProvider, initReactI18next } from 'react-i18next'
import { SessionDetail } from '../ui/Detail/SessionDetail'
import type { SessionDetailData } from '../types'

vi.mock('../api', () => ({
  getAdminSessionDetail: vi.fn(),
  deleteAdminSession: vi.fn(),
  exportAdminSession: vi.fn(),
  addSessionTag: vi.fn(),
  removeSessionTag: vi.fn(),
}))

import * as api from '../api'

const testI18n = i18n.createInstance()
testI18n.use(initReactI18next).init({
  lng: 'en',
  fallbackLng: 'en',
  resources: {
    en: {
      translation: {
        'conversations.title': 'Conversations',
        'conversations.detail.title': 'Conversation Detail',
        'conversations.detail.flag': 'Flag',
        'conversations.detail.export': 'Export',
        'conversations.detail.exportJson': 'Export JSON',
        'conversations.detail.exportMarkdown': 'Export Markdown',
        'conversations.detail.openInspector': 'Open in Inspector',
        'conversations.detail.delete': 'Delete',
        'conversations.detail.deleteConfirm': 'Delete session {{sessionId}}? This action cannot be undone.',
        'conversations.detail.messages': '{{count}} messages',
        'conversations.detail.duration': '{{duration}}',
        'conversations.detail.endOfConversation': 'End of conversation',
        'conversations.detail.loadOlder': 'Load older messages',
        'conversations.detail.showingMessages': 'Showing latest {{shown}} of {{total}} messages',
        'conversations.users.anonymousUser': 'User {{id}}',
        'conversations.tags.addTag': 'Add tag',
        'conversations.tags.tagLabel': 'Tag label',
        'conversations.tags.comment': 'Comment (optional)',
        'conversations.tags.save': 'Save',
        'conversations.tags.cancel': 'Cancel',
        'common.cancel': 'Cancel',
        'common.confirm': 'Confirm',
      },
    },
  },
  interpolation: { escapeValue: false },
})

// ---------------------------------------------------------------------------
// Inline test data (replaces deleted mock.ts)
// ---------------------------------------------------------------------------

const testSessionId = 'sess_test_001'

const mockDetail: SessionDetailData = {
  sessionId: testSessionId,
  userId: 'user_001',
  channel: 'web',
  personaId: 'p1',
  personaName: 'Default',
  model: null,
  messageCount: 3,
  duration: 60000,
  startedAt: Date.now() - 3600000,
  lastActivity: Date.now(),
  trust: 'clean',
  feedback: 'positive',
  tags: [],
  messages: [
    { id: 1, role: 'user', content: 'Hello', timestamp: Date.now() - 3600000 },
    { id: 2, role: 'assistant', content: 'Hi there!', timestamp: Date.now() - 3598000, model: 'gpt-4', durationMs: 1500 },
    { id: 3, role: 'user', content: 'Thanks', timestamp: Date.now() - 3595000 },
  ],
}

function renderDetail(initialEntries?: string[]) {
  vi.mocked(api.getAdminSessionDetail).mockResolvedValue(mockDetail)

  const router = createMemoryRouter(
    [
      { path: '/sessions/:sessionId', element: <SessionDetail /> },
      { path: '/sessions', element: <div>Sessions Overview</div> },
      { path: '/sessions/feed', element: <div>Sessions Feed</div> },
      { path: '/chat-inspector', element: <div>Chat Inspector</div> },
    ],
    { initialEntries: initialEntries ?? [`/sessions/${testSessionId}`] },
  )

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={testI18n}>
        <RouterProvider router={router} />
      </I18nextProvider>
    </QueryClientProvider>,
  )
}

describe('SessionDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders breadcrumb with link to Conversations', async () => {
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('Conversations')).toBeInTheDocument()
    })

    const link = screen.getByRole('link', { name: 'Conversations' })
    expect(link).toHaveAttribute('href', '/sessions')
  })

  it('renders a readable owner label instead of the raw account key', async () => {
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('User 001')).toBeInTheDocument()
    })
    expect(screen.queryByText(mockDetail.userId)).not.toBeInTheDocument()
  })

  it('renders session info bar with channel icon', async () => {
    const { container } = renderDetail()

    await waitFor(() => {
      const channelIcon = container.querySelector('.channel-icon')
      expect(channelIcon).not.toBeNull()
      expect(channelIcon).toBeInTheDocument()
    })
  })

  it('renders chat bubbles for messages', async () => {
    renderDetail()

    await waitFor(() => {
      // The visible messages show the last 50 (or all if fewer than 50)
      const visibleCount = Math.min(50, mockDetail.messages.length)
      const visibleMessages = mockDetail.messages.slice(-visibleCount)
      // Check that at least the first visible message content is rendered
      expect(screen.getByText(visibleMessages[0].content)).toBeInTheDocument()
    })
  })

  it('renders trust tag', async () => {
    renderDetail()

    await waitFor(() => {
      // Trust tag should show based on mockDetail.trust status
      const trustTag = screen.getByText(/clean|flagged|blocked/i)
      expect(trustTag).toBeInTheDocument()
    })
  })

  it('shows "End of conversation" marker', async () => {
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('End of conversation')).toBeInTheDocument()
    })
  })

  it('shows "Load older messages" button when messages > 50', async () => {
    // Find a session with more than 50 messages or create mock with many messages
    const manyMessagesDetail = {
      ...mockDetail,
      messages: Array.from({ length: 60 }, (_, i) => ({
        id: i + 1,
        role: i % 2 === 0 ? 'user' as const : 'assistant' as const,
        content: `Message ${i + 1}`,
        timestamp: Date.now() + i * 1000,
      })),
    }

    vi.mocked(api.getAdminSessionDetail).mockResolvedValue(manyMessagesDetail)

    const router = createMemoryRouter(
      [
        { path: '/sessions/:sessionId', element: <SessionDetail /> },
        { path: '/sessions', element: <div>Sessions Overview</div> },
      ],
      { initialEntries: [`/sessions/${testSessionId}`] },
    )

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <I18nextProvider i18n={testI18n}>
          <RouterProvider router={router} />
        </I18nextProvider>
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(screen.getByText('Load older messages')).toBeInTheDocument()
    })

    // Showing count text
    expect(screen.getByText('Showing latest 50 of 60 messages')).toBeInTheDocument()
  })

  it('does not show "Load older messages" when messages <= 50', async () => {
    // mockDetail has between 5-30 messages (deterministic from seed)
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('End of conversation')).toBeInTheDocument()
    })

    expect(screen.queryByText('Load older messages')).not.toBeInTheDocument()
  })

  it('keeps secondary and destructive actions closed until the operator asks for them', async () => {
    const { container } = renderDetail()

    await waitFor(() => {
      expect(screen.getByText('Open in Inspector')).toBeInTheDocument()
    })

    const actions = container.querySelector('.session-info-bar__actions')
    expect(actions).not.toBeNull()
    expect(actions).not.toHaveAttribute('open')
    expect(screen.getByText('conversations.detail.actions.more')).toBeInTheDocument()
  })

  it('shows delete confirm dialog when delete is clicked', async () => {
    const user = userEvent.setup()
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('conversations.detail.actions.more')).toBeInTheDocument()
    })

    await user.click(screen.getByText('conversations.detail.actions.more'))
    await user.click(screen.getByText('Delete'))

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  it('shows export dropdown with JSON and Markdown options', async () => {
    const user = userEvent.setup()
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('conversations.detail.actions.more')).toBeInTheDocument()
    })

    await user.click(screen.getByText('conversations.detail.actions.more'))
    // Click the Export dropdown toggle button.
    await user.click(screen.getByText(/^Export/))

    await waitFor(() => {
      expect(screen.getByText('Export JSON')).toBeInTheDocument()
      expect(screen.getByText('Export Markdown')).toBeInTheDocument()
    })
  })

  it('renders message count in info bar', async () => {
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText(`${mockDetail.messageCount} messages`)).toBeInTheDocument()
    })
  })

  it('uses the single flag action as the tag-entry trigger', async () => {
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('conversations.detail.actions.more')).toBeInTheDocument()
    })
  })

  it('shows tag form when the flag action is clicked', async () => {
    const user = userEvent.setup()
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('conversations.detail.actions.more')).toBeInTheDocument()
    })

    await user.click(screen.getByText('conversations.detail.actions.more'))
    await user.click(screen.getByText('Flag'))

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Tag label')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('Comment (optional)')).toBeInTheDocument()
    })
  })

  it('keeps messages ahead of tags and omits empty runtime metadata', async () => {
    const { container } = renderDetail()

    await waitFor(() => {
      expect(screen.getByText('Hello')).toBeInTheDocument()
    })

    const messages = container.querySelector('#session-section-messages')
    const tags = container.querySelector('#session-section-tags')
    expect(messages).not.toBeNull()
    expect(tags).not.toBeNull()
    expect(messages!.compareDocumentPosition(tags!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(container.querySelector('.session-runtime')).toBeNull()
  })
})

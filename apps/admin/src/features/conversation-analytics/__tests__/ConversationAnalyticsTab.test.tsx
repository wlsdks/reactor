import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '../../../test/utils'
import { ConversationAnalyticsTab } from '../ui/ConversationAnalyticsTab'
import * as api from '../api'
import type { ChannelConversationStats, FailurePattern, LatencyBucket } from '../types'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getConversationsByChannel: vi.fn(),
    getFailurePatterns: vi.fn(),
    getLatencyDistribution: vi.fn(),
  }
})

const getByChannelMock = vi.mocked(api.getConversationsByChannel)
const getFailureMock = vi.mocked(api.getFailurePatterns)
const getLatencyMock = vi.mocked(api.getLatencyDistribution)

const mockChannelStats: ChannelConversationStats[] = [
  { channel: 'web', total: 1250, success: 1100, failure: 150, successRate: 88.0, avgDurationMs: 1200 },
  { channel: 'slack', total: 860, success: 810, failure: 50, successRate: 94.2, avgDurationMs: 980 },
]

const mockFailures: FailurePattern[] = [
  { errorClass: 'LLM_TIMEOUT', count: 85, latest: '2026-04-05T12:30:00Z' },
  { errorClass: 'CONTEXT_OVERFLOW', count: 42, latest: '2026-04-05T11:00:00Z' },
]

const mockBuckets: LatencyBucket[] = [
  { bucket: '< 1s', count: 820 },
  { bucket: '1-3s', count: 1450 },
  { bucket: '3-5s', count: 380 },
  { bucket: '5-10s', count: 120 },
  { bucket: '> 10s', count: 30 },
]

describe('ConversationAnalyticsTab', () => {
  beforeEach(() => {
    getByChannelMock.mockResolvedValue(mockChannelStats)
    getFailureMock.mockResolvedValue(mockFailures)
    getLatencyMock.mockResolvedValue(mockBuckets)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders stat cards', async () => {
    render(<ConversationAnalyticsTab />)
    await waitFor(() => {
      expect(screen.getByText(/conversationAnalyticsTab\.totalConversations/i)).toBeInTheDocument()
      expect(screen.getByText(/conversationAnalyticsTab\.successRate/i)).toBeInTheDocument()
      expect(screen.getByText(/conversationAnalyticsTab\.avgLatency/i)).toBeInTheDocument()
      expect(screen.getByText(/conversationAnalyticsTab\.failures/i)).toBeInTheDocument()
    })
  })

  it('renders failure pattern table', async () => {
    render(<ConversationAnalyticsTab />)
    await waitFor(() => {
      expect(screen.getByText('conversationAnalyticsTab.failureTypes.llmTimeout')).toBeInTheDocument()
      expect(screen.getByText('conversationAnalyticsTab.failureTypes.contextOverflow')).toBeInTheDocument()
      expect(screen.queryByText('LLM_TIMEOUT')).not.toBeInTheDocument()
      expect(screen.queryByText('CONTEXT_OVERFLOW')).not.toBeInTheDocument()
    })
  })

  it('distinguishes a loading failure from an empty analytics period', async () => {
    getByChannelMock.mockRejectedValue(new Error('offline'))
    getFailureMock.mockRejectedValue(new Error('offline'))
    getLatencyMock.mockRejectedValue(new Error('offline'))

    render(<ConversationAnalyticsTab />)

    await waitFor(() => {
      expect(screen.getByText('conversationAnalyticsTab.loadErrorTitle')).toBeInTheDocument()
      expect(screen.getByText('conversationAnalyticsTab.loadErrorDescription')).toBeInTheDocument()
      expect(screen.queryByText('conversationAnalyticsTab.emptyTitle')).not.toBeInTheDocument()
    })
  })

  it('makes a partial loading failure visible while preserving the available data', async () => {
    getFailureMock.mockRejectedValue(new Error('offline'))

    render(<ConversationAnalyticsTab />)

    await waitFor(() => {
      expect(screen.getByText('conversationAnalyticsTab.partialErrorTitle')).toBeInTheDocument()
      expect(screen.getByText('conversationAnalyticsTab.totalConversations')).toBeInTheDocument()
    })
  })

  it('does not mistake a partial loading failure for an empty period', async () => {
    getByChannelMock.mockRejectedValue(new Error('offline'))
    getFailureMock.mockResolvedValue([])
    getLatencyMock.mockResolvedValue([])

    render(<ConversationAnalyticsTab />)

    await waitFor(() => {
      expect(screen.getByText('conversationAnalyticsTab.partialErrorTitle')).toBeInTheDocument()
      expect(screen.queryByText('conversationAnalyticsTab.emptyTitle')).not.toBeInTheDocument()
    })
  })

  it('renders latency distribution', async () => {
    render(<ConversationAnalyticsTab />)
    await waitFor(() => {
      expect(screen.getByText('< 1s')).toBeInTheDocument()
      expect(screen.getByText('1-3s')).toBeInTheDocument()
      expect(screen.getByText('> 10s')).toBeInTheDocument()
    })
  })

  it('renders chart region', async () => {
    render(<ConversationAnalyticsTab />)
    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'conversationAnalyticsTab.channelTrend' })).toBeInTheDocument()
    })
  })

  it('renders days selector buttons', async () => {
    render(<ConversationAnalyticsTab />)
    await waitFor(() => {
      expect(screen.getByText('conversationAnalyticsTab.title')).toBeInTheDocument()
    })
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen, i18n } from '../../../test/utils'
import { RagCacheInsightBar } from '../ui/RagCacheInsightBar'
import type { CacheStats, VectorStoreStats, RagPolicyState } from '../types'

function buildCacheStats(overrides: Partial<CacheStats> = {}): CacheStats {
  return {
    enabled: true,
    semanticEnabled: true,
    totalExactHits: 100,
    totalSemanticHits: 50,
    totalMisses: 50,
    hitRate: 0.243,
    config: {
      ttlMinutes: 60,
      maxSize: 1000,
      similarityThreshold: 0.85,
      maxCandidates: 10,
      cacheableTemperature: 0.3,
    },
    ...overrides,
  }
}

function buildVectorStoreStats(overrides: Partial<VectorStoreStats> = {}): VectorStoreStats {
  return {
    available: true,
    documentCount: 1247,
    ...overrides,
  }
}

function buildRagPolicy(overrides?: { enabled?: boolean }): RagPolicyState {
  return {
    configEnabled: true,
    dynamicEnabled: true,
    effective: {
      enabled: overrides?.enabled ?? true,
      requireReview: true,
      allowedChannels: [],
      minQueryChars: 10,
      minResponseChars: 20,
      blockedPatterns: [],
    },
    stored: null,
  }
}

describe('RagCacheInsightBar', () => {
  beforeEach(() => {
    i18n.addResourceBundle(
      'en',
      'translation',
      {
        'ragCachePage.insightBar.statusOk': 'System healthy',
        'ragCachePage.insightBar.statusWarning': 'Attention needed',
        'ragCachePage.insightBar.statusError': 'Error',
        'ragCachePage.insightBar.statusUnknown': 'Status unavailable',
        'ragCachePage.insightBar.cacheLabel': 'Cache',
        'ragCachePage.insightBar.ragDocsLabel': 'RAG docs',
        'ragCachePage.insightBar.pendingLabel': 'Pending',
        'ragCachePage.insightBar.reviewQueueLabel': 'Review pending',
        'ragCachePage.insightBar.reviewQueueTitle': 'Open Review Queue tab',
        'ragCachePage.insightBar.reviewQueueAriaLabel': 'Open Review Queue tab ({{count}} pending)',
        'ragCachePage.insightBar.noPending': 'No pending reviews',
      },
      true,
      true,
    )
  })

  it('renders status dot and metric labels', () => {
    render(
      <RagCacheInsightBar
        cacheStats={buildCacheStats()}
        vectorStoreStats={buildVectorStoreStats()}
        ragPolicy={buildRagPolicy()}
        pendingCandidatesCount={0}
        onJumpToCandidates={vi.fn()}
      />,
    )

    expect(screen.getByText('System healthy')).toBeInTheDocument()
    expect(screen.getByText('Cache')).toBeInTheDocument()
    expect(screen.getByText('RAG docs')).toBeInTheDocument()
    expect(screen.getByText('Pending')).toBeInTheDocument()
    expect(screen.getByText('24.3%')).toBeInTheDocument()
    expect(screen.getByText('1,247')).toBeInTheDocument()
  })

  it('renders em-dash placeholders when data is null', () => {
    render(
      <RagCacheInsightBar
        cacheStats={null}
        vectorStoreStats={null}
        ragPolicy={null}
        pendingCandidatesCount={0}
        onJumpToCandidates={vi.fn()}
      />,
    )

    const emDashes = screen.getAllByText('—')
    // Cache hit rate + RAG docs = 2 placeholders
    expect(emDashes.length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('Status unavailable')).toBeInTheDocument()
  })

  it('shows the review-queue CTA button when pending count > 0', () => {
    render(
      <RagCacheInsightBar
        cacheStats={buildCacheStats()}
        vectorStoreStats={buildVectorStoreStats()}
        ragPolicy={buildRagPolicy()}
        pendingCandidatesCount={3}
        onJumpToCandidates={vi.fn()}
      />,
    )

    // aria-label takes precedence over visible text for role-based name queries.
    const cta = screen.getByRole('button', { name: 'Open Review Queue tab (3 pending)' })
    expect(cta).toBeInTheDocument()
    // The count is already present in the summary ledger; keep the CTA focused
    // on the next task instead of repeating a badge-like number.
    expect(cta).toHaveTextContent('Review pending')
    expect(screen.queryByText('No pending reviews')).not.toBeInTheDocument()
  })

  it('hides review button and shows empty text when pending === 0', () => {
    render(
      <RagCacheInsightBar
        cacheStats={buildCacheStats()}
        vectorStoreStats={buildVectorStoreStats()}
        ragPolicy={buildRagPolicy()}
        pendingCandidatesCount={0}
        onJumpToCandidates={vi.fn()}
      />,
    )

    expect(
      screen.queryByRole('button', { name: /Open Review Queue tab/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByText('No pending reviews')).toBeInTheDocument()
  })

  it('calls onJumpToCandidates when the CTA is clicked', async () => {
    const handler = vi.fn()
    const user = userEvent.setup()

    render(
      <RagCacheInsightBar
        cacheStats={buildCacheStats()}
        vectorStoreStats={buildVectorStoreStats()}
        ragPolicy={buildRagPolicy()}
        pendingCandidatesCount={2}
        onJumpToCandidates={handler}
      />,
    )

    await user.click(
      screen.getByRole('button', { name: 'Open Review Queue tab (2 pending)' }),
    )
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('shows warning status when pending count is high', () => {
    render(
      <RagCacheInsightBar
        cacheStats={buildCacheStats()}
        vectorStoreStats={buildVectorStoreStats()}
        ragPolicy={buildRagPolicy()}
        pendingCandidatesCount={15}
        onJumpToCandidates={vi.fn()}
      />,
    )

    expect(screen.getByText('Attention needed')).toBeInTheDocument()
  })

  it('shows warning status when RAG policy is disabled', () => {
    render(
      <RagCacheInsightBar
        cacheStats={buildCacheStats()}
        vectorStoreStats={buildVectorStoreStats()}
        ragPolicy={buildRagPolicy({ enabled: false })}
        pendingCandidatesCount={0}
        onJumpToCandidates={vi.fn()}
      />,
    )

    expect(screen.getByText('Attention needed')).toBeInTheDocument()
  })

  it('shows error status when cache stats are missing and an error occurred', () => {
    render(
      <RagCacheInsightBar
        cacheStats={null}
        vectorStoreStats={null}
        ragPolicy={null}
        pendingCandidatesCount={0}
        cacheError
        onJumpToCandidates={vi.fn()}
      />,
    )

    expect(screen.getByText('Error')).toBeInTheDocument()
  })
})

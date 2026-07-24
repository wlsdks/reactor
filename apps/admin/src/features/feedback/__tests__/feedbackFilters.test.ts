import type { FeedbackEntry } from '../types'
import { filterFeedbackItems } from '../feedbackFilters'

function feedback(overrides: Partial<FeedbackEntry>): FeedbackEntry {
  return {
    feedbackId: 'fb-1',
    query: 'Release policy question',
    response: 'Answer',
    rating: 'thumbs_down',
    timestamp: '2026-07-10T12:00:00Z',
    comment: 'Missing citation',
    runId: 'run-1',
    intent: null,
    domain: null,
    model: null,
    promptVersion: null,
    toolsUsed: null,
    durationMs: null,
    tags: null,
    templateId: null,
    reviewStatus: 'inbox',
    reviewTags: [],
    reviewedBy: null,
    reviewedAt: null,
    reviewNote: null,
    version: 1,
    updatedAt: '2026-07-10T12:00:00Z',
    ...overrides,
  }
}

describe('filterFeedbackItems', () => {
  const items = [
    feedback({ feedbackId: 'fb-1' }),
    feedback({
      feedbackId: 'fb-2',
      query: 'Provider latency',
      comment: null,
      timestamp: '2026-07-01T12:00:00Z',
    }),
  ]

  it('applies query and comment presence filters locally', () => {
    expect(filterFeedbackItems(items, { q: 'citation', hasComment: true }).map((item) => item.feedbackId))
      .toEqual(['fb-1'])
  })

  it('applies inclusive date boundaries locally', () => {
    expect(filterFeedbackItems(items, {
      from: '2026-07-09T00:00:00Z',
      to: '2026-07-10T23:59:59Z',
    }).map((item) => item.feedbackId)).toEqual(['fb-1'])
  })
})

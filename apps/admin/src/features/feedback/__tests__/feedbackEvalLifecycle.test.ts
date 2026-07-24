import type { FeedbackEntry } from '../types'
import {
  feedbackCanClose,
  feedbackEvalLifecycleStage,
  feedbackRequiresEvalClosure,
} from '../feedbackEvalLifecycle'

function feedback(overrides: Partial<FeedbackEntry> = {}): FeedbackEntry {
  return {
    feedbackId: 'fb-rag-1',
    query: 'What policy applies?',
    response: 'Missing citation.',
    rating: 'thumbs_down',
    timestamp: '2026-07-10T00:00:00Z',
    comment: null,
    runId: 'run-rag-1',
    intent: null,
    domain: null,
    model: null,
    promptVersion: null,
    toolsUsed: null,
    durationMs: null,
    tags: ['documents-ask', 'citation-failure'],
    templateId: null,
    reviewStatus: 'inbox',
    reviewTags: [],
    reviewedBy: null,
    reviewedAt: null,
    reviewNote: null,
    version: 1,
    updatedAt: '2026-07-10T00:00:00Z',
    readyNextActionIds: ['promote-eval'],
    blockedNextActionIds: [],
    nextActionStates: { 'promote-eval': 'ready' },
    nextActions: [{
      id: 'promote-eval',
      label: 'Promote to regression eval',
      evalCaseId: 'case-rag-1',
      sourceRunId: 'run-rag-1',
      datasetName: 'reactor-admin-regression',
    }],
    ...overrides,
  }
}

describe('feedback eval lifecycle', () => {
  it('keeps promotable feedback open until LangSmith closure evidence exists', () => {
    const ready = feedback()
    expect(feedbackRequiresEvalClosure(ready)).toBe(true)
    expect(feedbackEvalLifecycleStage(ready)).toBe('ready')
    expect(feedbackCanClose(ready)).toBe(false)

    const promoted = feedback({ reviewTags: ['promoted'] })
    expect(feedbackEvalLifecycleStage(promoted)).toBe('sync_pending')
    expect(feedbackCanClose(promoted)).toBe(false)

    const taggedOnly = feedback({ reviewTags: ['promoted', 'langsmith'] })
    expect(feedbackEvalLifecycleStage(taggedOnly)).toBe('sync_pending')
    expect(feedbackCanClose(taggedOnly)).toBe(false)

    const closed = feedback({
      reviewStatus: 'done',
      reviewTags: ['promoted', 'langsmith'],
      reviewNote: 'Synced to LangSmith and readiness evidence recorded.',
    })
    expect(feedbackEvalLifecycleStage(closed)).toBe('closed')
    expect(feedbackCanClose(closed)).toBe(true)
  })

  it('preserves blocked and non-eval feedback as distinct operator states', () => {
    expect(feedbackEvalLifecycleStage(feedback({
      readyNextActionIds: [],
      blockedNextActionIds: ['promote-eval'],
      nextActionStates: { 'promote-eval': 'blocked' },
    }))).toBe('blocked')
    expect(feedbackEvalLifecycleStage(feedback({
      rating: 'thumbs_up',
      nextActions: [],
    }))).toBe('not_required')
  })
})

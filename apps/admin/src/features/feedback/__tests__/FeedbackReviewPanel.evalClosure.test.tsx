import { i18n, render, screen } from '../../../test/utils'
import type { FeedbackEntry } from '../types'
import { FeedbackReviewPanel } from '../ui/FeedbackReviewPanel'

function feedback(reviewTags: string[] = [], overrides: Partial<FeedbackEntry> = {}): FeedbackEntry {
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
    tags: ['documents-ask'],
    templateId: null,
    reviewStatus: 'inbox',
    reviewTags,
    reviewedBy: null,
    reviewedAt: null,
    reviewNote: null,
    version: 1,
    updatedAt: '2026-07-10T00:00:00Z',
    readyNextActionIds: ['promote-eval'],
    blockedNextActionIds: [],
    nextActionStates: { 'promote-eval': 'ready' },
    nextActions: [{ id: 'promote-eval', label: 'Promote', evalCaseId: 'case-rag-1' }],
    ...overrides,
  }
}

describe('FeedbackReviewPanel eval closure', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'feedbackPage.review.title': 'Review',
      'feedbackPage.review.status': 'Status',
      'feedbackPage.review.statusInbox': 'Inbox',
      'feedbackPage.review.statusDone': 'Done',
      'feedbackPage.review.tags': 'Tags',
      'feedbackPage.review.note': 'Note',
      'feedbackPage.review.notePlaceholder': 'Review note',
      'feedbackPage.evalLifecycle.closeBlocked': 'Complete eval promotion and LangSmith sync before closing.',
      'common.cancel': 'Cancel',
      'common.save': 'Save',
    }, true, true)
  })

  it('disables generic done resolution while eval sync is incomplete', () => {
    render(<FeedbackReviewPanel feedback={feedback(['promoted'])} />)

    expect(screen.getByRole('button', { name: 'Done' })).toBeDisabled()
    expect(screen.getByText('Complete eval promotion and LangSmith sync before closing.')).toBeInTheDocument()
  })

  it('allows done resolution after complete LangSmith evidence', () => {
    render(<FeedbackReviewPanel feedback={feedback(['promoted', 'langsmith'], {
      reviewStatus: 'done',
      reviewNote: 'Synced to LangSmith and readiness evidence recorded.',
    })} />)

    expect(screen.getByRole('button', { name: 'Done' })).toBeEnabled()
    expect(screen.queryByText('Complete eval promotion and LangSmith sync before closing.')).not.toBeInTheDocument()
  })
})

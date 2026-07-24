import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n, render, screen, waitFor } from '../../../test/utils'
import * as feedbackApi from '../api'
import type { FeedbackEntry } from '../types'
import { FeedbackEvalPromotionAction } from '../ui/FeedbackEvalPromotionAction'
import {
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
} from '../../../shared/releaseWorkflow'

vi.mock('../api', () => ({
  promoteFeedbackToEval: vi.fn(),
  syncFeedbackEvalToLangSmith: vi.fn(),
}))

const promoteFeedbackToEvalMock = vi.mocked(feedbackApi.promoteFeedbackToEval)
const syncFeedbackEvalToLangSmithMock = vi.mocked(feedbackApi.syncFeedbackEvalToLangSmith)

function feedbackEntry(overrides: Partial<FeedbackEntry> = {}): FeedbackEntry {
  return {
    feedbackId: 'fb-rag-1',
    query: 'Where is the citation?',
    response: 'No citation was returned.',
    rating: 'thumbs_down',
    timestamp: '2026-07-10T00:00:00Z',
    comment: null,
    runId: 'run-rag-1',
    intent: null,
    domain: null,
    model: 'ollama:gemma4:12b',
    promptVersion: null,
    toolsUsed: ['Rag:hybrid_search'],
    durationMs: 100,
    tags: ['documents-ask'],
    templateId: null,
    reviewStatus: 'inbox',
    reviewTags: [],
    reviewedBy: null,
    reviewedAt: null,
    reviewNote: null,
    version: 1,
    updatedAt: '2026-07-10T00:00:00Z',
    readyNextActionIds: ['promote-eval'],
    nextActions: [{
      id: 'promote-eval',
      label: 'Promote feedback',
      evalCaseId: 'case_rag_candidate_run_rag_1',
      sourceRunId: 'run-rag-1',
    }],
    ...overrides,
  }
}

describe('FeedbackEvalPromotionAction', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.addResourceBundle('en', 'translation', {
      'feedbackPage.evalPromotion.title': 'Regression eval promotion',
      'feedbackPage.evalPromotion.description': 'Persist the source run as an eval case.',
      'feedbackPage.evalPromotion.ready': 'Ready',
      'feedbackPage.evalPromotion.blocked': 'Blocked',
      'feedbackPage.evalPromotion.promoted': 'Eval case saved',
      'feedbackPage.evalPromotion.syncCompleted': 'LangSmith sync completed',
      'feedbackPage.evalPromotion.caseId': 'Eval case ID',
      'feedbackPage.evalPromotion.sourceRun': 'Source run ID',
      'feedbackPage.evalPromotion.action': 'Promote to eval case',
      'feedbackPage.evalPromotion.saved': '{{caseId}} saved.',
      'feedbackPage.evalPromotion.synced': '{{datasetName}} synced.',
      'feedbackPage.evalPromotion.pendingLangSmith': 'LangSmith sync is still pending.',
      'feedbackPage.evalPromotion.syncAction': 'Sync LangSmith and close review',
      'feedbackPage.evalPromotion.syncEvidence': '{{datasetName}} synced {{examples}} examples.',
      'feedbackPage.evalPromotion.openLangSmith': 'Open LangSmith sync',
      'feedbackPage.evalPromotion.openReadiness': 'Open release readiness',
    }, true, true)
  })

  it('persists the eval case and surfaces the pending LangSmith handoff', async () => {
    const feedback = feedbackEntry()
    promoteFeedbackToEvalMock.mockResolvedValue({
      evalCase: {
        id: 'case_rag_candidate_run_rag_1',
        name: 'Feedback fb-rag-1',
        sourceRunId: 'run-rag-1',
        tags: ['feedback:fb-rag-1'],
        enabled: true,
        assertionCount: 1,
        nextActions: [],
      },
      feedback: { ...feedback, reviewTags: ['promoted'], version: 2 },
    })
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <FeedbackEvalPromotionAction feedback={feedback} />
      </MemoryRouter>,
    )

    expect(screen.getByText('case_rag_candidate_run_rag_1')).toBeInTheDocument()
    expect(screen.getByText('run-rag-1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Promote to eval case' }))

    await waitFor(() => expect(promoteFeedbackToEvalMock).toHaveBeenCalledWith(feedback))
    expect(screen.getByRole('status')).toHaveTextContent('LangSmith sync is still pending.')
    expect(screen.getByRole('link', { name: 'Open LangSmith sync' })).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
  })

  it('closes feedback review only after complete LangSmith case metadata evidence', async () => {
    const promotedFeedback = feedbackEntry({
      reviewTags: ['promoted'],
      version: 2,
      nextActions: [{
        id: 'promote-eval',
        label: 'Promote feedback',
        evalCaseId: 'case_rag_candidate_run_rag_1',
        sourceRunId: 'run-rag-1',
        datasetName: 'reactor-rag-ingestion-candidate',
      }],
    })
    syncFeedbackEvalToLangSmithMock.mockResolvedValue({
      sync: {
        ok: true,
        status: 'passed',
        scope: 'langsmith_persisted_eval_dataset_sync',
        mode: 'langsmith_dataset_sync',
        datasetName: 'reactor-rag-ingestion-candidate',
        created: false,
        examples: 1,
        exampleIds: ['example-1'],
        caseIds: ['case_rag_candidate_run_rag_1'],
        metadataCaseIds: ['case_rag_candidate_run_rag_1'],
        sourceRunIds: ['run-rag-1'],
        caseSourceRunIds: { case_rag_candidate_run_rag_1: 'run-rag-1' },
        splitCounts: { regression: 1 },
        secretFree: true,
        exampleContract: {},
        sdkContract: {},
      },
      feedback: { ...promotedFeedback, reviewStatus: 'done', reviewTags: ['promoted', 'langsmith'] },
    })
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <FeedbackEvalPromotionAction feedback={promotedFeedback} />
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: 'Sync LangSmith and close review' }))

    await waitFor(() => expect(syncFeedbackEvalToLangSmithMock).toHaveBeenCalledWith(
      promotedFeedback,
      'case_rag_candidate_run_rag_1',
      'reactor-rag-ingestion-candidate',
    ))
    expect(screen.getByText('LangSmith sync completed')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(
      'reactor-rag-ingestion-candidate synced 1 examples.',
    )
    expect(screen.getByRole('link', { name: 'Open release readiness' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
    )
  })

  it('does not expose promotion for positive feedback', () => {
    render(
      <MemoryRouter>
        <FeedbackEvalPromotionAction feedback={feedbackEntry({ rating: 'thumbs_up' })} />
      </MemoryRouter>,
    )
    expect(screen.queryByText('Regression eval promotion')).not.toBeInTheDocument()
  })
})

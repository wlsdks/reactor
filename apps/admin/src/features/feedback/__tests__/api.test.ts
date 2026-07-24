import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  listFeedback,
  deleteFeedback,
  submitFeedback,
  getFeedback,
  exportFeedback,
  updateReview,
  bulkUpdateReview,
  fetchUnreviewedCount,
  fetchFeedbackStats,
  promoteFeedbackToEval,
  syncFeedbackEvalToLangSmith,
} from '../api'
import type { FeedbackEntry } from '../types'

const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
const mockApiPatch = vi.fn()
const mockApiDelete = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: (...args: unknown[]) => mockApiPost(...args),
    patch: (...args: unknown[]) => mockApiPatch(...args),
    put: vi.fn(),
    delete: (...args: unknown[]) => mockApiDelete(...args),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

const mockCursorPage = {
  items: [{ feedbackId: 'fb-1', rating: 'thumbs_up' }],
  nextCursor: null,
  prevCursor: null,
  approximateTotal: 1,
}

describe('feedback api', () => {
  afterEach(() => vi.clearAllMocks())

  it('listFeedback returns CursorPage with no filters', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockCursorPage))
    const result = await listFeedback()
    expect(result.items).toHaveLength(1)
    expect(result.approximateTotal).toBe(1)
    expect(mockApiGet).toHaveBeenCalledWith('feedback', expect.objectContaining({
      searchParams: expect.objectContaining({ limit: 50 }),
    }))
  })

  it('listFeedback passes rating + status + tag filters', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockCursorPage))
    await listFeedback({ rating: 'thumbs_down', status: 'inbox', tag: 'actionable' })
    const callArg = mockApiGet.mock.calls[0][1]
    expect(callArg.searchParams.rating).toBe('thumbs_down')
    expect(callArg.searchParams.reviewStatus).toBe('inbox')
    expect(callArg.searchParams.status).toBeUndefined()
    expect(callArg.searchParams.tag).toBe('actionable')
  })

  it('listFeedback leaves unsupported text and comment filters to the manager', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockCursorPage))
    await listFeedback({ q: 'error', hasComment: true })
    const callArg = mockApiGet.mock.calls[0][1]
    expect(callArg.searchParams.q).toBeUndefined()
    expect(callArg.searchParams.hasComment).toBeUndefined()
  })

  it('deleteFeedback sends DELETE', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))
    await expect(deleteFeedback('fb-1')).resolves.not.toThrow()
    expect(mockApiDelete).toHaveBeenCalledWith('feedback/fb-1')
  })

  it('submitFeedback sends POST', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ feedbackId: 'fb-1' }))
    await submitFeedback({ rating: 'thumbs_up', query: 'Q' })
    expect(mockApiPost).toHaveBeenCalledWith(
      'feedback',
      expect.objectContaining({ json: { rating: 'thumbs_up', query: 'Q' } }),
    )
  })

  it('getFeedback returns single entry', async () => {
    mockApiGet.mockReturnValue(jsonResponse({ feedbackId: 'fb-1' }))
    const r = await getFeedback('fb-1')
    expect(r).toHaveProperty('feedbackId', 'fb-1')
    expect(mockApiGet).toHaveBeenCalledWith('feedback/fb-1')
  })

  it('exportFeedback returns export response', async () => {
    mockApiGet.mockReturnValue(jsonResponse({
      version: 1, exportedAt: '2026-01-01T00:00:00Z', source: 'reactor', items: [],
    }))
    const r = await exportFeedback()
    expect(r).toHaveProperty('version', 1)
  })

  it('updateReview sends PATCH with If-Match header', async () => {
    mockApiPatch.mockReturnValue(jsonResponse({ feedbackId: 'fb-1', version: 2 }))
    await updateReview('fb-1', 1, { status: 'done', tags: ['resolved'] })
    const callArg = mockApiPatch.mock.calls[0][1]
    expect(callArg.headers['If-Match']).toBe('1')
    expect(callArg.json).toEqual({ status: 'done', tags: ['resolved'] })
  })

  it('bulkUpdateReview sends POST', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ updated: ['a', 'b'], failed: [] }))
    const r = await bulkUpdateReview({ ids: ['a', 'b'], status: 'done' })
    expect(r.updated).toHaveLength(2)
    expect(mockApiPost).toHaveBeenCalledWith('feedback/bulk-update', expect.anything())
  })

  it('fetchUnreviewedCount returns count', async () => {
    mockApiGet.mockReturnValue(jsonResponse({ count: 7 }))
    const r = await fetchUnreviewedCount()
    expect(r.count).toBe(7)
    expect(mockApiGet).toHaveBeenCalledWith('feedback/unreviewed-count')
  })

  it('normalizes the compact FastAPI feedback stats response', async () => {
    mockApiGet.mockReturnValue(jsonResponse({
      total: 1,
      positive: 0,
      negative: 1,
      positiveRate: 0,
      commentRate: 1,
      inboxCount: 1,
      doneCount: 0,
    }))

    await expect(fetchFeedbackStats()).resolves.toMatchObject({
      total: 1,
      negativeThisPeriod: 1,
      previousPeriodNegative: 0,
      negativeChange: 0,
      byDay: [],
      topNegativeDomains: [],
      topNegativeIntents: [],
      topNegativeTools: [],
    })
  })

  it('promotes feedback into a persisted eval case and records pending LangSmith review state', async () => {
    const feedback: FeedbackEntry = {
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
      tags: ['documents-ask', 'citation-failure'],
      templateId: null,
      reviewStatus: 'inbox',
      reviewTags: [],
      reviewedBy: null,
      reviewedAt: null,
      reviewNote: 'Operator confirmed weak evidence.',
      version: 3,
      updatedAt: '2026-07-10T00:00:00Z',
      readyNextActionIds: ['promote-eval'],
      nextActions: [{
        id: 'promote-eval',
        label: 'Promote feedback',
        evalCaseId: 'case_rag_candidate_run_rag_1',
        sourceRunId: 'run-rag-1',
        feedbackTags: ['documents-ask', 'expected-citation:policy:0'],
        workflowTags: ['collection:rag-ingestion-candidate'],
        expectedAnswers: ['[policy:0]'],
      }],
    }
    const evalCase = {
      id: 'case_rag_candidate_run_rag_1',
      name: 'Feedback fb-rag-1',
      sourceRunId: 'run-rag-1',
      tags: ['documents-ask', 'feedback:fb-rag-1'],
      enabled: true,
      assertionCount: 1,
      nextActions: [],
    }
    const reviewed = { ...feedback, reviewTags: ['promoted'], version: 4 }
    mockApiPost.mockReturnValueOnce(jsonResponse(evalCase))
    mockApiPatch.mockReturnValueOnce(jsonResponse(reviewed))

    await expect(promoteFeedbackToEval(feedback)).resolves.toEqual({ evalCase, feedback: reviewed })
    expect(mockApiPost).toHaveBeenCalledWith('admin/agent-eval/cases/promote', {
      json: {
        runId: 'run-rag-1',
        id: 'case_rag_candidate_run_rag_1',
        name: 'Feedback fb-rag-1: Where is the citation?',
        expectedAnswerContains: ['[policy:0]'],
        tags: [
          'documents-ask',
          'expected-citation:policy:0',
          'collection:rag-ingestion-candidate',
          'feedback:fb-rag-1',
          'feedback-rating:thumbs_down',
        ],
        enabled: true,
      },
    })
    expect(mockApiPatch).toHaveBeenCalledWith('feedback/fb-rag-1', {
      headers: { 'If-Match': '3' },
      json: {
        status: 'inbox',
        tags: ['promoted', 'collection:rag-ingestion-candidate'],
        tagMode: 'add',
        note: 'Operator confirmed weak evidence.\nEval case case_rag_candidate_run_rag_1 promoted from run-rag-1; LangSmith sync pending.',
      },
    })
  })

  it('closes promoted feedback only after LangSmith returns complete sync evidence', async () => {
    const feedback: FeedbackEntry = {
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
      reviewTags: ['promoted'],
      reviewedBy: 'admin',
      reviewedAt: '2026-07-10T00:01:00Z',
      reviewNote: 'Eval case promoted; LangSmith sync pending.',
      version: 4,
      updatedAt: '2026-07-10T00:01:00Z',
      nextActions: [{
        id: 'promote-eval',
        label: 'Promote feedback',
        evalCaseId: 'case_rag_candidate_run_rag_1',
        workflowTags: ['collection:rag-ingestion-candidate'],
      }],
    }
    const sync = {
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
    }
    const reviewed = {
      ...feedback,
      reviewStatus: 'done' as const,
      reviewTags: ['promoted', 'langsmith'],
      version: 5,
    }
    mockApiPost.mockReturnValueOnce(jsonResponse(sync))
    mockApiPatch.mockReturnValueOnce(jsonResponse(reviewed))

    await expect(syncFeedbackEvalToLangSmith(
      feedback,
      'case_rag_candidate_run_rag_1',
      'reactor-rag-ingestion-candidate',
    )).resolves.toEqual({ sync, feedback: reviewed })
    expect(mockApiPost).toHaveBeenCalledWith('admin/agent-eval/langsmith/sync', {
      json: {
        datasetName: 'reactor-rag-ingestion-candidate',
        caseIds: ['case_rag_candidate_run_rag_1'],
        description: 'Reactor admin feedback promotion regression cases',
      },
    })
    expect(mockApiPatch).toHaveBeenCalledWith('feedback/fb-rag-1', {
      headers: { 'If-Match': '4' },
      json: {
        status: 'done',
        tags: ['promoted', 'langsmith', 'collection:rag-ingestion-candidate'],
        tagMode: 'add',
        note: 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.',
      },
    })
  })
})

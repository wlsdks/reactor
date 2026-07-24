import type {
  FeedbackEntry,
  FeedbackStats,
  SubmitFeedbackRequest,
  FeedbackExportResponse,
  FeedbackRating,
  FeedbackReviewStatus,
  CursorPage,
  ReviewUpdateRequest,
  BulkUpdateRequest,
  BulkUpdateResult,
  FeedbackEvalPromotionResult,
  PromotedEvalCase,
  FeedbackLangSmithClosureResult,
  LangSmithPersistedEvalSyncResult,
} from './types'
import { api } from '../../shared/api/client'

export interface FeedbackFilters {
  rating?: FeedbackRating
  status?: FeedbackReviewStatus
  tag?: string
  q?: string
  hasComment?: boolean
  domain?: string
  intent?: string
  from?: string
  to?: string
  cursor?: string
  limit?: number
}

/** R465: 커서 페이징 목록 조회. */
export const listFeedback = async (
  filters: FeedbackFilters = {},
): Promise<CursorPage<FeedbackEntry>> => {
  const searchParams: Record<string, string | number | boolean> = {
    limit: filters.limit ?? 50,
  }
  if (filters.rating) searchParams.rating = filters.rating
  if (filters.status) searchParams.reviewStatus = filters.status
  if (filters.tag) searchParams.tag = filters.tag
  // FastAPI currently supports rating, reviewStatus, tag, and pagination.
  // Text/comment/date filters are applied explicitly by FeedbackManager.
  return api.get('feedback', { searchParams }).json()
}

export const deleteFeedback = async (feedbackId: string): Promise<void> => {
  await api.delete(`feedback/${encodeURIComponent(feedbackId)}`)
}

export const submitFeedback = (request: SubmitFeedbackRequest): Promise<FeedbackEntry> =>
  api.post('feedback', { json: request }).json()

export const getFeedback = (feedbackId: string): Promise<FeedbackEntry> =>
  api.get(`feedback/${encodeURIComponent(feedbackId)}`).json()

export const exportFeedback = (): Promise<FeedbackExportResponse> =>
  api.get('feedback/export').json()

type BackendFeedbackStats = Partial<FeedbackStats>

export const fetchFeedbackStats = async (from?: string, to?: string): Promise<FeedbackStats> => {
  const searchParams: Record<string, string> = { limit: '200' }
  if (from) searchParams.from = from
  if (to) searchParams.to = to
  const stats = await api.get('feedback/stats', { searchParams }).json<BackendFeedbackStats>()
  return {
    period: stats.period ?? { from: from ?? '', to: to ?? '' },
    total: stats.total ?? 0,
    positive: stats.positive ?? 0,
    negative: stats.negative ?? 0,
    negativeThisPeriod: stats.negativeThisPeriod ?? stats.negative ?? 0,
    previousPeriodNegative: stats.previousPeriodNegative ?? 0,
    negativeChange: stats.negativeChange ?? 0,
    positiveRate: stats.positiveRate ?? 0,
    previousPeriodRate: stats.previousPeriodRate ?? 0,
    commentRate: stats.commentRate ?? 0,
    byDay: stats.byDay ?? [],
    topNegativeDomains: stats.topNegativeDomains ?? [],
    topNegativeIntents: stats.topNegativeIntents ?? [],
    topNegativeTools: stats.topNegativeTools ?? [],
    inboxCount: stats.inboxCount ?? 0,
    doneCount: stats.doneCount ?? 0,
  }
}

/** R465: inbox 상태의 부정 피드백 개수. */
export const fetchUnreviewedCount = (): Promise<{ count: number }> =>
  api.get('feedback/unreviewed-count').json()

/** R465: 리뷰 워크플로 업데이트 — If-Match 헤더 필수 (낙관적 잠금). */
export const updateReview = (
  feedbackId: string,
  version: number,
  request: ReviewUpdateRequest,
): Promise<FeedbackEntry> =>
  api.patch(`feedback/${encodeURIComponent(feedbackId)}`, {
    headers: { 'If-Match': String(version) },
    json: request,
  }).json()

/** R465: 벌크 리뷰 업데이트 (100건 제한, 부분 성공). */
export const bulkUpdateReview = (
  request: BulkUpdateRequest,
): Promise<BulkUpdateResult> =>
  api.post('feedback/bulk-update', { json: request }).json()

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  return [...new Set(values.map((value) => value?.trim()).filter((value): value is string => Boolean(value)))]
}

function promotionNote(
  currentNote: string | null,
  caseId: string,
  sourceRunId: string,
): string {
  const line = `Eval case ${caseId} promoted from ${sourceRunId}; LangSmith sync pending.`
  const existing = currentNote?.trim() ?? ''
  if (!existing || existing.includes(line)) return existing || line
  return `${existing}\n${line}`
}

export async function promoteFeedbackToEval(
  feedback: FeedbackEntry,
): Promise<FeedbackEvalPromotionResult> {
  const action = feedback.nextActions?.find((candidate) => candidate.id === 'promote-eval')
  const sourceRunId = uniqueStrings([action?.sourceRunId, feedback.runId])[0]
  const caseId = action?.evalCaseId?.trim()
  if (!action || !sourceRunId || !caseId) {
    throw new Error('Feedback eval promotion requires promote-eval action, sourceRunId, and evalCaseId')
  }
  if (feedback.blockedNextActionIds?.includes('promote-eval')) {
    throw new Error('Feedback eval promotion is blocked by backend readiness policy')
  }

  const workflowTags = uniqueStrings(action.workflowTags ?? [])
  const tags = uniqueStrings([
    ...(action.feedbackTags ?? []),
    ...workflowTags,
    `feedback:${feedback.feedbackId}`,
    `feedback-rating:${feedback.rating}`,
  ])
  const evalCase = await api.post('admin/agent-eval/cases/promote', {
    json: {
      runId: sourceRunId,
      id: caseId,
      name: `Feedback ${feedback.feedbackId}: ${feedback.query}`.slice(0, 255),
      expectedAnswerContains: action.expectedAnswers ?? [],
      tags,
      enabled: true,
    },
  }).json<PromotedEvalCase>()

  const reviewed = await updateReview(feedback.feedbackId, feedback.version, {
    status: 'inbox',
    tags: uniqueStrings(['promoted', ...workflowTags]),
    tagMode: 'add',
    note: promotionNote(feedback.reviewNote, evalCase.id, evalCase.sourceRunId ?? sourceRunId),
  })
  return { evalCase, feedback: reviewed }
}

const LANGSMITH_REVIEW_NOTE =
  'Promoted to regression eval and reviewed in hardening/LangSmith. ' +
  'Required readiness reports: hardening_suite, langsmith_eval_sync.'

export async function syncFeedbackEvalToLangSmith(
  feedback: FeedbackEntry,
  caseId: string,
  datasetName: string,
): Promise<FeedbackLangSmithClosureResult> {
  const sync = await api.post('admin/agent-eval/langsmith/sync', {
    json: {
      datasetName,
      caseIds: [caseId],
      description: 'Reactor admin feedback promotion regression cases',
    },
  }).json<LangSmithPersistedEvalSyncResult>()
  if (
    sync.ok !== true
    || sync.status !== 'passed'
    || !sync.caseIds.includes(caseId)
    || !sync.metadataCaseIds.includes(caseId)
    || sync.secretFree !== true
  ) {
    throw new Error('LangSmith sync did not return complete case and metadata evidence')
  }
  const action = feedback.nextActions?.find((candidate) => candidate.id === 'promote-eval')
  const reviewed = await updateReview(feedback.feedbackId, feedback.version, {
    status: 'done',
    tags: uniqueStrings(['promoted', 'langsmith', ...(action?.workflowTags ?? [])]),
    tagMode: 'add',
    note: LANGSMITH_REVIEW_NOTE,
  })
  return { sync, feedback: reviewed }
}

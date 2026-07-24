import type { LangSmithPersistedEvalSyncResult } from '../evals/types'

export type { LangSmithPersistedEvalSyncResult } from '../evals/types'

export type FeedbackRating = 'thumbs_up' | 'thumbs_down'
export type FeedbackReviewStatus = 'inbox' | 'done'

export interface FeedbackEntry {
  feedbackId: string
  query: string
  response: string
  rating: FeedbackRating
  timestamp: string
  comment: string | null
  runId: string | null
  intent: string | null
  domain: string | null
  model: string | null
  promptVersion: number | null
  toolsUsed: string[] | null
  durationMs: number | null
  tags: string[] | null
  templateId: string | null

  // R465 review workflow
  reviewStatus: FeedbackReviewStatus
  reviewTags: string[]
  reviewedBy: string | null
  reviewedAt: string | null
  reviewNote: string | null
  version: number
  updatedAt: string
  readyNextActionIds?: string[] | null
  blockedNextActionIds?: string[] | null
  nextActionStates?: Record<string, string> | null
  nextActions?: FeedbackNextAction[] | null
}

export interface FeedbackNextAction {
  id: string
  label: string
  command?: string | null
  feedbackId?: string | null
  evalCaseId?: string | null
  sourceRunId?: string | null
  candidateTag?: string | null
  subjectUserId?: string | null
  reportFile?: string | null
  caseFile?: string | null
  runFile?: string | null
  diagnosticsApi?: string | null
  suiteFile?: string | null
  datasetName?: string | null
  preflightFile?: string | null
  preflightEnvTemplate?: string | null
  replatformReadinessFile?: string | null
  smokePlanFile?: string | null
  releaseEvidenceFile?: string | null
  releaseReadinessFile?: string | null
  releaseReadinessCommand?: string | null
  remediationCommand?: string | null
  envFileCommand?: string | null
  readinessReportArg?: string | null
  requiredReadinessReports?: string[] | null
  readinessReports?: Record<string, string> | null
  requiredEnvAnyOf?: string[][] | null
  missingEnvAnyOf?: string[] | null
  recommendedEnv?: string[] | null
  recommendedVersionBump?: string | null
  recommendedTagPattern?: string | null
  latestTagCommand?: string | null
  recommendedTagSource?: string | null
  minorBoundaryReports?: string[] | null
  feedbackTags?: string[] | null
  feedbackSource?: string | null
  workflowTags?: string[] | null
  expectedAnswers?: string[] | null
  dependsOnActionIds?: string[] | null
}

export interface PromotedEvalCase {
  id: string
  name: string
  sourceRunId: string | null
  tags: string[]
  enabled: boolean
  assertionCount: number
  nextActions: Array<{
    id: string
    label: string
    command: string
  }>
}

export interface FeedbackEvalPromotionResult {
  evalCase: PromotedEvalCase
  feedback: FeedbackEntry
}

export interface FeedbackLangSmithClosureResult {
  sync: LangSmithPersistedEvalSyncResult
  feedback: FeedbackEntry
}

export interface SubmitFeedbackRequest {
  rating: string
  query?: string
  response?: string
  comment?: string
  runId?: string
  intent?: string
  domain?: string
  model?: string
  promptVersion?: number
  toolsUsed?: string[]
  durationMs?: number
  tags?: string[]
  templateId?: string
}

export interface NegativeBucket {
  key: string
  negativeCount: number
  totalCount: number
  negativeRate: number
  wilsonLowerBound: number
  sampleWarning: boolean
}

export interface DayStat {
  date: string
  positive: number
  negative: number
  total: number
}

export interface FeedbackStats {
  period: { from: string; to: string }
  total: number
  positive: number
  negative: number
  negativeThisPeriod: number
  previousPeriodNegative: number
  negativeChange: number
  positiveRate: number
  previousPeriodRate: number
  commentRate: number
  byDay: DayStat[]
  topNegativeDomains: NegativeBucket[]
  topNegativeIntents: NegativeBucket[]
  topNegativeTools: NegativeBucket[]
  inboxCount: number
  doneCount: number
}

export interface FeedbackExportResponse {
  version: number
  exportedAt: string
  source: string
  items: Record<string, unknown>[]
}

export interface CursorPage<T> {
  items: T[]
  nextCursor: string | null
  prevCursor: string | null
  approximateTotal: number
}

export interface ReviewUpdateRequest {
  status?: FeedbackReviewStatus
  tags?: string[]
  tagMode?: 'set' | 'add' | 'remove'
  note?: string | null
}

export interface BulkUpdateRequest {
  ids: string[]
  status?: FeedbackReviewStatus
  tags?: string[]
  tagMode?: 'set' | 'add' | 'remove'
}

export interface BulkUpdateResult {
  updated: string[]
  failed: { id: string; reason: string }[]
}

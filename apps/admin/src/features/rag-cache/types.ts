export interface CacheStats {
  enabled: boolean
  semanticEnabled: boolean
  totalExactHits: number
  totalSemanticHits: number
  totalMisses: number
  hitRate: number
  config: CacheConfig
}

export interface CacheConfig {
  ttlMinutes: number
  maxSize: number
  similarityThreshold: number
  maxCandidates: number
  cacheableTemperature: number
}

export interface VectorStoreStats {
  available: boolean
  documentCount: number
}

export interface RagPolicy {
  enabled: boolean
  requireReview: boolean
  allowedChannels: string[]
  minQueryChars: number
  minResponseChars: number
  blockedPatterns: string[]
  createdAt?: number
  updatedAt?: number
}

export interface RagPolicyState {
  configEnabled: boolean
  dynamicEnabled: boolean
  effective: RagPolicy
  stored: RagPolicy | null
}

export type RagCandidateStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface RagCandidateNextAction {
  id: string
  label: string
  command?: string | null
  evalCaseId?: string | null
  sourceRunId?: string | null
  candidateTag?: string | null
  workflowTags?: string[] | null
  reportFile?: string | null
  caseFile?: string | null
  runFile?: string | null
  diagnosticsApi?: string | null
  suiteFile?: string | null
  datasetName?: string | null
  feedbackRating?: string | null
  feedbackSource?: string | null
  feedbackTags?: string[] | null
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
  dependsOnActionIds?: string[] | null
  promotionCoverage?: Record<string, boolean | number | string | null> | null
  citationMarkerContract?: Record<string, boolean | number | string | string[] | null> | null
}

export interface RagCandidate {
  id: string
  runId?: string | null
  query: string
  response: string
  channel: string
  status: RagCandidateStatus
  // 백엔드 RagIngestionController 응답 필드와 1:1 정합 — epoch ms
  capturedAt: number
  reviewedAt?: number | null
  reviewedBy?: string | null
  reviewComment?: string | null
  ingestedDocumentId?: string | null
  nextAction?: string | null
  readyNextActionIds?: string[] | null
  blockedNextActionIds?: string[] | null
  nextActionStates?: Record<string, string> | null
  nextActions?: RagCandidateNextAction[] | null
}

export interface RagCandidateFilters {
  status?: string
  channel?: string
}

export interface RagStatusStat {
  status: string
  count: number
  latestCaptured?: string | null
}

export interface RagChannelStat {
  channel: string
  pendingCount: number
  approvedCount: number
  rejectedCount: number
}

export interface DocumentSearchResult {
  id: string
  content: string
  metadata: Record<string, unknown>
  score: number | null
}

export interface RagAnswerContract {
  status: string | null
  citationIds: string[]
  sourceLabels: string[]
  citationStyle: string | null
  uncitedClaimsAllowed: boolean | null
}

export type RagAnswerProbeStatus = 'grounded' | 'weak' | 'failed'

export interface RagRetrievalSummary {
  ragToolResultCount: number
  chunkCount: number
  citationCount: number
  citationStatus: string | null
}

export interface RagAnswerExtractionSummary {
  status: string | null
  matchedCitationCount: number
  hashMismatchCount: number
  missingChunkCount: number
}

export interface RagAnswerProbeResult {
  query: string
  content: string | null
  success: boolean
  status: RagAnswerProbeStatus
  runId: string | null
  model: string | null
  durationMs: number | null
  grounded: boolean | null
  evidenceStatus: string | null
  citationIds: string[]
  sourceLabels: string[]
  missingEvidence: string[]
  operatorAction: string | null
  blockReason: string | null
  answerContract: RagAnswerContract | null
  retrievalSummary: RagRetrievalSummary | null
  answerExtraction: RagAnswerExtractionSummary | null
  recoverySteps: string[]
}

export interface RagWeakAnswerPromotionResult {
  feedbackId: string
  reviewStatus: string
  runId: string | null
  nextActionIds: string[]
}

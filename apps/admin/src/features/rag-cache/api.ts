import { api } from '../../shared/api/client'
import { snakeToCamel } from '../../shared/lib/caseTransform'
import type {
  CacheStats,
  VectorStoreStats,
  RagPolicyState,
  DocumentSearchResult,
  RagCandidate,
  RagCandidateFilters,
  RagStatusStat,
  RagChannelStat,
  RagAnswerContract,
  RagAnswerExtractionSummary,
  RagAnswerProbeResult,
  RagRetrievalSummary,
  RagWeakAnswerPromotionResult,
} from './types'
import type { RagPolicyFormValues } from './schema'

export const getCacheStats = (): Promise<CacheStats> =>
  api.get('admin/platform/cache/stats').json()

export const invalidateCache = (): Promise<{ invalidated: boolean; message: string }> =>
  api.post('admin/platform/cache/invalidate').json()

/** R452: 단일 키 무효화 — 오염된 엔트리만 타겟 삭제 (hit rate 핵폭탄 회피). */
export const invalidateCacheKey = (
  key: string,
): Promise<{ invalidated: boolean; cacheEnabled: boolean }> =>
  api.post('admin/platform/cache/invalidate-key', { json: { key } }).json()

/** R452: 와일드카드(`*`) 패턴 매칭 무효화. 예: `user:abc:*`. */
export const invalidateCacheByPattern = (
  pattern: string,
): Promise<{ invalidatedCount: number; cacheEnabled: boolean }> =>
  api.post('admin/platform/cache/invalidate-by-pattern', { json: { pattern } }).json()

// ── Runtime Settings (R454/R455) ─────────────────────────────────────
export interface RuntimeSetting {
  key: string
  value: string
  type: string
  category: string
  description?: string | null
  updatedBy?: string | null
  updatedAt: string
}

/** R455: 전체 런타임 설정 목록 조회. */
export const listRuntimeSettings = (): Promise<RuntimeSetting[]> =>
  api.get('admin/settings', { searchParams: { limit: 200 } }).json()

/**
 * R455: 단일 설정 조회 (full metadata).
 * 존재하지 않으면 HTTP 404 → ky throws; 호출부에서 `.catch(() => null)` 권장.
 */
export const getRuntimeSetting = (key: string): Promise<RuntimeSetting> =>
  api.get(`admin/settings/${encodeURIComponent(key)}`).json()

/** R454: 런타임 설정 변경 (캐시 kill-switch, TTL, threshold 등). */
export const updateRuntimeSetting = (
  key: string,
  value: string,
  type: string = 'STRING',
  category: string = 'cache',
  description?: string,
): Promise<{ key: string; value: string; status: string }> =>
  api.put(`admin/settings/${encodeURIComponent(key)}`, {
    json: { value, type, category, description },
  }).json()

/** R455: 설정 삭제 (기본값으로 리셋). */
export const deleteRuntimeSetting = async (key: string): Promise<void> => {
  await api.delete(`admin/settings/${encodeURIComponent(key)}`)
}

export const getVectorStoreStats = (): Promise<VectorStoreStats> =>
  api.get('admin/platform/vectorstore/stats').json()

export const getRagPolicy = (): Promise<RagPolicyState> =>
  api.get('rag-ingestion/policy').json()

export const updateRagPolicy = async (values: RagPolicyFormValues): Promise<void> => {
  await api.put('rag-ingestion/policy', { json: values })
}

export const resetRagPolicy = async (): Promise<void> => {
  await api.delete('rag-ingestion/policy')
}

export const searchDocuments = (query: string, topK: number): Promise<DocumentSearchResult[]> =>
  api.post('documents/search', { json: { query, topK } }).json()

interface RawResearchPlan {
  evidenceStatus?: unknown
  citationIds?: unknown
  sourceLabels?: unknown
  missingEvidence?: unknown
  operatorAction?: unknown
  answerContract?: unknown
  retrievalSummary?: unknown
  answerExtraction?: unknown
  recoverySteps?: unknown
}

interface RawGroundedChatResponse {
  content?: unknown
  success?: unknown
  model?: unknown
  durationMs?: unknown
  grounded?: unknown
  blockReason?: unknown
  metadata?: {
    runId?: unknown
    research_plan?: RawResearchPlan
  }
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    const normalized = stringValue(item)
    return normalized ? [normalized] : []
  })
}

function answerContract(value: unknown): RagAnswerContract | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const contract = value as Record<string, unknown>
  return {
    status: stringValue(contract.status),
    citationIds: stringList(contract.citationIds),
    sourceLabels: stringList(contract.sourceLabels),
    citationStyle: stringValue(contract.citationStyle),
    uncitedClaimsAllowed: typeof contract.uncitedClaimsAllowed === 'boolean'
      ? contract.uncitedClaimsAllowed
      : null,
  }
}

function nonnegativeNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0
}

function retrievalSummary(value: unknown): RagRetrievalSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const summary = value as Record<string, unknown>
  return {
    ragToolResultCount: nonnegativeNumber(summary.ragToolResultCount),
    chunkCount: nonnegativeNumber(summary.chunkCount),
    citationCount: nonnegativeNumber(summary.citationCount),
    citationStatus: stringValue(summary.citationStatus),
  }
}

function answerExtraction(value: unknown): RagAnswerExtractionSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const summary = value as Record<string, unknown>
  return {
    status: stringValue(summary.status),
    matchedCitationCount: nonnegativeNumber(summary.matchedCitationCount),
    hashMismatchCount: nonnegativeNumber(summary.hashMismatchCount),
    missingChunkCount: nonnegativeNumber(summary.missingChunkCount),
  }
}

export async function askGroundedRag(query: string): Promise<RagAnswerProbeResult> {
  const normalizedQuery = query.trim()
  const raw = await api.post('chat', {
    json: {
      message: normalizedQuery,
      graphProfile: 'research',
      responseFormat: 'TEXT',
      metadata: { diagnosticSource: 'admin-rag-answer-probe' },
    },
  }).json<RawGroundedChatResponse>()
  const researchPlan = raw.metadata?.research_plan
  const evidenceStatus = stringValue(researchPlan?.evidenceStatus)
  const contract = answerContract(researchPlan?.answerContract)
  const citationIds = stringList(researchPlan?.citationIds ?? contract?.citationIds)
  const sourceLabels = stringList(researchPlan?.sourceLabels ?? contract?.sourceLabels)
  const success = raw.success === true
  const isGrounded = raw.grounded === true
    && evidenceStatus === 'grounded'
    && citationIds.length > 0
    && sourceLabels.length > 0

  return {
    query: normalizedQuery,
    content: stringValue(raw.content),
    success,
    status: !success ? 'failed' : isGrounded ? 'grounded' : 'weak',
    runId: stringValue(raw.metadata?.runId),
    model: stringValue(raw.model),
    durationMs: typeof raw.durationMs === 'number' ? raw.durationMs : null,
    grounded: typeof raw.grounded === 'boolean' ? raw.grounded : null,
    evidenceStatus,
    citationIds,
    sourceLabels,
    missingEvidence: stringList(researchPlan?.missingEvidence),
    operatorAction: stringValue(researchPlan?.operatorAction),
    blockReason: stringValue(raw.blockReason),
    answerContract: contract,
    retrievalSummary: retrievalSummary(researchPlan?.retrievalSummary),
    answerExtraction: answerExtraction(researchPlan?.answerExtraction),
    recoverySteps: stringList(researchPlan?.recoverySteps),
  }
}

export async function promoteWeakRagAnswer(
  result: RagAnswerProbeResult,
  options: { expectedDocumentId?: string | null } = {},
): Promise<RagWeakAnswerPromotionResult> {
  if (!result.runId) throw new Error('RAG answer probe result is missing runId')
  const expectedCitationTags = result.citationIds.map((id) => `expected-citation:${id}`)
  const expectedDocumentId = stringValue(options.expectedDocumentId)
  const feedback = await api.post('feedback', {
    json: {
      rating: 'thumbs_down',
      query: result.query,
      response: result.content ?? '',
      runId: result.runId,
      model: result.model ?? undefined,
      durationMs: result.durationMs ?? undefined,
      source: 'admin-rag-answer-probe',
      toolsUsed: ['Rag:hybrid_search'],
      tags: [
        'documents-ask',
        'citation-failure',
        'collection:rag-ingestion-candidate',
        ...(expectedDocumentId ? [`expected-document:${expectedDocumentId}`] : []),
        ...expectedCitationTags,
      ],
      comment: [
        result.blockReason,
        result.missingEvidence.length > 0
          ? `missingEvidence=${result.missingEvidence.join(',')}`
          : null,
        result.operatorAction ? `operatorAction=${result.operatorAction}` : null,
        expectedDocumentId ? `expectedDocumentId=${expectedDocumentId}` : null,
      ].filter(Boolean).join('; ') || 'Weak grounded answer captured by admin RAG probe.',
    },
  }).json<Record<string, unknown>>()

  return {
    feedbackId: stringValue(feedback.feedbackId) ?? '',
    reviewStatus: stringValue(feedback.reviewStatus) ?? 'inbox',
    runId: stringValue(feedback.runId),
    nextActionIds: stringList(feedback.readyNextActionIds),
  }
}

export const listRagCandidates = (filters: RagCandidateFilters = {}): Promise<RagCandidate[]> => {
  const searchParams: Record<string, string | number> = { limit: 200 }
  if (filters.status) searchParams.status = filters.status
  if (filters.channel) searchParams.channel = filters.channel
  return api.get('rag-ingestion/candidates', { searchParams }).json()
}

export const approveRagCandidate = async (id: string): Promise<void> => {
  await api.post(`rag-ingestion/candidates/${id}/approve`)
}

export const rejectRagCandidate = async (id: string): Promise<void> => {
  await api.post(`rag-ingestion/candidates/${id}/reject`)
}

/**
 * Bulk result returned by {@link bulkApproveRagCandidates} /
 * {@link bulkRejectRagCandidates}. No backend batch endpoint exists today —
 * implementation fan-outs to N single-item calls via `Promise.allSettled`.
 * When backend exposes a batch endpoint, replace the internals without
 * breaking the caller shape.
 */
export interface BulkCandidateActionResult {
  /** Ids that resolved successfully. */
  succeeded: string[]
  /** Ids that rejected, paired with the first error message. */
  failed: Array<{ id: string; error: string }>
}

async function runBulk(
  ids: readonly string[],
  action: (id: string) => Promise<void>,
): Promise<BulkCandidateActionResult> {
  const outcomes = await Promise.allSettled(
    ids.map(async (id) => {
      await action(id)
      return id
    }),
  )
  const succeeded: string[] = []
  const failed: Array<{ id: string; error: string }> = []
  outcomes.forEach((outcome, index) => {
    const id = ids[index]
    if (outcome.status === 'fulfilled') {
      succeeded.push(id)
    } else {
      const reason = outcome.reason
      const message = reason instanceof Error ? reason.message : String(reason)
      failed.push({ id, error: message })
    }
  })
  return { succeeded, failed }
}

/** Approve N candidates in parallel. Falls back to single-item endpoints. */
export const bulkApproveRagCandidates = (
  ids: readonly string[],
): Promise<BulkCandidateActionResult> => runBulk(ids, approveRagCandidate)

/** Reject N candidates in parallel. Falls back to single-item endpoints. */
export const bulkRejectRagCandidates = (
  ids: readonly string[],
): Promise<BulkCandidateActionResult> => runBulk(ids, rejectRagCandidate)

export const getRagStatusStats = async (): Promise<RagStatusStat[]> => {
  const raw = await api.get('admin/rag-analytics/status', { searchParams: { limit: 200 } }).json()
  return snakeToCamel(raw) as RagStatusStat[]
}

export const getRagChannelStats = (): Promise<RagChannelStat[]> =>
  api.get('admin/rag-analytics/by-channel', { searchParams: { limit: 200 } }).json()

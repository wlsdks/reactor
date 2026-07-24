export interface AddDocumentRequest {
  content: string
  metadata?: Record<string, unknown>
}

export interface AddDocumentResponse {
  id: string
  content: string
  metadata: Record<string, unknown>
}

export interface BatchAddDocumentRequest {
  documents: AddDocumentRequest[]
}

export interface BatchAddDocumentResponse {
  count: number
  ids: string[]
}

export interface SearchDocumentRequest {
  query: string
  topK?: number
  similarityThreshold?: number
}

export interface SearchResultResponse {
  id: string
  content: string
  metadata: Record<string, unknown>
  score: number | null
}

export type IngestionCandidateStatus = 'PENDING' | 'INGESTED' | 'REJECTED'

export interface IngestionCandidate {
  id: string
  runId: string
  channel: string | null
  query: string
  response: string
  status: IngestionCandidateStatus
  capturedAt: number
  reviewedAt: number | null
  reviewedBy: string | null
  reviewComment: string | null
  ingestedDocumentId: string | null
}

export interface RagIngestionPolicy {
  enabled: boolean
  requireReview: boolean
  allowedChannels: string[]
  minQueryChars: number
  minResponseChars: number
  blockedPatterns: string[]
  createdAt: number
  updatedAt: number
}

export interface RagIngestionPolicyState {
  configEnabled: boolean
  dynamicEnabled: boolean
  effective: RagIngestionPolicy
  stored: RagIngestionPolicy | null
}

export interface UpdateRagIngestionPolicyRequest {
  enabled: boolean
  requireReview: boolean
  allowedChannels: string[]
  minQueryChars: number
  minResponseChars: number
  blockedPatterns: string[]
}

/**
 * Single policy document entry sent to `/api/admin/rag/seed-policy`.
 *
 * Backend constraints (see PolicyRagSeedModels.kt):
 *  - `key`: NotBlank, ≤128 chars (stable identifier; re-seeding the same key overwrites)
 *  - `title`: NotBlank, ≤300 chars
 *  - `content`: NotBlank, ≤100,000 chars (markdown or plain text)
 *  - `category`: optional, ≤64 chars (e.g. "hr" / "security")
 *  - `spaceKey`: optional, ≤64 chars (Confluence space key)
 *  - `url`: optional, ≤500 chars (source document URL)
 */
export interface PolicySeedEntry {
  key: string
  title: string
  content: string
  category?: string
  spaceKey?: string
  url?: string
}

export interface PolicySeedRequest {
  entries: PolicySeedEntry[]
}

/**
 * Aggregate-only response from the bulk-seed endpoint. The backend swallows
 * individual entry failures (continuing the loop) so the only delta available
 * is `keys.length` vs the request size.
 */
export interface PolicySeedResponse {
  documentCount: number
  chunkCount: number
  keys: string[]
  durationMs: number
}

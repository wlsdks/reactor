import type {
  AddDocumentRequest,
  AddDocumentResponse,
  BatchAddDocumentRequest,
  BatchAddDocumentResponse,
  SearchDocumentRequest,
  SearchResultResponse,
  IngestionCandidate,
  IngestionCandidateStatus,
  RagIngestionPolicyState,
  UpdateRagIngestionPolicyRequest,
  PolicySeedEntry,
  PolicySeedResponse,
} from './types'
import { api } from '../../shared/api/client'

export interface StoredDocument {
  id: string
  content: string
  metadata: Record<string, unknown>
}

export const listDocuments = (limit = 100): Promise<StoredDocument[]> =>
  api.get('documents', { searchParams: { limit } }).json()

export const addDocument = (request: AddDocumentRequest): Promise<AddDocumentResponse> =>
  api.post('documents', { json: request }).json()

export const addDocumentsBatch = (request: BatchAddDocumentRequest): Promise<BatchAddDocumentResponse> =>
  api.post('documents/batch', { json: request }).json()

export const searchDocuments = (request: SearchDocumentRequest): Promise<SearchResultResponse[]> =>
  api.post('documents/search', { json: request }).json()

export const deleteDocuments = (ids: string[]): Promise<void> =>
  api.delete('documents', { json: { ids } }).json()

export const listIngestionCandidates = (
  status?: IngestionCandidateStatus,
  channel?: string,
  limit = 500,
): Promise<IngestionCandidate[]> => {
  const searchParams: Record<string, string> = { limit: String(limit) }
  if (status) searchParams.status = status
  if (channel) searchParams.channel = channel
  return api.get('rag-ingestion/candidates', { searchParams }).json()
}

export const acceptCandidate = (id: string, comment?: string): Promise<IngestionCandidate> =>
  api.post(`rag-ingestion/candidates/${id}/approve`, { json: { comment } }).json()

export const rejectCandidate = (id: string, comment?: string): Promise<IngestionCandidate> =>
  api.post(`rag-ingestion/candidates/${id}/reject`, { json: { comment } }).json()

export const getRagIngestionPolicy = (): Promise<RagIngestionPolicyState> =>
  api.get('rag-ingestion/policy').json()

export const updateRagIngestionPolicy = (request: UpdateRagIngestionPolicyRequest): Promise<void> =>
  api.put('rag-ingestion/policy', { json: request }).json()

export const resetRagIngestionPolicy = (): Promise<void> =>
  api.delete('rag-ingestion/policy').json()

/**
 * Bulk-seed policy documents into the RAG knowledge base.
 *
 * POSTs `/api/admin/rag/seed-policy` with the entries body. The backend
 * swallows individual entry failures (continuing the loop) so the only delta
 * available is `keys.length` vs the request size.
 *
 * BE constraints (PolicyRagSeedModels.kt): 1 ≤ entries ≤ 50, key ≤ 128,
 * title ≤ 300, content ≤ 100,000, category/spaceKey ≤ 64, url ≤ 500.
 */
export const seedPolicyDocuments = (
  entries: PolicySeedEntry[],
): Promise<PolicySeedResponse> =>
  api.post('admin/rag/seed-policy', { json: { entries } }).json()

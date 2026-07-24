import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  addDocument,
  addDocumentsBatch,
  searchDocuments,
  deleteDocuments,
  listIngestionCandidates,
  acceptCandidate,
  rejectCandidate,
  getRagIngestionPolicy,
  updateRagIngestionPolicy,
  resetRagIngestionPolicy,
  seedPolicyDocuments,
} from '../api'

const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
const mockApiPut = vi.fn()
const mockApiDelete = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: (...args: unknown[]) => mockApiPost(...args),
    put: (...args: unknown[]) => mockApiPut(...args),
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

describe('documents api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('addDocument sends POST and returns created document', async () => {
    const mockResponse = { id: 'doc-1', title: 'Test Doc', content: 'content' }
    mockApiPost.mockReturnValue(jsonResponse(mockResponse))

    const result = await addDocument({ title: 'Test Doc', content: 'content' })

    expect(mockApiPost).toHaveBeenCalledWith(
      'documents',
      expect.objectContaining({ json: { title: 'Test Doc', content: 'content' } }),
    )
    expect(result).toHaveProperty('id', 'doc-1')
  })

  it('addDocumentsBatch sends POST and returns batch response', async () => {
    const mockResponse = { added: 2, failed: 0 }
    mockApiPost.mockReturnValue(jsonResponse(mockResponse))

    const result = await addDocumentsBatch({ documents: [] })

    expect(mockApiPost).toHaveBeenCalledWith(
      'documents/batch',
      expect.objectContaining({ json: { documents: [] } }),
    )
    expect(result).toHaveProperty('added', 2)
  })

  it('searchDocuments sends POST and returns results array', async () => {
    const mockResults = [{ id: 'doc-1', score: 0.9, content: 'result' }]
    mockApiPost.mockReturnValue(jsonResponse(mockResults))

    const result = await searchDocuments({ query: 'test query', limit: 10 })

    expect(mockApiPost).toHaveBeenCalledWith(
      'documents/search',
      expect.objectContaining({ json: { query: 'test query', limit: 10 } }),
    )
    expect(Array.isArray(result)).toBe(true)
    expect(result[0]).toHaveProperty('score', 0.9)
  })

  it('deleteDocuments sends DELETE without error', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))

    await expect(deleteDocuments(['doc-1', 'doc-2'])).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith(
      'documents',
      expect.objectContaining({ json: { ids: ['doc-1', 'doc-2'] } }),
    )
  })

  it('listIngestionCandidates returns array with default limit', async () => {
    const mockCandidates = [{ id: 'cand-1', status: 'pending', channel: 'slack' }]
    mockApiGet.mockReturnValue(jsonResponse(mockCandidates))

    const result = await listIngestionCandidates()

    expect(mockApiGet).toHaveBeenCalledWith(
      'rag-ingestion/candidates',
      expect.objectContaining({ searchParams: expect.objectContaining({ limit: '500' }) }),
    )
    expect(Array.isArray(result)).toBe(true)
  })

  it('listIngestionCandidates passes status and channel filters', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await listIngestionCandidates('pending', 'slack')

    const callArg = mockApiGet.mock.calls[0][1]
    expect(callArg.searchParams.status).toBe('pending')
    expect(callArg.searchParams.channel).toBe('slack')
  })

  it('acceptCandidate sends POST to approve endpoint', async () => {
    const mockCandidate = { id: 'cand-1', status: 'approved' }
    mockApiPost.mockReturnValue(jsonResponse(mockCandidate))

    const result = await acceptCandidate('cand-1', 'looks good')

    expect(mockApiPost).toHaveBeenCalledWith(
      'rag-ingestion/candidates/cand-1/approve',
      expect.objectContaining({ json: { comment: 'looks good' } }),
    )
    expect(result).toHaveProperty('status', 'approved')
  })

  it('rejectCandidate sends POST to reject endpoint', async () => {
    const mockCandidate = { id: 'cand-1', status: 'rejected' }
    mockApiPost.mockReturnValue(jsonResponse(mockCandidate))

    const result = await rejectCandidate('cand-1', 'out of scope')

    expect(mockApiPost).toHaveBeenCalledWith(
      'rag-ingestion/candidates/cand-1/reject',
      expect.objectContaining({ json: { comment: 'out of scope' } }),
    )
    expect(result).toHaveProperty('status', 'rejected')
  })

  it('getRagIngestionPolicy returns policy state', async () => {
    const mockPolicy = { mode: 'auto', enabled: true }
    mockApiGet.mockReturnValue(jsonResponse(mockPolicy))

    const result = await getRagIngestionPolicy()

    expect(mockApiGet).toHaveBeenCalledWith('rag-ingestion/policy')
    expect(result).toHaveProperty('mode', 'auto')
  })

  it('updateRagIngestionPolicy sends PUT and resolves', async () => {
    mockApiPut.mockReturnValue(jsonResponse(null))

    await expect(updateRagIngestionPolicy({ mode: 'manual' })).resolves.not.toThrow()

    expect(mockApiPut).toHaveBeenCalledWith(
      'rag-ingestion/policy',
      expect.objectContaining({ json: { mode: 'manual' } }),
    )
  })

  it('resetRagIngestionPolicy sends DELETE and resolves', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))

    await expect(resetRagIngestionPolicy()).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith('rag-ingestion/policy')
  })

  it('seedPolicyDocuments POSTs to admin/rag/seed-policy with the entries body', async () => {
    const response = { documentCount: 2, chunkCount: 8, keys: ['k1', 'k2'], durationMs: 350 }
    mockApiPost.mockReturnValue(jsonResponse(response))

    const entries = [
      { key: 'k1', title: 'T1', content: 'C1' },
      { key: 'k2', title: 'T2', content: 'C2' },
    ]

    await expect(seedPolicyDocuments(entries)).resolves.toEqual(response)
    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/rag/seed-policy',
      expect.objectContaining({ json: { entries } }),
    )
  })

  it('seedPolicyDocuments forwards optional category/spaceKey/url', async () => {
    const response = { documentCount: 1, chunkCount: 2, keys: ['k1'], durationMs: 50 }
    mockApiPost.mockReturnValue(jsonResponse(response))

    const entries = [
      {
        key: 'k1',
        title: 'T1',
        content: 'C1',
        category: 'safety',
        spaceKey: 'engineering',
        url: 'https://example.com/doc',
      },
    ]

    await seedPolicyDocuments(entries)
    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/rag/seed-policy',
      expect.objectContaining({ json: { entries } }),
    )
  })
})

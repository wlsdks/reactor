import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  getCacheStats,
  invalidateCache,
  getVectorStoreStats,
  getRagPolicy,
  updateRagPolicy,
  resetRagPolicy,
  searchDocuments,
  listRagCandidates,
  approveRagCandidate,
  rejectRagCandidate,
  getRagStatusStats,
  getRagChannelStats,
  bulkApproveRagCandidates,
  bulkRejectRagCandidates,
  askGroundedRag,
  promoteWeakRagAnswer,
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

function emptyResponse() {
  return Promise.resolve({})
}

describe('rag-cache api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('getCacheStats sends GET to admin/platform/cache/stats', async () => {
    const mockStats = {
      enabled: true,
      semanticEnabled: true,
      totalExactHits: 100,
      totalSemanticHits: 50,
      totalMisses: 30,
      hitRate: 0.83,
      config: {
        ttlMinutes: 60,
        maxSize: 1000,
        similarityThreshold: 0.85,
        maxCandidates: 10,
        cacheableTemperature: 0.3,
      },
    }
    mockApiGet.mockReturnValue(jsonResponse(mockStats))

    const result = await getCacheStats()

    expect(mockApiGet).toHaveBeenCalledWith('admin/platform/cache/stats')
    expect(result).toHaveProperty('hitRate', 0.83)
    expect(result).toHaveProperty('totalExactHits', 100)
    expect(result.config).toHaveProperty('ttlMinutes', 60)
  })

  it('invalidateCache sends POST to admin/platform/cache/invalidate', async () => {
    const mockResponse = { invalidated: true, message: 'Cache cleared' }
    mockApiPost.mockReturnValue(jsonResponse(mockResponse))

    const result = await invalidateCache()

    expect(mockApiPost).toHaveBeenCalledWith('admin/platform/cache/invalidate')
    expect(result).toHaveProperty('invalidated', true)
    expect(result).toHaveProperty('message', 'Cache cleared')
  })

  it('getVectorStoreStats sends GET to admin/platform/vectorstore/stats', async () => {
    const mockStats = { available: true, documentCount: 42 }
    mockApiGet.mockReturnValue(jsonResponse(mockStats))

    const result = await getVectorStoreStats()

    expect(mockApiGet).toHaveBeenCalledWith('admin/platform/vectorstore/stats')
    expect(result).toHaveProperty('available', true)
    expect(result).toHaveProperty('documentCount', 42)
  })

  it('getRagPolicy sends GET to rag-ingestion/policy and returns policy state', async () => {
    const mockPolicyState = {
      configEnabled: true,
      dynamicEnabled: true,
      effective: {
        enabled: true,
        requireReview: true,
        allowedChannels: ['web', 'slack'],
        minQueryChars: 10,
        minResponseChars: 20,
        blockedPatterns: [],
      },
      stored: null,
    }
    mockApiGet.mockReturnValue(jsonResponse(mockPolicyState))

    const result = await getRagPolicy()

    expect(mockApiGet).toHaveBeenCalledWith('rag-ingestion/policy')
    expect(result).toHaveProperty('configEnabled', true)
    expect(result.effective).toHaveProperty('allowedChannels', ['web', 'slack'])
    expect(result).toHaveProperty('stored', null)
  })

  it('updateRagPolicy sends PUT with form values', async () => {
    mockApiPut.mockReturnValue(emptyResponse())

    await updateRagPolicy({
      enabled: true,
      requireReview: true,
      allowedChannels: ['a'],
      minQueryChars: 5,
      minResponseChars: 10,
      blockedPatterns: ['foo'],
    })

    expect(mockApiPut).toHaveBeenCalledWith(
      'rag-ingestion/policy',
      expect.objectContaining({
        json: expect.objectContaining({ enabled: true, allowedChannels: ['a'] }),
      }),
    )
  })

  it('resetRagPolicy sends DELETE to rag-ingestion/policy', async () => {
    mockApiDelete.mockReturnValue(emptyResponse())

    await resetRagPolicy()

    expect(mockApiDelete).toHaveBeenCalledWith('rag-ingestion/policy')
  })

  it('searchDocuments sends POST with query and topK', async () => {
    const mockResults = [{ id: 'doc-1', score: 0.92, content: 'result' }]
    mockApiPost.mockReturnValue(jsonResponse(mockResults))

    const result = await searchDocuments('test query', 5)

    expect(mockApiPost).toHaveBeenCalledWith(
      'documents/search',
      expect.objectContaining({ json: { query: 'test query', topK: 5 } }),
    )
    expect(Array.isArray(result)).toBe(true)
    expect(result).toHaveLength(1)
  })

  it('askGroundedRag runs the research profile and normalizes citation evidence', async () => {
    mockApiPost.mockReturnValue(jsonResponse({
      content: 'Grounded answer [doc_policy:0]',
      success: true,
      grounded: true,
      model: 'ollama:gemma4:12b',
      durationMs: 120,
      metadata: {
        runId: 'run-grounded-1',
        research_plan: {
          evidenceStatus: 'grounded',
          citationIds: ['doc_policy:0'],
          sourceLabels: ['policy://release'],
          retrievalSummary: {
            ragToolResultCount: 1,
            chunkCount: 2,
            citationCount: 1,
            citationStatus: 'grounded',
          },
          answerExtraction: {
            status: 'available',
            matchedCitationCount: 1,
            hashMismatchCount: 0,
            missingChunkCount: 0,
          },
          recoverySteps: ['retry_with_grounded_rag'],
          answerContract: {
            status: 'grounded',
            citationIds: ['doc_policy:0'],
            sourceLabels: ['policy://release'],
            citationStyle: 'manifest_ids',
            uncitedClaimsAllowed: false,
          },
        },
      },
    }))

    await expect(askGroundedRag('  release policy?  ')).resolves.toMatchObject({
      query: 'release policy?',
      status: 'grounded',
      runId: 'run-grounded-1',
      citationIds: ['doc_policy:0'],
      sourceLabels: ['policy://release'],
      retrievalSummary: {
        ragToolResultCount: 1,
        chunkCount: 2,
        citationCount: 1,
        citationStatus: 'grounded',
      },
      answerExtraction: {
        status: 'available',
        matchedCitationCount: 1,
        hashMismatchCount: 0,
        missingChunkCount: 0,
      },
      recoverySteps: ['retry_with_grounded_rag'],
    })
    expect(mockApiPost).toHaveBeenCalledWith('chat', {
      json: {
        message: 'release policy?',
        graphProfile: 'research',
        responseFormat: 'TEXT',
        metadata: { diagnosticSource: 'admin-rag-answer-probe' },
      },
    })
  })

  it('askGroundedRag classifies a successful response without citations as weak', async () => {
    mockApiPost.mockReturnValue(jsonResponse({
      content: 'Evidence is unavailable.',
      success: true,
      grounded: false,
      blockReason: 'missing_research_evidence:rag_citations',
      metadata: {
        runId: 'run-weak-1',
        research_plan: {
          evidenceStatus: 'missing',
          missingEvidence: ['rag_citations'],
          operatorAction: 'retry_with_grounded_rag',
        },
      },
    }))

    await expect(askGroundedRag('missing answer')).resolves.toMatchObject({
      status: 'weak',
      runId: 'run-weak-1',
      missingEvidence: ['rag_citations'],
      operatorAction: 'retry_with_grounded_rag',
    })
  })

  it('promoteWeakRagAnswer preserves run provenance and eval workflow tags', async () => {
    mockApiPost.mockReturnValue(jsonResponse({
      feedbackId: 'fb-weak-1',
      reviewStatus: 'inbox',
      runId: 'run-weak-1',
      readyNextActionIds: ['promote-eval-case'],
    }))

    const result = await promoteWeakRagAnswer(
      {
        query: 'missing answer',
        content: 'Evidence is unavailable.',
        success: true,
        status: 'weak',
        runId: 'run-weak-1',
        model: 'ollama:gemma4:12b',
        durationMs: 120,
        grounded: false,
        evidenceStatus: 'missing',
        citationIds: ['doc_policy:0'],
        sourceLabels: [],
        missingEvidence: ['source_labels'],
        operatorAction: 'retry_with_source_labeled_rag',
        blockReason: 'missing_research_evidence:source_labels',
        answerContract: null,
        retrievalSummary: null,
        answerExtraction: null,
        recoverySteps: ['verify_rag_citations_include_source_uri'],
      },
      { expectedDocumentId: 'doc-policy' },
    )

    expect(result).toEqual({
      feedbackId: 'fb-weak-1',
      reviewStatus: 'inbox',
      runId: 'run-weak-1',
      nextActionIds: ['promote-eval-case'],
    })
    expect(mockApiPost).toHaveBeenCalledWith('feedback', {
      json: expect.objectContaining({
        rating: 'thumbs_down',
        runId: 'run-weak-1',
        source: 'admin-rag-answer-probe',
        toolsUsed: ['Rag:hybrid_search'],
        tags: [
          'documents-ask',
          'citation-failure',
          'collection:rag-ingestion-candidate',
          'expected-document:doc-policy',
          'expected-citation:doc_policy:0',
        ],
        comment: expect.stringContaining('expectedDocumentId=doc-policy'),
      }),
    })
  })

  it('listRagCandidates sends GET with limit=200 and no filters by default', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await listRagCandidates()

    expect(mockApiGet).toHaveBeenCalledWith(
      'rag-ingestion/candidates',
      expect.objectContaining({ searchParams: { limit: 200 } }),
    )
  })

  it('listRagCandidates merges status and channel filters', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await listRagCandidates({ status: 'PENDING', channel: 'web' })

    expect(mockApiGet).toHaveBeenCalledWith(
      'rag-ingestion/candidates',
      expect.objectContaining({
        searchParams: { limit: 200, status: 'PENDING', channel: 'web' },
      }),
    )
  })

  it('approveRagCandidate sends POST to approve endpoint', async () => {
    mockApiPost.mockReturnValue(emptyResponse())

    await approveRagCandidate('abc-123')

    expect(mockApiPost).toHaveBeenCalledWith('rag-ingestion/candidates/abc-123/approve')
  })

  it('rejectRagCandidate sends POST to reject endpoint', async () => {
    mockApiPost.mockReturnValue(emptyResponse())

    await rejectRagCandidate('abc-123')

    expect(mockApiPost).toHaveBeenCalledWith('rag-ingestion/candidates/abc-123/reject')
  })

  it('getRagStatusStats sends GET to admin/rag-analytics/status with limit and normalizes evidence timestamps', async () => {
    mockApiGet.mockReturnValue(jsonResponse([
      { status: 'INGESTED', count: 2, latest_captured: '2026-04-05T12:00:00Z' },
    ]))

    await expect(getRagStatusStats()).resolves.toEqual([
      { status: 'INGESTED', count: 2, latestCaptured: '2026-04-05T12:00:00Z' },
    ])

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/rag-analytics/status',
      expect.objectContaining({ searchParams: { limit: 200 } }),
    )
  })

  it('getRagChannelStats sends GET to admin/rag-analytics/by-channel with limit', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await getRagChannelStats()

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/rag-analytics/by-channel',
      expect.objectContaining({ searchParams: { limit: 200 } }),
    )
  })

  it('bulkApproveRagCandidates fan-outs to N approve calls and returns success list', async () => {
    mockApiPost.mockReturnValue(emptyResponse())

    const result = await bulkApproveRagCandidates(['a', 'b', 'c'])

    expect(mockApiPost).toHaveBeenCalledTimes(3)
    expect(mockApiPost).toHaveBeenCalledWith('rag-ingestion/candidates/a/approve')
    expect(mockApiPost).toHaveBeenCalledWith('rag-ingestion/candidates/b/approve')
    expect(mockApiPost).toHaveBeenCalledWith('rag-ingestion/candidates/c/approve')
    expect(result.succeeded).toEqual(['a', 'b', 'c'])
    expect(result.failed).toEqual([])
  })

  it('bulkRejectRagCandidates fan-outs to N reject calls', async () => {
    mockApiPost.mockReturnValue(emptyResponse())

    const result = await bulkRejectRagCandidates(['x', 'y'])

    expect(mockApiPost).toHaveBeenCalledTimes(2)
    expect(mockApiPost).toHaveBeenCalledWith('rag-ingestion/candidates/x/reject')
    expect(mockApiPost).toHaveBeenCalledWith('rag-ingestion/candidates/y/reject')
    expect(result.succeeded).toEqual(['x', 'y'])
    expect(result.failed).toEqual([])
  })

  it('bulkApproveRagCandidates records partial failures without short-circuiting', async () => {
    mockApiPost.mockImplementation((url: string) => {
      if (url.includes('/b/')) return Promise.reject(new Error('boom'))
      return emptyResponse()
    })

    const result = await bulkApproveRagCandidates(['a', 'b', 'c'])

    expect(result.succeeded).toEqual(['a', 'c'])
    expect(result.failed).toEqual([{ id: 'b', error: 'boom' }])
  })

  it('bulkApproveRagCandidates returns empty result for empty id list', async () => {
    const result = await bulkApproveRagCandidates([])
    expect(mockApiPost).not.toHaveBeenCalled()
    expect(result).toEqual({ succeeded: [], failed: [] })
  })
})

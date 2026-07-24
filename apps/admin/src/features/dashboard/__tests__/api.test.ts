import { describe, it, expect, vi, afterEach } from 'vitest'
import { getDashboard, listMetricNames } from '../api'

const mockApiGet = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

const mockDashboard = {
  metrics: [
    { name: 'total_sessions', value: 100 },
    { name: 'active_users', value: 25 },
  ],
  updatedAt: '2026-03-01T00:00:00Z',
}

describe('dashboard api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('getDashboard without names calls ops/dashboard without searchParams', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockDashboard))

    const result = await getDashboard()

    expect(mockApiGet).toHaveBeenCalledWith('ops/dashboard')
    expect(result).toHaveProperty('metrics')
  })

  it('getDashboard with empty names array calls without searchParams', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockDashboard))

    await getDashboard([])

    expect(mockApiGet).toHaveBeenCalledWith('ops/dashboard')
  })

  it('getDashboard with names array passes them as searchParams', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockDashboard))

    await getDashboard(['total_sessions', 'active_users'])

    expect(mockApiGet).toHaveBeenCalledWith(
      'ops/dashboard',
      expect.objectContaining({ searchParams: expect.any(URLSearchParams) }),
    )
    const sp: URLSearchParams = mockApiGet.mock.calls[0][1].searchParams
    expect(sp.getAll('names')).toEqual(['total_sessions', 'active_users'])
  })

  it('getDashboard preserves v1.1 release readiness facets', async () => {
    const readinessDashboard = {
      ...mockDashboard,
      releaseReadiness: {
        status: 'eligible_with_warnings',
        recommendedTag: 'v1.1.0',
        recommendedVersionBump: 'minor',
        minorEligible: true,
        warnings: [
          {
            name: 'hardening_suite',
            status: 'review_required',
            source: 'memoryMaintenanceLifecycle.dependencyWarnings',
            remediationCommand: 'monitor upstream trustcall/langmem compatibility',
            reviewCommand: 'uv pip show langmem trustcall langgraph',
          },
        ],
        tagRecommendation: {
          releaseReadinessCommand: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
        },
        productCapabilityBoundary: {
          capability: 'rag_ingest_to_feedback_eval_langsmith_readiness',
          minorEligible: true,
          evidence: ['rag_ingestion_lifecycle', 'release_readiness_command'],
          sourceReport: 'langsmith_eval_sync',
          status: 'passed',
        },
        ragIngestionLifecycle: {
          status: 'verified',
          researchAnswerContract: {
            requiresCitationIds: true,
            uncitedClaimsAllowed: false,
          },
        },
        feedbackReviewQueue: {
          reviewStatus: 'reviewed',
          caseIds: ['case_rag_candidate_grounded_citation'],
        },
        langsmithSync: {
          datasetName: 'reactor-rag-ingestion-candidate',
          metadataCaseIds: ['case_rag_candidate_grounded_citation'],
        },
        backendProviderIntegration: {
          status: 'verified',
          provider: 'ollama',
          usageMetadata: {
            present: true,
            totalMatchesBreakdown: true,
          },
        },
      },
    }
    mockApiGet.mockReturnValue(jsonResponse(readinessDashboard))

    const result = await getDashboard(['reactor.release.readiness'])

    expect(result.releaseReadiness?.recommendedVersionBump).toBe('minor')
    expect(result.releaseReadiness?.warnings?.[0]?.reviewCommand).toBe('uv pip show langmem trustcall langgraph')
    expect(result.releaseReadiness?.tagRecommendation?.releaseReadinessCommand).toContain('reactor-release-smoke-run')
    expect(result.releaseReadiness?.productCapabilityBoundary?.capability).toBe('rag_ingest_to_feedback_eval_langsmith_readiness')
    expect(result.releaseReadiness?.productCapabilityBoundary?.evidence).toContain('release_readiness_command')
    expect(result.releaseReadiness?.ragIngestionLifecycle?.researchAnswerContract?.requiresCitationIds).toBe(true)
    expect(result.releaseReadiness?.feedbackReviewQueue?.caseIds).toContain('case_rag_candidate_grounded_citation')
    expect(result.releaseReadiness?.langsmithSync?.metadataCaseIds).toContain('case_rag_candidate_grounded_citation')
    expect(result.releaseReadiness?.backendProviderIntegration?.usageMetadata?.totalMatchesBreakdown).toBe(true)
  })

  it('listMetricNames returns array of strings', async () => {
    mockApiGet.mockReturnValue(jsonResponse(['total_sessions', 'active_users', 'error_rate']))

    const result = await listMetricNames()

    expect(mockApiGet).toHaveBeenCalledWith('ops/metrics/names', { searchParams: { limit: 200 } })
    expect(Array.isArray(result)).toBe(true)
    expect(result).toContain('total_sessions')
  })
})

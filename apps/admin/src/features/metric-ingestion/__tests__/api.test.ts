import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  ingestMcpHealth,
  ingestToolCall,
  ingestEvalResult,
  ingestEvalResults,
  ingestMcpHealthBatch,
} from '../api'

const mockApiPost = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: vi.fn(),
    post: (...args: unknown[]) => mockApiPost(...args),
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

describe('metric-ingestion api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('ingestMcpHealth sends POST to mcp-health endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ accepted: true }))

    const result = await ingestMcpHealth({
      tenantId: 'default',
      serverName: 'atlassian',
      status: 'healthy',
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/metrics/ingest/mcp-health',
      expect.objectContaining({ json: expect.objectContaining({ serverName: 'atlassian' }) }),
    )
    expect(result).toHaveProperty('accepted', true)
  })

  it('ingestToolCall sends POST to tool-call endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ ingested: 1 }))

    const result = await ingestToolCall({
      tenantId: 'default',
      runId: 'run-1',
      toolName: 'create_issue',
      durationMs: 250,
      success: true,
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/metrics/ingest/tool-call',
      expect.objectContaining({ json: expect.objectContaining({ toolName: 'create_issue' }) }),
    )
    expect(result).toHaveProperty('ingested', 1)
  })

  it('ingestEvalResult sends POST to eval-result endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ jobId: 'job-1' }))

    const result = await ingestEvalResult({
      tenantId: 'default',
      evalRunId: 'eval-1',
      testCaseId: 'case-1',
      score: 0.95,
      pass: true,
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/metrics/ingest/eval-result',
      expect.objectContaining({ json: expect.objectContaining({ evalRunId: 'eval-1' }) }),
    )
    expect(result).toHaveProperty('jobId', 'job-1')
  })

  it('ingestEvalResults sends POST to eval-results endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ batchId: 'batch-1', count: 5 }))

    const result = await ingestEvalResults({
      tenantId: 'default',
      evalRunId: 'run-1',
      results: [],
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/metrics/ingest/eval-results',
      expect.objectContaining({ json: expect.objectContaining({ evalRunId: 'run-1' }) }),
    )
    expect(result).toHaveProperty('batchId', 'batch-1')
  })

  it('ingestMcpHealthBatch sends POST to batch endpoint with array', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ accepted: 3 }))

    const requests = [
      { tenantId: 'default', serverName: 'atlassian', status: 'healthy' },
      { tenantId: 'default', serverName: 'swagger', status: 'degraded' },
      { tenantId: 'default', serverName: 'github', status: 'healthy' },
    ]

    const result = await ingestMcpHealthBatch(requests)

    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/metrics/ingest/batch',
      expect.objectContaining({ json: requests }),
    )
    expect(result).toHaveProperty('accepted', 3)
  })
})

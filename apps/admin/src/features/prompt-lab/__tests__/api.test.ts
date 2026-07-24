import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  listExperiments,
  createExperiment,
  getExperiment,
  getExperimentStatus,
  getExperimentTrials,
  getExperimentReport,
  runExperiment,
  cancelExperiment,
  activateExperimentRecommendation,
  deleteExperiment,
  autoOptimize,
  analyzeFeedback,
} from '../api'

const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
const mockApiDelete = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: (...args: unknown[]) => mockApiPost(...args),
    put: vi.fn(),
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

const mockExperiment = {
  id: 'exp-1',
  name: 'Greeting A/B test',
  status: 'pending',
  templateId: 'tmpl-1',
  createdAt: '2026-03-01T00:00:00Z',
}

describe('prompt-lab api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('listExperiments returns array without status filter', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockExperiment]))

    const result = await listExperiments()

    expect(mockApiGet).toHaveBeenCalledWith('prompt-lab/experiments', { searchParams: { limit: 200 } })
    expect(Array.isArray(result)).toBe(true)
    expect(result[0].id).toBe('exp-1')
  })

  it('listExperiments passes status filter as searchParam', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await listExperiments('running')

    expect(mockApiGet).toHaveBeenCalledWith(
      'prompt-lab/experiments',
      expect.objectContaining({ searchParams: expect.objectContaining({ status: 'running', limit: 200 }) }),
    )
  })

  it('createExperiment sends POST and returns created experiment', async () => {
    mockApiPost.mockReturnValue(jsonResponse(mockExperiment))

    const result = await createExperiment({
      name: 'Greeting A/B test',
      templateId: 'tmpl-1',
      variants: [],
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'prompt-lab/experiments',
      expect.objectContaining({ json: expect.objectContaining({ name: 'Greeting A/B test' }) }),
    )
    expect(result.id).toBe('exp-1')
  })

  it('getExperiment returns experiment by id', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockExperiment))

    const result = await getExperiment('exp-1')

    expect(mockApiGet).toHaveBeenCalledWith('prompt-lab/experiments/exp-1')
    expect(result.name).toBe('Greeting A/B test')
  })

  it('getExperimentStatus returns status response', async () => {
    const mockStatus = { id: 'exp-1', status: 'running', progress: 0.5 }
    mockApiGet.mockReturnValue(jsonResponse(mockStatus))

    const result = await getExperimentStatus('exp-1')

    expect(mockApiGet).toHaveBeenCalledWith('prompt-lab/experiments/exp-1/status')
    expect(result).toHaveProperty('status', 'running')
  })

  it('getExperimentTrials returns array of trials', async () => {
    const mockTrials = [{ id: 'trial-1', variant: 'A', score: 0.8 }]
    mockApiGet.mockReturnValue(jsonResponse(mockTrials))

    const result = await getExperimentTrials('exp-1')

    expect(mockApiGet).toHaveBeenCalledWith('prompt-lab/experiments/exp-1/trials')
    expect(Array.isArray(result)).toBe(true)
  })

  it('getExperimentReport returns report data', async () => {
    const mockReport = { experimentId: 'exp-1', winner: 'B', confidence: 0.95 }
    mockApiGet.mockReturnValue(jsonResponse(mockReport))

    const result = await getExperimentReport('exp-1')

    expect(mockApiGet).toHaveBeenCalledWith('prompt-lab/experiments/exp-1/report')
    expect(result).toHaveProperty('winner', 'B')
  })

  it('runExperiment sends POST to run endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse(null))

    await expect(runExperiment('exp-1')).resolves.not.toThrow()

    expect(mockApiPost).toHaveBeenCalledWith('prompt-lab/experiments/exp-1/run')
  })

  it('cancelExperiment sends POST to cancel endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse(null))

    await expect(cancelExperiment('exp-1')).resolves.not.toThrow()

    expect(mockApiPost).toHaveBeenCalledWith('prompt-lab/experiments/exp-1/cancel')
  })

  it('activateExperimentRecommendation sends POST to activate endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse(null))

    await expect(activateExperimentRecommendation('exp-1')).resolves.not.toThrow()

    expect(mockApiPost).toHaveBeenCalledWith('prompt-lab/experiments/exp-1/activate')
  })

  it('deleteExperiment sends DELETE without error', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))

    await expect(deleteExperiment('exp-1')).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith('prompt-lab/experiments/exp-1')
  })

  it('autoOptimize sends POST and returns job info', async () => {
    const mockResult = { status: 'started', templateId: 'tmpl-1', jobId: 'job-1' }
    mockApiPost.mockReturnValue(jsonResponse(mockResult))

    const result = await autoOptimize({ templateId: 'tmpl-1', feedback: [] })

    expect(mockApiPost).toHaveBeenCalledWith(
      'prompt-lab/auto-optimize',
      expect.objectContaining({ json: { templateId: 'tmpl-1', feedback: [] } }),
    )
    expect(result.jobId).toBe('job-1')
  })

  it('analyzeFeedback sends POST and returns analysis', async () => {
    const mockAnalysis = { templateId: 'tmpl-1', topIssues: ['too verbose'], suggestions: [] }
    mockApiPost.mockReturnValue(jsonResponse(mockAnalysis))

    const result = await analyzeFeedback({ templateId: 'tmpl-1', feedbackIds: ['fb-1'] })

    expect(mockApiPost).toHaveBeenCalledWith(
      'prompt-lab/analyze',
      expect.objectContaining({ json: { templateId: 'tmpl-1', feedbackIds: ['fb-1'] } }),
    )
    expect(result).toHaveProperty('topIssues')
  })
})

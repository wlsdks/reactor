import { describe, it, expect, vi, afterEach } from 'vitest'
import * as evalsApi from '../api'

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: vi.fn().mockReturnValue({
      json: vi.fn(),
    }),
    post: vi.fn().mockReturnValue({
      json: vi.fn(),
    }),
  },
}))

import { api } from '../../../shared/api/client'

const mockedApi = vi.mocked(api)

afterEach(() => {
  vi.clearAllMocks()
})

describe('evals api', () => {
  it('getEvalRuns calls correct endpoint with days param', async () => {
    const mockData = [{ eval_run_id: 'run-1', total_cases: 10, pass_count: 8 }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await evalsApi.getEvalRuns(30)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/evals/runs', {
      searchParams: { days: 30 },
    })
    // Result is transformed via snakeToCamel
    expect(result).toEqual([{ evalRunId: 'run-1', totalCases: 10, passCount: 8 }])
  })

  it('getEvalPassRate calls correct endpoint', async () => {
    const mockData = [{ day: '2026-04-01', total: 10, passed: 8, avg_score: 0.85 }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await evalsApi.getEvalPassRate(30)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/evals/pass-rate', {
      searchParams: { days: 30 },
    })
    expect(result).toEqual([{ day: '2026-04-01', total: 10, passed: 8, avgScore: 0.85 }])
  })

  it('getEvalRuns defaults to 30 days', async () => {
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue([]) })

    await evalsApi.getEvalRuns()

    expect(mockedApi.get).toHaveBeenCalledWith('admin/evals/runs', {
      searchParams: { days: 30 },
    })
  })

  it('lists enabled persisted eval cases for operator sync', async () => {
    const mockData = [{ id: 'case-1', name: 'Case 1', enabled: true, source_run_id: 'run-1' }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await evalsApi.getPersistedEvalCases()

    expect(mockedApi.get).toHaveBeenCalledWith('admin/agent-eval/cases', {
      searchParams: { enabledOnly: true, limit: 100 },
    })
    expect(result).toEqual([{ id: 'case-1', name: 'Case 1', enabled: true, sourceRunId: 'run-1' }])
  })

  it('syncs all enabled persisted cases when caseIds are omitted', async () => {
    const syncResult = {
      ok: true,
      status: 'passed',
      datasetName: 'reactor-admin-persisted-eval-cases',
      caseIds: ['case-1'],
      metadataCaseIds: ['case-1'],
      exampleIds: ['example-1'],
      splitCounts: { regression: 1 },
      secretFree: true,
    }
    mockedApi.post = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(syncResult) })

    const result = await evalsApi.syncPersistedEvalCases('reactor-admin-persisted-eval-cases')

    expect(mockedApi.post).toHaveBeenCalledWith('admin/agent-eval/langsmith/sync', {
      json: {
        datasetName: 'reactor-admin-persisted-eval-cases',
        caseIds: [],
        description: 'Reactor admin persisted eval case dataset sync',
      },
    })
    expect(result).toEqual(syncResult)
  })
})

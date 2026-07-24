import { describe, it, expect, vi, afterEach } from 'vitest'
import * as usageApi from '../api'

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: vi.fn().mockReturnValue({
      json: vi.fn(),
    }),
  },
}))

import { api } from '../../../shared/api/client'

const mockedApi = vi.mocked(api)

afterEach(() => {
  vi.clearAllMocks()
})

describe('usage api', () => {
  it('getUsersCost calls correct endpoint with days and limit', async () => {
    const mockData = [{ user_id: 'user-001', session_count: 10 }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await usageApi.getUsersCost(30, 20)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/users/usage/cost', {
      searchParams: { days: 30, limit: 20 },
    })
    expect(result).toEqual([{
      userId: 'user-001',
      sessionCount: 10,
      totalTokens: 0,
      totalCostUsd: 0,
      avgLatencyMs: 0,
      lastActivity: '',
    }])
  })

  it('getUsersCost defaults to 30 days and 20 limit', async () => {
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue([]) })

    await usageApi.getUsersCost()

    expect(mockedApi.get).toHaveBeenCalledWith('admin/users/usage/cost', {
      searchParams: { days: 30, limit: 20 },
    })
  })

  it('getUsageDaily calls correct endpoint with days', async () => {
    const mockData = [{ day: '2026-04-01', session_count: 50 }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await usageApi.getUsageDaily(7)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/users/usage/daily', {
      searchParams: { days: 7 },
    })
    expect(result).toEqual([{
      day: '2026-04-01',
      sessionCount: 50,
      totalTokens: 0,
      totalCostUsd: 0,
      uniqueUsers: 0,
    }])
  })

  it('getUsageByModel sends only the supported days parameter and normalizes fields', async () => {
    const mockData = [{ model: 'gemma4:12b', provider: 'ollama', call_count: 2, total_tokens: 42 }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await usageApi.getUsageByModel(30)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/users/usage/by-model', {
      searchParams: { days: 30 },
    })
    expect(result[0]).toMatchObject({ model: 'gemma4:12b', provider: 'ollama', callCount: 2, totalTokens: 42 })
  })

  it('drops malformed rows instead of trusting a broad cast', async () => {
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue([null, { session_count: 1 }, { user_id: 'u-1', total_cost_usd: '1.25' }]) })

    await expect(usageApi.getUsersCost()).resolves.toEqual([expect.objectContaining({ userId: 'u-1', totalCostUsd: 1.25 })])
  })
})

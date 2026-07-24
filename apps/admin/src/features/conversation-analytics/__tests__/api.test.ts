import { describe, it, expect, vi, afterEach } from 'vitest'
import * as convApi from '../api'

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

describe('conversation-analytics api', () => {
  it('getConversationsByChannel calls correct endpoint', async () => {
    const mockData = [{ channel: 'web', total: 100, success: 90, failure: 10, success_rate: 90.0, avg_duration_ms: 1200 }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await convApi.getConversationsByChannel(30)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/conversation-analytics/by-channel', {
      searchParams: { days: 30, limit: 200 },
    })
    expect(result).toEqual([{ channel: 'web', total: 100, success: 90, failure: 10, successRate: 90.0, avgDurationMs: 1200 }])
  })

  it('getFailurePatterns calls correct endpoint', async () => {
    const mockData = [{ error_class: 'LLM_TIMEOUT', count: 85, latest: '2026-04-05T12:00:00Z' }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await convApi.getFailurePatterns(30)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/conversation-analytics/failure-patterns', {
      searchParams: { days: 30, limit: 200 },
    })
    expect(result).toEqual([{ errorClass: 'LLM_TIMEOUT', count: 85, latest: '2026-04-05T12:00:00Z' }])
  })

  it('getLatencyDistribution calls correct endpoint', async () => {
    const mockData = [{ bucket: '< 1s', count: 820 }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await convApi.getLatencyDistribution(7)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/conversation-analytics/latency-distribution', {
      searchParams: { days: 7, limit: 200 },
    })
    expect(result).toEqual([{ bucket: '< 1s', count: 820 }])
  })

  it('getConversationsByChannel defaults to 30 days', async () => {
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue([]) })

    await convApi.getConversationsByChannel()

    expect(mockedApi.get).toHaveBeenCalledWith('admin/conversation-analytics/by-channel', {
      searchParams: { days: 30, limit: 200 },
    })
  })
})

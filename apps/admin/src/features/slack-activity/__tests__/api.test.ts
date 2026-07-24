import { describe, it, expect, vi, afterEach } from 'vitest'
import * as slackApi from '../api'

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

describe('slack-activity api', () => {
  it('getSlackChannels calls correct endpoint with days param', async () => {
    const mockData = [{ channel: '#general', session_count: 10, unique_users: 5, total_tokens: 1000, total_cost_usd: 1.5, avg_latency_ms: 300 }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await slackApi.getSlackChannels(30)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/slack-activity/channels', {
      searchParams: { days: 30, limit: 200 },
    })
    expect(result).toEqual([{ channel: '#general', sessionCount: 10, uniqueUsers: 5, totalTokens: 1000, totalCostUsd: 1.5, avgLatencyMs: 300 }])
  })

  it('getSlackDaily calls correct endpoint with days param', async () => {
    const mockData = [{ day: '2026-04-01', message_count: 50, unique_users: 10, success_count: 45, failure_count: 5 }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await slackApi.getSlackDaily(7)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/slack-activity/daily', {
      searchParams: { days: 7, limit: 200 },
    })
    expect(result).toEqual([{ day: '2026-04-01', messageCount: 50, uniqueUsers: 10, successCount: 45, failureCount: 5 }])
  })

  it('getSlackChannels defaults to 30 days', async () => {
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue([]) })

    await slackApi.getSlackChannels()

    expect(mockedApi.get).toHaveBeenCalledWith('admin/slack-activity/channels', {
      searchParams: { days: 30, limit: 200 },
    })
  })
})

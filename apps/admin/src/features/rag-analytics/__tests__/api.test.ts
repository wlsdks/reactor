import { describe, it, expect, vi, afterEach } from 'vitest'
import * as ragApi from '../api'

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

describe('rag-analytics api', () => {
  it('getRagStatus calls correct endpoint', async () => {
    const mockData = [{ status: 'PENDING', count: 24, latest_captured: '2026-04-05T12:00:00Z' }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await ragApi.getRagStatus()

    expect(mockedApi.get).toHaveBeenCalledWith('admin/rag-analytics/status', {
      searchParams: { limit: 200 },
    })
    expect(result).toEqual([{ status: 'PENDING', count: 24, latestCaptured: '2026-04-05T12:00:00Z' }])
  })

  it('getRagByChannel calls correct endpoint with days param', async () => {
    const mockData = [{ channel: '#support', candidate_count: 420, ingested: 380, pending: 15, rejected: 25 }]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockData) })

    const result = await ragApi.getRagByChannel(30)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/rag-analytics/by-channel', {
      searchParams: { days: 30, limit: 200 },
    })
    expect(result).toEqual([{ channel: '#support', candidateCount: 420, ingested: 380, pending: 15, rejected: 25 }])
  })

  it('getRagByChannel defaults to 30 days', async () => {
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue([]) })

    await ragApi.getRagByChannel()

    expect(mockedApi.get).toHaveBeenCalledWith('admin/rag-analytics/by-channel', {
      searchParams: { days: 30, limit: 200 },
    })
  })
})

import { describe, it, expect, vi, afterEach } from 'vitest'
import * as retentionApi from '../api'

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: vi.fn().mockReturnValue({
      json: vi.fn(),
    }),
    put: vi.fn().mockReturnValue({
      json: vi.fn(),
    }),
  },
}))

import { api } from '../../../shared/api/client'

const mockedApi = vi.mocked(api)

afterEach(() => {
  vi.clearAllMocks()
})

describe('retention api', () => {
  it('getRetentionPolicy calls correct endpoint', async () => {
    const mockPolicy = { sessionRetentionDays: 90, conversationRetentionDays: 365, auditRetentionDays: 730, metricRetentionDays: 180, checkpointRetentionDays: 90 }
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockPolicy) })

    const result = await retentionApi.getRetentionPolicy()

    expect(mockedApi.get).toHaveBeenCalledWith('admin/retention')
    expect(result).toEqual(mockPolicy)
  })

  it('updateRetentionPolicy calls PUT with data', async () => {
    const update = { sessionRetentionDays: 120 }
    const mockResponse = { sessionRetentionDays: 120, conversationRetentionDays: 365, auditRetentionDays: 730, metricRetentionDays: 180, checkpointRetentionDays: 90 }
    mockedApi.put = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockResponse) })

    const result = await retentionApi.updateRetentionPolicy(update)

    expect(mockedApi.put).toHaveBeenCalledWith('admin/retention', { json: update })
    expect(result).toEqual(mockResponse)
  })
})

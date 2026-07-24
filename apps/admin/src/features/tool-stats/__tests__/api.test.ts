import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getToolAccuracy, getToolStats } from '../api'

const mockApiGet = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: { get: (...args: unknown[]) => mockApiGet(...args) },
}))

beforeEach(() => mockApiGet.mockReset())

describe('tool-stats api', () => {
  it('getToolStats GETs admin/tools/stats with optional server filter', async () => {
    mockApiGet.mockReturnValueOnce({
      json: () =>
        Promise.resolve({
          total: 0,
          byOutcome: { ok: 0, error: 0, timeout: 0 },
          byServer: {},
          byTool: [],
          accuracy: 1,
        }),
    })

    await getToolStats({ server: 'atlassian' })

    expect(mockApiGet).toHaveBeenCalledWith('admin/tools/stats', {
      searchParams: { server: 'atlassian' },
    })
  })

  it('getToolStats omits server when not provided', async () => {
    mockApiGet.mockReturnValueOnce({
      json: () =>
        Promise.resolve({
          total: 0,
          byOutcome: {},
          byServer: {},
          byTool: [],
          accuracy: 0,
        }),
    })

    await getToolStats()

    expect(mockApiGet).toHaveBeenCalledWith('admin/tools/stats', {
      searchParams: {},
    })
  })

  it('getToolStats omits server when empty string', async () => {
    mockApiGet.mockReturnValueOnce({
      json: () =>
        Promise.resolve({
          total: 0,
          byOutcome: {},
          byServer: {},
          byTool: [],
          accuracy: 0,
        }),
    })

    await getToolStats({ server: '' })

    expect(mockApiGet).toHaveBeenCalledWith('admin/tools/stats', {
      searchParams: {},
    })
  })

  it('getToolAccuracy GETs admin/tools/accuracy', async () => {
    mockApiGet.mockReturnValueOnce({
      json: () =>
        Promise.resolve({
          total: 100,
          ok: 92,
          accuracy: 0.92,
          invalidCallRate: 0.02,
          timeoutRate: 0.01,
          notFoundRate: 0.05,
        }),
    })

    await expect(getToolAccuracy()).resolves.toEqual({
      total: 100,
      ok: 92,
      accuracy: 0.92,
      invalidCallRate: 0.02,
      timeoutRate: 0.01,
      notFoundRate: 0.05,
    })
    expect(mockApiGet).toHaveBeenCalledWith('admin/tools/accuracy')
  })
})

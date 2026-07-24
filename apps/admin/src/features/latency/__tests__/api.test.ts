import { describe, it, expect, vi, afterEach } from 'vitest'
import * as latencyApi from '../api'

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

describe('latency api', () => {
  it('getLatencyTimeSeries calls correct endpoint with days param and transforms response', async () => {
    const backendData = [
      { time: '2026-01-01T12:00:00Z', avgMs: 100, p95Ms: 500, count: 50 },
    ]
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(backendData) })

    const result = await latencyApi.getLatencyTimeSeries(7)

    expect(mockedApi.get).toHaveBeenCalledWith('admin/metrics/latency/timeseries', {
      searchParams: { days: 7, limit: 200 },
    })
    expect(result).toEqual([
      {
        timestamp: new Date('2026-01-01T12:00:00Z').getTime(),
        avg: 100,
        p95: 500,
        p95Available: 1,
        count: 50,
      },
    ])
  })

  it('normalizes the current bucket and averageMs contract without inventing p95', async () => {
    mockedApi.get = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue([
        { bucket: '2026-07-10T12:00:00+00:00', averageMs: 42, count: 2 },
      ]),
    })

    await expect(latencyApi.getLatencyTimeSeries(1)).resolves.toEqual([
      {
        timestamp: new Date('2026-07-10T12:00:00+00:00').getTime(),
        avg: 42,
        p95: 0,
        p95Available: 0,
        count: 2,
      },
    ])
  })

  it('drops malformed time-series rows and fail-closes non-finite metrics', async () => {
    mockedApi.get = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue([
        { bucket: 'not-a-date', averageMs: 100, count: 1 },
        { bucket: '2026-07-10T12:00:00Z', averageMs: 'NaN', count: Infinity },
      ]),
    })

    await expect(latencyApi.getLatencyTimeSeries()).resolves.toEqual([
      {
        timestamp: new Date('2026-07-10T12:00:00Z').getTime(),
        avg: 0,
        p95: 0,
        p95Available: 0,
        count: 0,
      },
    ])
  })

  it('getLatencyTimeSeries defaults to 1 day', async () => {
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue([]) })

    await latencyApi.getLatencyTimeSeries()

    expect(mockedApi.get).toHaveBeenCalledWith('admin/metrics/latency/timeseries', {
      searchParams: { days: 1, limit: 200 },
    })
  })

  it('getLatencySummary calls correct endpoint', async () => {
    const mockSummary = { p50: 100, p95: 500, p99: 1000 }
    mockedApi.get = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue(mockSummary) })

    const result = await latencyApi.getLatencySummary()

    expect(mockedApi.get).toHaveBeenCalledWith('admin/metrics/latency/summary')
    expect(result).toEqual({ ...mockSummary, count: 1 })
  })

  it('normalizes the current summary contract and its sample count', async () => {
    mockedApi.get = vi.fn().mockReturnValue({
      json: vi.fn().mockResolvedValue({ count: 2, p50Ms: 0, p95Ms: 12, p99Ms: 30 }),
    })

    await expect(latencyApi.getLatencySummary()).resolves.toEqual({
      count: 2,
      p50: 0,
      p95: 12,
      p99: 30,
    })
  })
})

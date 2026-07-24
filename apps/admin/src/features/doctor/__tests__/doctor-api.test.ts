import { describe, it, expect, vi, afterEach } from 'vitest'
import { getDoctorSummary, getDoctorReport } from '../api'

const mockApiGet = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: vi.fn(),
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

const mockSummary = {
  summary: '2 섹션 — OK 2',
  status: 'OK',
  generatedAt: '2026-04-13T00:00:00Z',
  allHealthy: true,
}

const mockReport = {
  generatedAt: '2026-04-13T00:00:00Z',
  status: 'WARN',
  allHealthy: true,
  summary: '2 sections - OK 1, WARN 1, ERROR 0, SKIPPED 0',
  sections: [
    {
      name: 'Database',
      status: 'OK',
      message: 'connected',
      checks: [{ name: 'ping', status: 'OK', detail: 'pg alive' }],
    },
    {
      name: 'Cache',
      status: 'WARN',
      message: 'redis latency high',
      checks: [{ name: 'latency', status: 'WARN', detail: '120ms' }],
    },
  ],
}

describe('doctor api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('getDoctorSummary calls api.get with correct endpoint', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockSummary))

    const result = await getDoctorSummary()

    expect(mockApiGet).toHaveBeenCalledWith('admin/doctor/summary', { throwHttpErrors: false })
    expect(result).toEqual(mockSummary)
  })

  it('getDoctorReport calls api.get with correct endpoint', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockReport))

    const result = await getDoctorReport()

    expect(mockApiGet).toHaveBeenCalledWith('admin/doctor', { throwHttpErrors: false })
    expect(result).toEqual(mockReport)
    expect(result.sections).toHaveLength(2)
  })
})

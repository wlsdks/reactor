import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  getOverview,
  getUsage,
  getQuality,
  getTools,
  getCost,
  getSlo,
  getTenantAlerts,
  getQuota,
  exportExecutionsCsv,
  exportToolsCsv,
} from '../api'

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

function textResponse(text: string) {
  return { text: () => Promise.resolve(text) }
}

describe('tenant-admin api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('getOverview passes tenant id and range using the backend contract', async () => {
    mockApiGet.mockReturnValue(jsonResponse({ totalRequests: 42, successRate: 0.98 }))

    const result = await getOverview('tenant-1', { fromMs: 100, toMs: 200 })

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/tenant/overview',
      expect.objectContaining({ headers: { 'X-Tenant-Id': 'tenant-1' } }),
    )
    expect(mockApiGet.mock.calls[0][1].searchParams).toEqual({ fromMs: '100', toMs: '200' })
    expect(result).toHaveProperty('totalRequests', 42)
  })

  it('getUsage passes tenant id and no searchParams when no range', async () => {
    mockApiGet.mockReturnValue(jsonResponse({ timeSeries: [], channelDistribution: {}, topUsers: [] }))

    await getUsage('tenant-1')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/tenant/usage',
      expect.objectContaining({ headers: { 'X-Tenant-Id': 'tenant-1' } }),
    )
    const callArg = mockApiGet.mock.calls[0][1]
    expect(callArg.searchParams).toBeUndefined()
  })

  it('getUsage passes fromMs and toMs as searchParams', async () => {
    mockApiGet.mockReturnValue(jsonResponse({ timeSeries: [], channelDistribution: {}, topUsers: [] }))

    await getUsage('tenant-1', { fromMs: 1700000000000, toMs: 1700100000000 })

    const callArg = mockApiGet.mock.calls[0][1]
    expect(callArg.searchParams.fromMs).toBe('1700000000000')
    expect(callArg.searchParams.toMs).toBe('1700100000000')
  })

  it('getQuality passes tenant id via header', async () => {
    mockApiGet.mockReturnValue(jsonResponse({ latencyP50: 120, latencyP95: 400, latencyP99: 800, errorDistribution: {} }))

    const result = await getQuality('tenant-1')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/tenant/quality',
      expect.objectContaining({ headers: { 'X-Tenant-Id': 'tenant-1' } }),
    )
    expect(result).toHaveProperty('latencyP99', 800)
  })

  it('getTools passes tenant id via header', async () => {
    mockApiGet.mockReturnValue(jsonResponse({ toolRanking: [], slowestTools: [], statusCounts: {} }))

    const result = await getTools('tenant-1')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/tenant/tools',
      expect.objectContaining({ headers: { 'X-Tenant-Id': 'tenant-1' } }),
    )
    expect(result).toHaveProperty('toolRanking')
  })

  it('getCost passes tenant id via header', async () => {
    mockApiGet.mockReturnValue(jsonResponse({ monthlyCost: '12.50', costByModel: { 'gpt-5': '8.25' } }))

    const result = await getCost('tenant-1')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/tenant/cost',
      expect.objectContaining({ headers: { 'X-Tenant-Id': 'tenant-1' } }),
    )
    expect(result).toHaveProperty('monthlyCost', '12.50')
  })

  it('getSlo returns SLO data with tenant header', async () => {
    mockApiGet.mockReturnValue(jsonResponse({ tenantId: 'tenant-1', sloAvailability: 0.999, sloLatencyP99Ms: 850, currentAvailability: 0.9995, latencyP99Ms: 720, errorBudgetRemaining: 0.8 }))

    const result = await getSlo('tenant-1')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/tenant/slo',
      expect.objectContaining({ headers: { 'X-Tenant-Id': 'tenant-1' } }),
    )
    expect(result).toHaveProperty('currentAvailability', 0.9995)
  })

  it('getTenantAlerts returns array of alerts with tenant header', async () => {
    mockApiGet.mockReturnValue(jsonResponse([{ id: 'alert-1', severity: 'warn' }]))

    const result = await getTenantAlerts('tenant-1')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/tenant/alerts',
      expect.objectContaining({ headers: { 'X-Tenant-Id': 'tenant-1' } }),
    )
    expect(Array.isArray(result)).toBe(true)
  })

  it('getQuota returns quota response with tenant header', async () => {
    const mockQuota = { tenantId: 'tenant-1', quota: { maxRequestsPerMonth: 1000 }, usage: { requests: 250 }, requestUsagePercent: 25, tokenUsagePercent: 10 }
    mockApiGet.mockReturnValue(jsonResponse(mockQuota))

    const result = await getQuota('tenant-1')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/tenant/quota',
      expect.objectContaining({ headers: { 'X-Tenant-Id': 'tenant-1' } }),
    )
    expect(result).toHaveProperty('requestUsagePercent', 25)
  })

  it('exportExecutionsCsv returns CSV string with tenant header', async () => {
    mockApiGet.mockReturnValue(textResponse('id,status,duration\nexec-1,success,250'))

    const result = await exportExecutionsCsv('tenant-1')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/tenant/export/executions',
      expect.objectContaining({ headers: { 'X-Tenant-Id': 'tenant-1' } }),
    )
    expect(typeof result).toBe('string')
    expect(result).toContain('exec-1')
  })

  it('exportToolsCsv returns CSV string with tenant header', async () => {
    mockApiGet.mockReturnValue(textResponse('tool,count\nsearch,42'))

    const result = await exportToolsCsv('tenant-1')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/tenant/export/tools',
      expect.objectContaining({ headers: { 'X-Tenant-Id': 'tenant-1' } }),
    )
    expect(result).toContain('search')
  })

  it('exportExecutionsCsv passes range params as searchParams', async () => {
    mockApiGet.mockReturnValue(textResponse(''))

    await exportExecutionsCsv('tenant-1', { fromMs: 1700000000000, toMs: 1700100000000 })

    const callArg = mockApiGet.mock.calls[0][1]
    expect(callArg.searchParams.fromMs).toBe('1700000000000')
  })
})

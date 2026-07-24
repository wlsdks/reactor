import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  getPlatformHealth,
  listTenants,
  getTenant,
  createTenant,
  suspendTenant,
  activateTenant,
  listPricing,
  upsertPricing,
  listAlertRules,
  saveAlertRule,
  deleteAlertRule,
  listActiveAlerts,
  resolveAlert,
  evaluateAlerts,
  invalidateResponseCache,
  getUserByEmail,
  updateUserRole,
} from '../api'

const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
const mockApiDelete = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: (...args: unknown[]) => mockApiPost(...args),
    put: vi.fn(),
    delete: (...args: unknown[]) => mockApiDelete(...args),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

const mockTenant = {
  id: 'tenant-1',
  name: 'Acme Corp',
  status: 'active',
  plan: 'enterprise',
  createdAt: '2026-01-01T00:00:00Z',
}

const mockAlertRule = {
  id: 'alert-rule-1',
  name: 'High error rate',
  condition: 'error_rate > 0.1',
  severity: 'critical',
  enabled: true,
}

describe('platform-admin api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('getPlatformHealth returns health dashboard', async () => {
    const mockHealth = { pipelineBufferUsage: 2, activeAlerts: 1, cacheExactHits: 4 }
    mockApiGet.mockReturnValue(jsonResponse(mockHealth))

    const result = await getPlatformHealth()

    expect(mockApiGet).toHaveBeenCalledWith('admin/platform/health')
    expect(result).toEqual({
      pipelineBufferUsage: 2,
      pipelineDropRate: 0,
      pipelineWriteLatencyMs: 0,
      pipelineMetricsAvailable: false,
      responseCacheEnabled: false,
      activeAlerts: 1,
      cacheExactHits: 4,
      cacheSemanticHits: 0,
      cacheMisses: 0,
    })
  })

  it('listTenants returns array of tenants', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockTenant]))

    const result = await listTenants()

    expect(mockApiGet).toHaveBeenCalledWith('admin/platform/tenants', { searchParams: { limit: 200 } })
    expect(Array.isArray(result)).toBe(true)
    expect(result[0].id).toBe('tenant-1')
  })

  it('getTenant returns single tenant by id', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockTenant))

    const result = await getTenant('tenant-1')

    expect(mockApiGet).toHaveBeenCalledWith('admin/platform/tenants/tenant-1')
    expect(result.name).toBe('Acme Corp')
  })

  it('getTenant URL-encodes tenant id', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockTenant))

    await getTenant('tenant/special')

    expect(mockApiGet).toHaveBeenCalledWith('admin/platform/tenants/tenant%2Fspecial')
  })

  it('createTenant sends POST and returns created tenant', async () => {
    mockApiPost.mockReturnValue(jsonResponse(mockTenant))

    const result = await createTenant({ name: 'Acme Corp', plan: 'enterprise' })

    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/platform/tenants',
      expect.objectContaining({ json: { name: 'Acme Corp', plan: 'enterprise' } }),
    )
    expect(result.id).toBe('tenant-1')
  })

  it('suspendTenant sends POST to suspend endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ ...mockTenant, status: 'suspended' }))

    const result = await suspendTenant('tenant-1')

    expect(mockApiPost).toHaveBeenCalledWith('admin/platform/tenants/tenant-1/suspend')
    expect(result.status).toBe('suspended')
  })

  it('activateTenant sends POST to activate endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ ...mockTenant, status: 'active' }))

    const result = await activateTenant('tenant-1')

    expect(mockApiPost).toHaveBeenCalledWith('admin/platform/tenants/tenant-1/activate')
    expect(result.status).toBe('active')
  })

  it('listPricing returns pricing array', async () => {
    const mockPricing = [{ id: 'price-1', provider: 'openai', model: 'gpt-4', promptPricePer1m: '30', completionPricePer1m: '60', cachedInputPricePer1m: '0', reasoningPricePer1m: '0', batchPromptPricePer1m: '0', batchCompletionPricePer1m: '0', effectiveFrom: '2026-01-01T00:00:00Z', effectiveTo: null }]
    mockApiGet.mockReturnValue(jsonResponse(mockPricing))

    const result = await listPricing()

    expect(mockApiGet).toHaveBeenCalledWith('admin/platform/pricing')
    expect(Array.isArray(result)).toBe(true)
  })

  it('upsertPricing sends POST and returns pricing entry', async () => {
    const request = { id: 'price-1', provider: 'openai', model: 'gpt-4', promptPricePer1m: 30, completionPricePer1m: 60, cachedInputPricePer1m: 0, reasoningPricePer1m: 0, batchPromptPricePer1m: 0, batchCompletionPricePer1m: 0, effectiveFrom: '2026-01-01T00:00:00Z', effectiveTo: null }
    const response = { ...request, promptPricePer1m: '30', completionPricePer1m: '60', cachedInputPricePer1m: '0', reasoningPricePer1m: '0', batchPromptPricePer1m: '0', batchCompletionPricePer1m: '0' }
    mockApiPost.mockReturnValue(jsonResponse(response))

    const result = await upsertPricing(request)

    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/platform/pricing',
      expect.objectContaining({ json: request }),
    )
    expect(result.model).toBe('gpt-4')
  })

  it('listAlertRules returns rules array', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockAlertRule]))

    const result = await listAlertRules()

    expect(mockApiGet).toHaveBeenCalledWith('admin/platform/alerts/rules')
    expect(result[0].id).toBe('alert-rule-1')
  })

  it('saveAlertRule sends POST and returns saved rule', async () => {
    mockApiPost.mockReturnValue(jsonResponse(mockAlertRule))

    const result = await saveAlertRule(mockAlertRule)

    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/platform/alerts/rules',
      expect.objectContaining({ json: mockAlertRule }),
    )
    expect(result.name).toBe('High error rate')
  })

  it('deleteAlertRule sends DELETE without error', async () => {
    mockApiDelete.mockResolvedValue({})

    await expect(deleteAlertRule('alert-rule-1')).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith('admin/platform/alerts/rules/alert-rule-1')
  })

  it('listActiveAlerts returns active alerts array', async () => {
    const mockAlerts = [{ id: 'alert-1', ruleId: 'alert-rule-1', firedAt: '2026-03-01T00:00:00Z' }]
    mockApiGet.mockReturnValue(jsonResponse(mockAlerts))

    const result = await listActiveAlerts()

    expect(mockApiGet).toHaveBeenCalledWith('admin/platform/alerts')
    expect(Array.isArray(result)).toBe(true)
  })

  it('resolveAlert sends POST to resolve endpoint', async () => {
    mockApiPost.mockReturnValue(jsonResponse(null))

    await expect(resolveAlert('alert-1')).resolves.not.toThrow()

    expect(mockApiPost).toHaveBeenCalledWith('admin/platform/alerts/alert-1/resolve')
  })

  it('evaluateAlerts sends POST and returns status', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ status: 'ok' }))

    const result = await evaluateAlerts()

    expect(mockApiPost).toHaveBeenCalledWith('admin/platform/alerts/evaluate')
    expect(result).toHaveProperty('status', 'ok')
  })

  it('invalidateResponseCache sends POST and returns result', async () => {
    mockApiPost.mockReturnValue(jsonResponse({ invalidated: 42 }))

    const result = await invalidateResponseCache()

    expect(mockApiPost).toHaveBeenCalledWith('admin/platform/cache/invalidate')
    expect(result).toHaveProperty('invalidated', 42)
  })

  it('getUserByEmail sends GET with email searchParam', async () => {
    const mockUser = { id: 'user-1', email: 'admin@example.com', role: 'ADMIN' }
    mockApiGet.mockReturnValue(jsonResponse(mockUser))

    const result = await getUserByEmail('admin@example.com')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/platform/users/by-email',
      expect.objectContaining({ searchParams: { email: 'admin@example.com' } }),
    )
    expect(result).toHaveProperty('role', 'ADMIN')
  })

  it('updateUserRole sends POST with role and returns updated user', async () => {
    const mockUser = { id: 'user-1', email: 'admin@example.com', role: 'ADMIN_MANAGER' }
    mockApiPost.mockReturnValue(jsonResponse(mockUser))

    const result = await updateUserRole('user-1', 'ADMIN_MANAGER')

    expect(mockApiPost).toHaveBeenCalledWith(
      'admin/platform/users/user-1/role',
      expect.objectContaining({ json: { role: 'ADMIN_MANAGER' } }),
    )
    expect(result.role).toBe('ADMIN_MANAGER')
  })
})

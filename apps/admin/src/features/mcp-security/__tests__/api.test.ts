import { describe, it, expect, vi, afterEach } from 'vitest'
import { getMcpSecurityPolicy, updateMcpSecurityPolicy, deleteMcpSecurityPolicy } from '../api'

const mockApiGet = vi.fn()
const mockApiPut = vi.fn()
const mockApiDelete = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: vi.fn(),
    put: (...args: unknown[]) => mockApiPut(...args),
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

const baseRuleSet = {
  allowedServerNames: ['  payments ', 'orders', ' auth '],
  allowToolCategories: ['read', 'write'],
}

const mockPolicyState = {
  effective: baseRuleSet,
  stored: baseRuleSet,
  configDefault: baseRuleSet,
}

describe('mcp-security api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('getMcpSecurityPolicy returns normalized policy state', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockPolicyState))

    const result = await getMcpSecurityPolicy()

    expect(mockApiGet).toHaveBeenCalledWith('mcp/security')
    // normalizeRuleSet trims and sorts allowedServerNames
    expect(result.effective.allowedServerNames).toEqual(['auth', 'orders', 'payments'])
    expect(result.stored?.allowedServerNames).toEqual(['auth', 'orders', 'payments'])
    expect(result.configDefault.allowedServerNames).toEqual(['auth', 'orders', 'payments'])
  })

  it('getMcpSecurityPolicy handles null stored policy', async () => {
    const policyWithNullStored = { ...mockPolicyState, stored: null }
    mockApiGet.mockReturnValue(jsonResponse(policyWithNullStored))

    const result = await getMcpSecurityPolicy()

    expect(result.stored).toBeNull()
  })

  it('normalizeRuleSet filters out empty server names', async () => {
    const policyWithEmptyNames = {
      ...mockPolicyState,
      effective: {
        ...baseRuleSet,
        allowedServerNames: ['payments', '', '  '],
      },
    }
    mockApiGet.mockReturnValue(jsonResponse(policyWithEmptyNames))

    const result = await getMcpSecurityPolicy()

    expect(result.effective.allowedServerNames).toEqual(['payments'])
  })

  it('updateMcpSecurityPolicy sends PUT and returns normalized rule set', async () => {
    const mockResponse = {
      allowedServerNames: [' tool-a ', 'tool-b'],
      allowToolCategories: ['read'],
    }
    mockApiPut.mockReturnValue(jsonResponse(mockResponse))

    const result = await updateMcpSecurityPolicy({
      allowedServerNames: ['tool-a', 'tool-b'],
    })

    expect(mockApiPut).toHaveBeenCalledWith(
      'mcp/security',
      expect.objectContaining({ json: { allowedServerNames: ['tool-a', 'tool-b'] } }),
    )
    expect(result.allowedServerNames).toEqual(['tool-a', 'tool-b'])
  })

  it('deleteMcpSecurityPolicy sends DELETE without error', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))

    await expect(deleteMcpSecurityPolicy()).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith('mcp/security')
  })
})

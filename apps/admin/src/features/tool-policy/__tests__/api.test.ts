import { describe, it, expect, vi, afterEach } from 'vitest'
import { getPolicy, updatePolicy, deletePolicy } from '../api'

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

const mockRuleSet = {
  allowedTools: ['search', 'create_issue'],
  deniedTools: ['delete_repo'],
  requireApproval: ['deploy'],
}

const mockPolicyState = {
  effective: mockRuleSet,
  stored: mockRuleSet,
  configDefault: mockRuleSet,
}

describe('tool-policy api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('getPolicy returns full policy state', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockPolicyState))

    const result = await getPolicy()

    expect(mockApiGet).toHaveBeenCalledWith('tool-policy')
    expect(result).toHaveProperty('effective')
    expect(result).toHaveProperty('stored')
    expect(result).toHaveProperty('configDefault')
    expect(result.effective.allowedTools).toContain('search')
  })

  it('updatePolicy sends PUT and returns updated rule set', async () => {
    mockApiPut.mockReturnValue(jsonResponse(mockRuleSet))

    const result = await updatePolicy({ allowedTools: ['search'] })

    expect(mockApiPut).toHaveBeenCalledWith(
      'tool-policy',
      expect.objectContaining({ json: { allowedTools: ['search'] } }),
    )
    expect(result).toHaveProperty('allowedTools')
  })

  it('deletePolicy sends DELETE without error', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))

    await expect(deletePolicy()).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith('tool-policy')
  })
})

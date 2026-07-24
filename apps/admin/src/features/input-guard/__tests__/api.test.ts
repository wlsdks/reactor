import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getInputGuardRule } from '../api'

const mockApiGet = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

beforeEach(() => {
  mockApiGet.mockReset()
})

describe('getInputGuardRule', () => {
  it('GETs admin/input-guard/rules/{id}', async () => {
    const rule = {
      id: 'rule-1',
      name: 'Test',
      pattern: 'foo',
      patternType: 'regex',
      action: 'block',
      priority: 1,
      category: 'safety',
      description: 'd',
      enabled: true,
      createdAt: '2026-04-25T00:00:00Z',
      updatedAt: '2026-04-25T00:00:00Z',
    }
    mockApiGet.mockReturnValueOnce(jsonResponse(rule))
    await expect(getInputGuardRule('rule-1')).resolves.toEqual(rule)
    expect(mockApiGet).toHaveBeenCalledWith('admin/input-guard/rules/rule-1')
  })

  it('encodes id with special characters', async () => {
    mockApiGet.mockReturnValueOnce(jsonResponse({}))
    await getInputGuardRule('a/b c')
    expect(mockApiGet).toHaveBeenCalledWith('admin/input-guard/rules/a%2Fb%20c')
  })
})

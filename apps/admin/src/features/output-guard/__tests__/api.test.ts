import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  listRules,
  listRuleAudits,
  createRule,
  updateRule,
  deleteRule,
  simulateGuard,
} from '../api'

const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
const mockApiPut = vi.fn()
const mockApiDelete = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    post: (...args: unknown[]) => mockApiPost(...args),
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

const mockRule = {
  id: 'rule-1',
  name: 'block-pii',
  pattern: '\\b\\d{3}-\\d{2}-\\d{4}\\b',
  action: 'block',
  enabled: true,
}

describe('output-guard api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('listRules returns array of rules', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockRule]))

    const result = await listRules()

    expect(mockApiGet).toHaveBeenCalledWith('output-guard/rules', { searchParams: { limit: 200 } })
    expect(Array.isArray(result)).toBe(true)
    expect(result[0].id).toBe('rule-1')
  })

  it('listRuleAudits returns audit log with default limit', async () => {
    const mockAudit = [{ id: 'audit-1', ruleId: 'rule-1', action: 'triggered' }]
    mockApiGet.mockReturnValue(jsonResponse(mockAudit))

    const result = await listRuleAudits()

    expect(mockApiGet).toHaveBeenCalledWith(
      'output-guard/rules/audits',
      expect.objectContaining({ searchParams: { limit: '100' } }),
    )
    expect(Array.isArray(result)).toBe(true)
  })

  it('listRuleAudits passes custom limit', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await listRuleAudits(50)

    expect(mockApiGet).toHaveBeenCalledWith(
      'output-guard/rules/audits',
      expect.objectContaining({ searchParams: { limit: '50' } }),
    )
  })

  it('createRule sends POST and returns created rule', async () => {
    mockApiPost.mockReturnValue(jsonResponse(mockRule))

    const result = await createRule({
      name: 'block-pii',
      pattern: '\\b\\d{3}-\\d{2}-\\d{4}\\b',
      action: 'block',
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'output-guard/rules',
      expect.objectContaining({ json: expect.objectContaining({ name: 'block-pii' }) }),
    )
    expect(result.id).toBe('rule-1')
  })

  it('updateRule sends PUT with correct id and returns updated rule', async () => {
    const updated = { ...mockRule, enabled: false }
    mockApiPut.mockReturnValue(jsonResponse(updated))

    const result = await updateRule('rule-1', { enabled: false })

    expect(mockApiPut).toHaveBeenCalledWith(
      'output-guard/rules/rule-1',
      expect.objectContaining({ json: { enabled: false } }),
    )
    expect(result.enabled).toBe(false)
  })

  it('deleteRule sends DELETE without error', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))

    await expect(deleteRule('rule-1')).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith('output-guard/rules/rule-1')
  })

  it('simulateGuard sends POST and returns simulation response', async () => {
    const mockSimResponse = {
      blocked: true,
      matchedRuleId: 'rule-1',
      output: '[REDACTED]',
    }
    mockApiPost.mockReturnValue(jsonResponse(mockSimResponse))

    const result = await simulateGuard({ text: 'My SSN is 123-45-6789' })

    expect(mockApiPost).toHaveBeenCalledWith(
      'output-guard/rules/simulate',
      expect.objectContaining({ json: { text: 'My SSN is 123-45-6789' } }),
    )
    expect(result.blocked).toBe(true)
    expect(result.matchedRuleId).toBe('rule-1')
  })
})

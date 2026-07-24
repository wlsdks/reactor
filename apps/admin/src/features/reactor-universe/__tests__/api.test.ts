import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockApiGet = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
  },
}))

import { getAgentSpecSystemPrompt, listAgentSpecs } from '../api'

beforeEach(() => {
  mockApiGet.mockReset()
})

describe('getAgentSpecSystemPrompt', () => {
  it('GETs admin/agent-specs/{id}/system-prompt and returns the response', async () => {
    mockApiGet.mockReturnValueOnce({
      json: () => Promise.resolve({ systemPrompt: 'You are an agent.' }),
    })
    const result = await getAgentSpecSystemPrompt('spec-123')
    expect(mockApiGet).toHaveBeenCalledWith('admin/agent-specs/spec-123/system-prompt')
    expect(result).toEqual({ systemPrompt: 'You are an agent.' })
  })

  it('encodes the id', async () => {
    mockApiGet.mockReturnValueOnce({
      json: () => Promise.resolve({ systemPrompt: '' }),
    })
    await getAgentSpecSystemPrompt('spec/with slash')
    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/agent-specs/spec%2Fwith%20slash/system-prompt',
    )
  })
})

describe('listAgentSpecs', () => {
  it('uses the current list endpoint and validates the full backend response shape', async () => {
    const agentSpec = {
      id: 'spec-123',
      name: 'Support',
      description: 'desc',
      toolNames: ['rag_search'],
      keywords: ['help'],
      systemPromptPreview: 'Be helpful.',
      hasSystemPrompt: true,
      mode: 'REACT',
      independentExecution: true,
      enabled: true,
      createdAt: '2026-04-01T00:00:00Z',
      updatedAt: '2026-04-01T00:00:00Z',
    }
    mockApiGet.mockReturnValueOnce({ json: () => Promise.resolve([agentSpec]) })

    await expect(listAgentSpecs()).resolves.toEqual([agentSpec])
    expect(mockApiGet).toHaveBeenCalledWith('admin/agent-specs')
  })

  it('fails closed when the backend omits protected list-contract fields', async () => {
    mockApiGet.mockReturnValueOnce({
      json: () => Promise.resolve([{ id: 'spec-123', name: 'Incomplete' }]),
    })

    await expect(listAgentSpecs()).rejects.toThrow('AI 역할 목록을 확인할 수 없어요')
  })
})

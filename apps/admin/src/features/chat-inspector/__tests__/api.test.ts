import { describe, it, expect, vi, afterEach } from 'vitest'
import { CHAT_REQUEST_TIMEOUT_MS, sendChat } from '../api'

const mockApiPost = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: vi.fn(),
    post: (...args: unknown[]) => mockApiPost(...args),
    put: vi.fn(),
    delete: vi.fn(),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
  fetchWithAuth: vi.fn(),
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

describe('chat-inspector api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('sendChat normalizes standard response (content field)', async () => {
    const mockResponse = {
      content: 'Hello!',
      success: true,
      model: 'gpt-4',
      toolsUsed: ['web_search'],
      durationMs: 500,
    }
    mockApiPost.mockReturnValue(jsonResponse(mockResponse))

    const result = await sendChat({ message: 'Hi', model: 'gpt-4' })

    expect(mockApiPost).toHaveBeenCalledWith(
      'chat',
      expect.objectContaining({
        json: { message: 'Hi', model: 'gpt-4' },
        timeout: CHAT_REQUEST_TIMEOUT_MS,
      }),
    )
    expect(result.content).toBe('Hello!')
    expect(result.success).toBe(true)
    expect(result.toolsUsed).toEqual(['web_search'])
    expect(result.durationMs).toBe(500)
  })

  it('sendChat normalizes mock response (response field, flat tokens)', async () => {
    const mockResponse = {
      response: 'Mock answer',
      model: 'claude-sonnet-4-20250514',
      toolCalls: [],
      durationMs: 1500,
      inputTokens: 150,
      outputTokens: 85,
    }
    mockApiPost.mockReturnValue(jsonResponse(mockResponse))

    const result = await sendChat({ message: 'test' })

    expect(result.content).toBe('Mock answer')
    expect(result.success).toBe(true)
    expect(result.toolsUsed).toEqual([])
    expect(result.durationMs).toBe(1500)
    expect(result.metadata?.tokenUsage?.promptTokens).toBe(150)
    expect(result.metadata?.tokenUsage?.completionTokens).toBe(85)
    expect(result.metadata?.tokenUsage?.totalTokens).toBe(235)
  })

  it('sendChat normalizes error response', async () => {
    const mockResponse = {
      errorCode: 'RATE_LIMITED',
      errorMessage: 'Too many requests',
      success: false,
    }
    mockApiPost.mockReturnValue(jsonResponse(mockResponse))

    const result = await sendChat({ message: 'test' })

    expect(result.success).toBe(false)
    expect(result.errorCode).toBe('RATE_LIMITED')
    expect(result.errorMessage).toBe('Too many requests')
    expect(result.content).toBeNull()
  })
})

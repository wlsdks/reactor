import { describe, it, expect, vi, afterEach } from 'vitest'
import { listSlackBots, getSlackBot, createSlackBot, updateSlackBot, deleteSlackBot } from '../api'

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

const mockBot = {
  id: 'bot-1',
  name: 'Test Bot',
  botToken: null,
  appToken: null,
  signingSecret: null,
  workspace: 'test-workspace',
  description: 'A test bot',
  isActive: true,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
}

describe('slack-bots api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('listSlackBots calls GET with limit param', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockBot]))

    const result = await listSlackBots()

    expect(mockApiGet).toHaveBeenCalledWith('admin/slack-bots', { searchParams: { limit: 200 } })
    expect(result).toEqual([mockBot])
  })

  it('getSlackBot calls GET with id', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockBot))

    const result = await getSlackBot('bot-1')

    expect(mockApiGet).toHaveBeenCalledWith('admin/slack-bots/bot-1')
    expect(result).toEqual(mockBot)
  })

  it('createSlackBot calls POST with json payload', async () => {
    mockApiPost.mockReturnValue(jsonResponse(mockBot))

    const request = {
      name: 'Test Bot',
      botToken: 'xoxb-token',
      appToken: 'xapp-token',
      signingSecret: 'secret123',
      workspace: 'test-workspace',
      description: 'A test bot',
    }

    const result = await createSlackBot(request)

    expect(mockApiPost).toHaveBeenCalledWith('admin/slack-bots', { json: request })
    expect(result).toEqual(mockBot)
  })

  it('updateSlackBot calls PUT with id and json payload', async () => {
    mockApiPut.mockReturnValue(jsonResponse({ ...mockBot, name: 'Updated Bot' }))

    const request = { name: 'Updated Bot' }
    const result = await updateSlackBot('bot-1', request)

    expect(mockApiPut).toHaveBeenCalledWith('admin/slack-bots/bot-1', { json: request })
    expect(result.name).toBe('Updated Bot')
  })

  it('deleteSlackBot calls DELETE and returns undefined', async () => {
    mockApiDelete.mockReturnValue(Promise.resolve({ json: () => Promise.resolve(null) }))

    const result = await deleteSlackBot('bot-1')

    expect(mockApiDelete).toHaveBeenCalledWith('admin/slack-bots/bot-1')
    expect(result).toBeUndefined()
  })
})

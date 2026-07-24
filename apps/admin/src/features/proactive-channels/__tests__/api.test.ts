import { describe, it, expect, vi, afterEach } from 'vitest'
import { listProactiveChannels, addProactiveChannel, removeProactiveChannel } from '../api'

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

const mockChannel = {
  channelId: 'C123ABC',
  channelName: '#general',
  workspaceId: 'T001',
  addedAt: '2026-03-01T00:00:00Z',
}

describe('proactive-channels api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('listProactiveChannels returns array of channels', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockChannel]))

    const result = await listProactiveChannels()

    expect(mockApiGet).toHaveBeenCalledWith('proactive-channels', { searchParams: { limit: 200 } })
    expect(Array.isArray(result)).toBe(true)
    expect(result[0].channelId).toBe('C123ABC')
  })

  it('addProactiveChannel sends POST and returns created channel', async () => {
    mockApiPost.mockReturnValue(jsonResponse(mockChannel))

    const result = await addProactiveChannel({
      channelId: 'C123ABC',
      channelName: '#general',
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'proactive-channels',
      expect.objectContaining({
        json: { channelId: 'C123ABC', channelName: '#general' },
      }),
    )
    expect(result.channelId).toBe('C123ABC')
  })

  it('removeProactiveChannel sends DELETE without error', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))

    await expect(removeProactiveChannel('C123ABC')).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith('proactive-channels/C123ABC')
  })

  it('removeProactiveChannel URL-encodes channel id with special characters', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))

    await removeProactiveChannel('channel/with/slashes')

    expect(mockApiDelete).toHaveBeenCalledWith(
      'proactive-channels/channel%2Fwith%2Fslashes',
    )
  })
})

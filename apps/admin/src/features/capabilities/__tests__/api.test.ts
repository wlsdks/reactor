import { describe, expect, it, vi } from 'vitest'
import { getCapabilityManifest } from '../api'

// Mock the shared api client to decouple from URL resolution in test environments
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

describe('capability manifest api', () => {
  it('parses manifest path list into a set', async () => {
    mockApiGet.mockReturnValue({
      json: () => Promise.resolve({
        generatedAt: 123,
        source: 'request-mappings',
        paths: ['/api/ops/dashboard', '/api/mcp/servers'],
      }),
    })

    const result = await getCapabilityManifest()

    expect(result).not.toBeNull()
    expect([...result ?? []]).toEqual(['/api/ops/dashboard', '/api/mcp/servers'])
  })

  it('returns null when manifest endpoint is unavailable', async () => {
    mockApiGet.mockReturnValue({
      json: () => Promise.resolve({}),
    })

    const result = await getCapabilityManifest()

    expect(result).toBeNull()
  })
})

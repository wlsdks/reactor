import { describe, it, expect, vi, afterEach } from 'vitest'
import { getUserMemory, updateUserFacts, updateUserPreferences, deleteUserMemory } from '../api'

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

function voidResponse() {
  return { then: (fn: (v: unknown) => unknown) => Promise.resolve(fn(undefined)) }
}

const mockMemory = {
  userId: 'user-123',
  facts: { name: 'Alice', role: 'Engineer' },
  preferences: { language: 'en', theme: 'dark' },
}

describe('user-memory api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('getUserMemory fetches memory for a user', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockMemory))

    const result = await getUserMemory('user-123')

    expect(mockApiGet).toHaveBeenCalledWith('user-memory/user-123')
    expect(result).toHaveProperty('userId', 'user-123')
    expect(result.facts).toEqual({ name: 'Alice', role: 'Engineer' })
    expect(result.preferences).toEqual({ language: 'en', theme: 'dark' })
  })

  it('updateUserFacts sends PUT with facts payload', async () => {
    mockApiPut.mockReturnValue(voidResponse())

    const facts = { name: 'Bob' }
    await updateUserFacts('user-123', facts)

    expect(mockApiPut).toHaveBeenCalledWith(
      'user-memory/user-123/facts',
      expect.objectContaining({ json: { name: 'Bob' } }),
    )
  })

  it('updateUserPreferences sends PUT with preferences payload', async () => {
    mockApiPut.mockReturnValue(voidResponse())

    const prefs = { theme: 'light' }
    await updateUserPreferences('user-123', prefs)

    expect(mockApiPut).toHaveBeenCalledWith(
      'user-memory/user-123/preferences',
      expect.objectContaining({ json: { theme: 'light' } }),
    )
  })

  it('deleteUserMemory sends DELETE without error', async () => {
    mockApiDelete.mockReturnValue(voidResponse())

    await expect(deleteUserMemory('user-123')).resolves.toBeUndefined()

    expect(mockApiDelete).toHaveBeenCalledWith('user-memory/user-123')
  })
})

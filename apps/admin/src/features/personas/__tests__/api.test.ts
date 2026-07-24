import { describe, it, expect, vi, afterEach } from 'vitest'
import { listPersonas, getPersona, createPersona, updatePersona, deletePersona } from '../api'

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
  fetchWithAuth: vi.fn(),
}))

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

const mockPersona = {
  id: 'persona-1',
  name: 'Jarvis',
  description: 'Helpful assistant',
  systemPrompt: 'You are a helpful assistant.',
  model: 'gpt-4',
  createdAt: '2026-03-01T00:00:00Z',
}

describe('personas api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('listPersonas returns array of personas', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockPersona]))

    const result = await listPersonas()

    expect(mockApiGet).toHaveBeenCalledWith('personas', { searchParams: { limit: 200 } })
    expect(Array.isArray(result)).toBe(true)
    expect(result[0].id).toBe('persona-1')
    expect(result[0].name).toBe('Jarvis')
  })

  it('getPersona returns single persona by id', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockPersona))

    const result = await getPersona('persona-1')

    expect(mockApiGet).toHaveBeenCalledWith('personas/persona-1')
    expect(result.id).toBe('persona-1')
    expect(result.model).toBe('gpt-4')
  })

  it('createPersona sends POST and returns created persona', async () => {
    mockApiPost.mockReturnValue(jsonResponse(mockPersona))

    const result = await createPersona({
      name: 'Jarvis',
      description: 'Helpful assistant',
      systemPrompt: 'You are a helpful assistant.',
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'personas',
      expect.objectContaining({
        json: expect.objectContaining({ name: 'Jarvis' }),
      }),
    )
    expect(result.id).toBe('persona-1')
  })

  it('updatePersona sends PUT and returns updated persona', async () => {
    const updated = { ...mockPersona, name: 'JARVIS v2' }
    mockApiPut.mockReturnValue(jsonResponse(updated))

    const result = await updatePersona('persona-1', { name: 'JARVIS v2' })

    expect(mockApiPut).toHaveBeenCalledWith(
      'personas/persona-1',
      expect.objectContaining({ json: { name: 'JARVIS v2' } }),
    )
    expect(result.name).toBe('JARVIS v2')
  })

  it('deletePersona sends DELETE without error', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))

    await expect(deletePersona('persona-1')).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith('personas/persona-1')
  })
})

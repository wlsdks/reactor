import { describe, it, expect, vi, afterEach } from 'vitest'
import {
  listTemplates,
  getTemplate,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  createVersion,
  activateVersion,
  archiveVersion,
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

const mockTemplate = {
  id: 'tmpl-1',
  name: 'greeting',
  description: 'Greeting template',
  activeVersionId: 'v1',
  createdAt: '2026-03-01T00:00:00Z',
}

const mockVersion = {
  id: 'v1',
  templateId: 'tmpl-1',
  content: 'Hello, {{name}}!',
  status: 'active',
  createdAt: '2026-03-01T00:00:00Z',
}

describe('prompts api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('listTemplates returns array of templates', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockTemplate]))

    const result = await listTemplates()

    expect(mockApiGet).toHaveBeenCalledWith('prompt-templates', { searchParams: { limit: 200 } })
    expect(Array.isArray(result)).toBe(true)
    expect(result[0].id).toBe('tmpl-1')
  })

  it('getTemplate returns template detail by id', async () => {
    const mockDetail = { ...mockTemplate, versions: [mockVersion] }
    mockApiGet.mockReturnValue(jsonResponse(mockDetail))

    const result = await getTemplate('tmpl-1')

    expect(mockApiGet).toHaveBeenCalledWith('prompt-templates/tmpl-1')
    expect(result).toHaveProperty('id', 'tmpl-1')
  })

  it('createTemplate sends POST and returns created template', async () => {
    mockApiPost.mockReturnValue(jsonResponse(mockTemplate))

    const result = await createTemplate({
      name: 'greeting',
      description: 'Greeting template',
    })

    expect(mockApiPost).toHaveBeenCalledWith(
      'prompt-templates',
      expect.objectContaining({ json: { name: 'greeting', description: 'Greeting template' } }),
    )
    expect(result.id).toBe('tmpl-1')
  })

  it('updateTemplate sends PUT and returns updated template', async () => {
    const updated = { ...mockTemplate, description: 'Updated greeting' }
    mockApiPut.mockReturnValue(jsonResponse(updated))

    const result = await updateTemplate('tmpl-1', { description: 'Updated greeting' })

    expect(mockApiPut).toHaveBeenCalledWith(
      'prompt-templates/tmpl-1',
      expect.objectContaining({ json: { description: 'Updated greeting' } }),
    )
    expect(result.description).toBe('Updated greeting')
  })

  it('deleteTemplate sends DELETE without error', async () => {
    mockApiDelete.mockReturnValue(jsonResponse(null))

    await expect(deleteTemplate('tmpl-1')).resolves.not.toThrow()

    expect(mockApiDelete).toHaveBeenCalledWith('prompt-templates/tmpl-1')
  })

  it('createVersion sends POST to versions endpoint and returns version', async () => {
    mockApiPost.mockReturnValue(jsonResponse(mockVersion))

    const result = await createVersion('tmpl-1', { content: 'Hello, {{name}}!' })

    expect(mockApiPost).toHaveBeenCalledWith(
      'prompt-templates/tmpl-1/versions',
      expect.objectContaining({ json: { content: 'Hello, {{name}}!' } }),
    )
    expect(result.id).toBe('v1')
    expect(result.templateId).toBe('tmpl-1')
  })

  it('activateVersion sends PUT to activate endpoint and returns version', async () => {
    const activatedVersion = { ...mockVersion, status: 'active' }
    mockApiPut.mockReturnValue(jsonResponse(activatedVersion))

    const result = await activateVersion('tmpl-1', 'v1')

    expect(mockApiPut).toHaveBeenCalledWith('prompt-templates/tmpl-1/versions/v1/activate')
    expect(result.status).toBe('active')
  })

  it('archiveVersion sends PUT to archive endpoint and returns version', async () => {
    const archivedVersion = { ...mockVersion, status: 'archived' }
    mockApiPut.mockReturnValue(jsonResponse(archivedVersion))

    const result = await archiveVersion('tmpl-1', 'v1')

    expect(mockApiPut).toHaveBeenCalledWith('prompt-templates/tmpl-1/versions/v1/archive')
    expect(result.status).toBe('archived')
  })
})

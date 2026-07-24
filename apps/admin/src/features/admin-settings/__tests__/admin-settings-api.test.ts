import { describe, it, expect, vi, afterEach } from 'vitest'
import { listSettings, getSetting, updateSetting, deleteSetting, refreshSettingsCache } from '../api'

const mockApiGet = vi.fn()
const mockApiPut = vi.fn()
const mockApiDelete = vi.fn()
const mockApiPost = vi.fn()

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

function thenResponse() {
  return { then: (cb: (v: unknown) => unknown) => Promise.resolve(cb(undefined)) }
}

const mockSingleSetting = {
  tenantId: 'tenant-1',
  key: 'app.name',
  value: 'MyApp',
  type: 'string',
  category: 'application',
  description: '애플리케이션 이름',
  updatedBy: 'admin-1',
  updatedAt: '2026-01-01T00:00:00Z',
  metadata: {},
}

const mockSettings = [
  mockSingleSetting,
  {
    ...mockSingleSetting,
    key: 'app.debug',
    value: 'true',
    type: 'boolean',
    description: '디버그 모드',
    updatedAt: '2026-01-02T00:00:00Z',
  },
]

describe('admin-settings api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('listSettings calls the unpaginated backend endpoint without unsupported parameters', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockSettings))

    const result = await listSettings()

    expect(mockApiGet).toHaveBeenCalledWith('admin/settings')
    expect(result).toHaveLength(2)
    expect(result[0].key).toBe('app.name')
  })

  it('getSetting calls GET admin/settings/:key', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockSingleSetting))

    const result = await getSetting('app.name')

    expect(mockApiGet).toHaveBeenCalledWith('admin/settings/app.name')
    expect(result.key).toBe('app.name')
    expect(result.value).toBe('MyApp')
  })

  it('getSetting encodes special characters in key', async () => {
    mockApiGet.mockReturnValue(jsonResponse(mockSingleSetting))

    await getSetting('app/special key')

    expect(mockApiGet).toHaveBeenCalledWith('admin/settings/app%2Fspecial%20key')
  })

  it('updateSetting calls PUT with value payload', async () => {
    const updated = { ...mockSingleSetting, value: 'NewApp' }
    mockApiPut.mockReturnValue(jsonResponse(updated))

    const result = await updateSetting('app.name', 'NewApp')

    expect(mockApiPut).toHaveBeenCalledWith(
      'admin/settings/app.name',
      expect.objectContaining({ json: { value: 'NewApp' } }),
    )
    expect(result.value).toBe('NewApp')
  })

  it('deleteSetting calls DELETE and returns void', async () => {
    mockApiDelete.mockReturnValue(thenResponse())

    await expect(deleteSetting('app.name')).resolves.toBeUndefined()

    expect(mockApiDelete).toHaveBeenCalledWith('admin/settings/app.name')
  })

  it('refreshSettingsCache calls POST admin/settings/refresh', async () => {
    mockApiPost.mockReturnValue(thenResponse())

    await expect(refreshSettingsCache()).resolves.toBeUndefined()

    expect(mockApiPost).toHaveBeenCalledWith('admin/settings/refresh')
  })
})

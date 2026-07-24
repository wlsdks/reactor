import { describe, it, expect, vi, afterEach } from 'vitest'
import { listAuditLogs, listAuditPage } from '../api'

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

function jsonResponse(data: unknown) {
  return { json: () => Promise.resolve(data) }
}

const mockEntry = {
  id: 'audit-1',
  category: 'mcp_server',
  action: 'CREATE',
  actor: 'admin@example.com',
  resourceType: 'McpServer',
  resourceId: 'atlassian',
  detail: null,
  createdAt: 1710000000000,
}

describe('audit api', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('listAuditLogs extracts items from paginated response', async () => {
    const paginated = { items: [mockEntry], total: 1, offset: 0, limit: 100 }
    mockApiGet.mockReturnValue(jsonResponse(paginated))

    const result = await listAuditLogs()

    expect(Array.isArray(result)).toBe(true)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe('audit-1')
    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/audits',
      expect.objectContaining({ searchParams: expect.objectContaining({ limit: '100' }) }),
    )
  })

  it('listAuditLogs handles raw array response as fallback', async () => {
    mockApiGet.mockReturnValue(jsonResponse([mockEntry]))

    const result = await listAuditLogs()

    expect(Array.isArray(result)).toBe(true)
    expect(result[0].id).toBe('audit-1')
  })

  it('listAuditLogs passes custom limit', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await listAuditLogs(50)

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/audits',
      expect.objectContaining({ searchParams: expect.objectContaining({ limit: '50' }) }),
    )
  })

  it('listAuditLogs passes category filter', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await listAuditLogs(100, 'auth')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/audits',
      expect.objectContaining({
        searchParams: expect.objectContaining({ category: 'auth' }),
      }),
    )
  })

  it('listAuditLogs passes action filter', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await listAuditLogs(100, undefined, 'login')

    expect(mockApiGet).toHaveBeenCalledWith(
      'admin/audits',
      expect.objectContaining({
        searchParams: expect.objectContaining({ action: 'login' }),
      }),
    )
  })

  it('listAuditLogs omits category and action when not provided', async () => {
    mockApiGet.mockReturnValue(jsonResponse([]))

    await listAuditLogs()

    const callArg = mockApiGet.mock.calls[0][1]
    expect(callArg.searchParams).not.toHaveProperty('category')
    expect(callArg.searchParams).not.toHaveProperty('action')
  })
})
  it('listAuditPage uses the backend pageLimit and offset contract', async () => {
    mockApiGet.mockReturnValue(jsonResponse({ items: [mockEntry], total: 51, offset: 25, limit: 25 }))

    const result = await listAuditPage({ category: 'platform_user', action: 'ROLE_UPDATE', offset: 25, limit: 25 })

    expect(result).toMatchObject({ total: 51, offset: 25, limit: 25 })
    expect(mockApiGet).toHaveBeenCalledWith('admin/audits', {
      searchParams: {
        category: 'platform_user', action: 'ROLE_UPDATE', offset: '25', pageLimit: '25',
      },
    })
  })

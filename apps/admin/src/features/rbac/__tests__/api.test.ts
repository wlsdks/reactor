import { describe, it, expect, vi, afterEach } from 'vitest'
import { listRoles, assignUserRole } from '../api'
import type { RawRole } from '../types'

const mockApiGet = vi.fn()
const mockApiPut = vi.fn()

vi.mock('../../../shared/api/client', () => ({
  api: {
    get: (...args: unknown[]) => mockApiGet(...args),
    put: (...args: unknown[]) => mockApiPut(...args),
  },
  getAuthToken: vi.fn(() => null),
  setAuthToken: vi.fn(),
  removeAuthToken: vi.fn(),
  setOnUnauthorized: vi.fn(),
}))

function jsonResponse<T>(data: T) {
  return { json: () => Promise.resolve(data) }
}

describe('rbac api', () => {
  afterEach(() => {
    mockApiGet.mockReset()
    mockApiPut.mockReset()
  })

  describe('listRoles', () => {
    it('GETs admin/rbac/roles with limit 200', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse<RawRole[]>([]))
      await listRoles()
      expect(mockApiGet).toHaveBeenCalledWith('admin/rbac/roles', { searchParams: { limit: 200 } })
    })

    it('maps RawRole to Role and parses permissions', async () => {
      mockApiGet.mockReturnValueOnce(
        jsonResponse<RawRole[]>([
          {
            role: 'CUSTOM_ROLE',
            scope: 'tenant-scope',
            permissions: ['mcp:read', 'mcp:write', 'audit:read'],
          },
        ]),
      )
      const result = await listRoles()
      expect(result).toEqual([
        {
          id: 'CUSTOM_ROLE',
          name: 'CUSTOM_ROLE',
          description: 'tenant-scope',
          isSystem: false,
          permissions: [
            { id: 'mcp:read', resource: 'mcp', action: 'read' },
            { id: 'mcp:write', resource: 'mcp', action: 'write' },
            { id: 'audit:read', resource: 'audit', action: 'read' },
          ],
          memberCount: 0,
          createdAt: 0,
        },
      ])
    })

    it('marks the 4 system roles as isSystem=true', async () => {
      mockApiGet.mockReturnValueOnce(
        jsonResponse<RawRole[]>([
          { role: 'USER', permissions: [] },
          { role: 'ADMIN', permissions: [] },
          { role: 'ADMIN_MANAGER', permissions: [] },
          { role: 'ADMIN_DEVELOPER', permissions: [] },
        ]),
      )
      const result = await listRoles()
      expect(result.map((r) => r.isSystem)).toEqual([true, true, true, true])
    })

    it('falls back to empty description when scope is undefined', async () => {
      mockApiGet.mockReturnValueOnce(
        jsonResponse<RawRole[]>([{ role: 'X', permissions: [] }]),
      )
      const result = await listRoles()
      expect(result[0].description).toBe('')
    })

    it('fails closed when the server returns a malformed role or permission payload', async () => {
      mockApiGet.mockReturnValueOnce(jsonResponse([
        { role: 'ADMIN', scope: 'FULL', permissions: [{ resource: 'audit', action: 'read' }] },
      ]))

      await expect(listRoles()).rejects.toThrow('역할별 권한 정보를 확인할 수 없습니다.')
    })

    it.each(['audit-read', 'audit:read:extra'])('fails closed when the server returns an invalid permission string (%s)', async (permission) => {
      mockApiGet.mockReturnValueOnce(jsonResponse<RawRole[]>([
        { role: 'ADMIN', scope: 'FULL', permissions: [permission] },
      ]))

      await expect(listRoles()).rejects.toThrow('권한 정보 형식이 올바르지 않습니다.')
    })
  })

  describe('assignUserRole', () => {
    it('PUTs admin/rbac/users/{id}/role with the role in the body', async () => {
      mockApiPut.mockReturnValueOnce(jsonResponse(undefined))
      await assignUserRole('user-1', 'ADMIN')
      expect(mockApiPut).toHaveBeenCalledWith('admin/rbac/users/user-1/role', { json: { role: 'ADMIN' } })
    })

    it('encodes the user id', async () => {
      mockApiPut.mockReturnValueOnce(jsonResponse(undefined))
      await assignUserRole('user/with slash', 'ADMIN_MANAGER')
      expect(mockApiPut).toHaveBeenCalledWith('admin/rbac/users/user%2Fwith%20slash/role', {
        json: { role: 'ADMIN_MANAGER' },
      })
    })
  })
})

import { api } from '../../shared/api/client'
import type { Role, RawRole, Permission } from './types'

const SYSTEM_ROLES = new Set(['USER', 'ADMIN', 'ADMIN_MANAGER', 'ADMIN_DEVELOPER'])

function parsePermission(perm: string): Permission {
  const parts = perm.split(':')
  const [resource, action] = parts
  if (parts.length !== 2 || !resource?.trim() || !action?.trim()) {
    throw new Error('권한 정보 형식이 올바르지 않습니다.')
  }
  return { id: perm, resource, action }
}

function isRawRole(value: unknown): value is RawRole {
  if (typeof value !== 'object' || value === null) return false
  const raw = value as Record<string, unknown>
  return typeof raw.role === 'string'
    && (raw.scope === undefined || raw.scope === null || typeof raw.scope === 'string')
    && Array.isArray(raw.permissions)
    && raw.permissions.every((permission) => typeof permission === 'string')
}

function mapRawRole(raw: RawRole): Role {
  return {
    id: raw.role,
    name: raw.role,
    description: raw.scope ?? '',
    isSystem: SYSTEM_ROLES.has(raw.role),
    permissions: raw.permissions.map(parsePermission),
    memberCount: 0,
    createdAt: 0,
  }
}

export const listRoles = async (): Promise<Role[]> => {
  const raw = await api.get('admin/rbac/roles', { searchParams: { limit: 200 } }).json<unknown>()
  if (!Array.isArray(raw) || !raw.every(isRawRole)) {
    throw new Error('역할별 권한 정보를 확인할 수 없습니다.')
  }
  return raw.map(mapRawRole)
}

export const assignUserRole = (userId: string, role: string): Promise<void> =>
  api.put(`admin/rbac/users/${encodeURIComponent(userId)}/role`, { json: { role } }).json()

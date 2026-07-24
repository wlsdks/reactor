import type { User, UserRole } from '../../features/auth/types'

/** Decoded JWT payload from reactor-iam access tokens */
interface JwtClaims {
  sub: string
  roles: string[]
  permissions: string[]
  iss: string
  exp: number
  iat: number
  jti: string
}

interface JwtPayload {
  exp?: number
  [key: string]: unknown
}

export function parseJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const payload = parts[1]
    const padded = payload.replace(/-/g, '+').replace(/_/g, '/')
    const decoded = atob(padded)
    return JSON.parse(decoded) as JwtPayload
  } catch {
    return null
  }
}

export function getTokenExpiry(token: string): number | null {
  const payload = parseJwtPayload(token)
  return payload?.exp ?? null
}

export function parseJwtClaims(token: string): JwtClaims | null {
  return parseJwtPayload(token) as JwtClaims | null
}

/**
 * Map backend role names to frontend UserRole.
 * Backend uses ROLE_ADMIN / ROLE_USER; frontend expects ADMIN / USER etc.
 */
function mapRole(backendRoles: string[]): UserRole {
  if (backendRoles.includes('ROLE_ADMIN')) return 'ADMIN'
  return 'USER'
}

/**
 * Build a User object from JWT claims.
 * Supports both reactor tokens (single role string, has email)
 * and reactor-iam tokens (roles array, no email).
 */
export function userFromToken(token: string): User | null {
  const payload = parseJwtPayload(token)
  if (!payload?.sub) return null

  // reactor JWT: { sub, email, role (string), tenantId }
  if (typeof payload.role === 'string') {
    return {
      id: payload.sub as string,
      email: (payload.email as string) || '',
      name: (payload.name as string) || '',
      role: payload.role as UserRole,
    }
  }

  // reactor-iam JWT: { sub, roles (string[]), permissions }
  if (Array.isArray(payload.roles)) {
    return {
      id: payload.sub as string,
      email: '',
      name: '',
      role: mapRole(payload.roles as string[]),
    }
  }

  return null
}

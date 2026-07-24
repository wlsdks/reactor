/**
 * Build a mock JWT token that parseJwtPayload can decode.
 * The signature is fake -- only the payload matters for client-side parsing.
 */
function base64url(obj: Record<string, unknown>): string {
  return btoa(JSON.stringify(obj))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

export type MockRole = 'ADMIN' | 'ADMIN_MANAGER' | 'ADMIN_DEVELOPER'

export interface MockUser {
  id: string
  email: string
  name: string
  role: MockRole
}

export function createMockUser(role: MockRole = 'ADMIN'): MockUser {
  return {
    id: 'user-1',
    email: 'admin@example.com',
    name: 'Admin Operator',
    role,
  }
}

export function createMockToken(role: MockRole = 'ADMIN'): string {
  const user = createMockUser(role)
  return [
    base64url({ alg: 'HS256', typ: 'JWT' }),
    base64url({
      sub: user.id,
      email: user.email,
      name: user.name,
      role: user.role,
      exp: Math.floor(Date.now() / 1000) + 86400,
      iat: Math.floor(Date.now() / 1000),
    }),
    'fakesignature',
  ].join('.')
}

// Backward-compatible exports — default ADMIN role.
// New role-aware tests should call createMockUser(role) / createMockToken(role) directly.
export const MOCK_USER = createMockUser('ADMIN')
export const MOCK_TOKEN = createMockToken('ADMIN')

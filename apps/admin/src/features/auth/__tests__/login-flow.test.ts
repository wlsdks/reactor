import { describe, it, expect, vi, beforeEach } from 'vitest'

// Use URL-safe base64 for test JWTs
function makeTestToken(payload: Record<string, unknown>): string {
  const encoded = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.${encoded}.test-signature`
}

describe('IAM login API functions', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('iamLogin is a callable function', async () => {
    const { iamLogin } = await import('../api')
    expect(typeof iamLogin).toBe('function')
  })

  it('IAM_ENABLED is a boolean', async () => {
    const { IAM_ENABLED } = await import('../api')
    expect(typeof IAM_ENABLED).toBe('boolean')
  })
})

describe('JWT role mapping', () => {
  it('maps reactor token with single role string', async () => {
    const { userFromToken } = await import('../../../shared/lib/jwt')
    const payload = { sub: 'user-1', email: 'user@example.com', role: 'ADMIN', name: 'Test' }
    const token = makeTestToken(payload)
    const user = userFromToken(token)
    expect(user?.role).toBe('ADMIN')
    expect(user?.email).toBe('user@example.com')
  })

  it('maps reactor-iam token with ROLE_ADMIN to ADMIN', async () => {
    const { userFromToken } = await import('../../../shared/lib/jwt')
    const payload = { sub: 'user-1', roles: ['ROLE_ADMIN'], permissions: ['ALL'] }
    const token = makeTestToken(payload)
    const user = userFromToken(token)
    expect(user?.role).toBe('ADMIN')
  })

  it('maps reactor-iam token with unknown roles to USER', async () => {
    const { userFromToken } = await import('../../../shared/lib/jwt')
    const payload = { sub: 'user-1', roles: ['ROLE_VIEWER'], permissions: [] }
    const token = makeTestToken(payload)
    const user = userFromToken(token)
    expect(user?.role).toBe('USER')
  })

  it('returns null for invalid token', async () => {
    const { userFromToken } = await import('../../../shared/lib/jwt')
    expect(userFromToken('invalid')).toBeNull()
  })

  it('returns null for token without sub claim', async () => {
    const { userFromToken } = await import('../../../shared/lib/jwt')
    const token = makeTestToken({ email: 'no-sub@example.com' })
    expect(userFromToken(token)).toBeNull()
  })
})

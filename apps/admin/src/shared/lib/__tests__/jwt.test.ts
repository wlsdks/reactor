import { describe, it, expect } from 'vitest'
import { parseJwtPayload, getTokenExpiry } from '../jwt'

// Helper to produce a minimal JWT string from a payload object
function makeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  const body = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `${header}.${body}.fakesignature`
}

describe('parseJwtPayload', () => {
  it('parses a valid JWT and returns the payload', () => {
    const token = makeJwt({ sub: 'user-1', role: 'ADMIN' })
    const result = parseJwtPayload(token)
    expect(result).not.toBeNull()
    expect(result?.sub).toBe('user-1')
    expect(result?.role).toBe('ADMIN')
  })

  it('returns null for a token with fewer than 3 parts', () => {
    expect(parseJwtPayload('only.two')).toBeNull()
  })

  it('returns null for a token with too many parts', () => {
    expect(parseJwtPayload('a.b.c.d')).toBeNull()
  })

  it('returns null for a token with invalid base64 payload', () => {
    expect(parseJwtPayload('header.!!!invalid!!!.sig')).toBeNull()
  })

  it('parses a token with exp field', () => {
    const exp = Math.floor(Date.now() / 1000) + 3600
    const token = makeJwt({ sub: 'u', exp })
    const result = parseJwtPayload(token)
    expect(result?.exp).toBe(exp)
  })

  it('returns null for empty string', () => {
    expect(parseJwtPayload('')).toBeNull()
  })
})

describe('getTokenExpiry', () => {
  it('returns the exp value from a valid token', () => {
    const exp = 9999999999
    const token = makeJwt({ exp })
    expect(getTokenExpiry(token)).toBe(exp)
  })

  it('returns null when the token has no exp field', () => {
    const token = makeJwt({ sub: 'user-1' })
    expect(getTokenExpiry(token)).toBeNull()
  })

  it('returns null for an invalid token', () => {
    expect(getTokenExpiry('not.a.token')).toBeNull()
  })
})

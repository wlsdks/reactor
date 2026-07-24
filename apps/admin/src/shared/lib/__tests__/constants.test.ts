import { describe, it, expect } from 'vitest'
import { API_BASE, AUTH_SELF_REGISTRATION_ENABLED } from '../constants'

describe('API_BASE', () => {
  it('is a string', () => {
    expect(typeof API_BASE).toBe('string')
  })

  it('defaults to empty string when VITE_API_URL is not set', () => {
    // In test environment VITE_API_URL is not configured, so it falls back to ''
    expect(API_BASE).toBe('')
  })
})

describe('AUTH_SELF_REGISTRATION_ENABLED', () => {
  it('is a boolean', () => {
    expect(typeof AUTH_SELF_REGISTRATION_ENABLED).toBe('boolean')
  })

  it('defaults to false when VITE_AUTH_ALLOW_SELF_REGISTRATION is not set', () => {
    // In test environment the env var is not set, so should be false
    expect(AUTH_SELF_REGISTRATION_ENABLED).toBe(false)
  })
})

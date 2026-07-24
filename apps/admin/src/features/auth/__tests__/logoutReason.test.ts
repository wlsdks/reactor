import { describe, it, expect, beforeEach } from 'vitest'
import {
  setLogoutReason,
  readLogoutReason,
  clearLogoutReason,
  consumeLogoutReason,
} from '../logoutReason'

describe('logoutReason', () => {
  beforeEach(() => {
    clearLogoutReason()
  })

  it('returns null when no reason is stored', () => {
    expect(readLogoutReason()).toBeNull()
  })

  it('round-trips a cross-tab reason', () => {
    setLogoutReason('cross-tab')
    expect(readLogoutReason()).toBe('cross-tab')
  })

  it('round-trips a session-expired reason', () => {
    setLogoutReason('session-expired')
    expect(readLogoutReason()).toBe('session-expired')
  })

  it('clearLogoutReason removes the stored value', () => {
    setLogoutReason('cross-tab')
    clearLogoutReason()
    expect(readLogoutReason()).toBeNull()
  })

  it('consumeLogoutReason returns and clears in one call', () => {
    setLogoutReason('cross-tab')
    expect(consumeLogoutReason()).toBe('cross-tab')
    // Second consume should be null — the value was cleared.
    expect(consumeLogoutReason()).toBeNull()
    expect(readLogoutReason()).toBeNull()
  })

  it('rejects unknown values when reading', () => {
    sessionStorage.setItem('reactor-admin-logout-reason', 'garbage-value')
    expect(readLogoutReason()).toBeNull()
  })

  it('survives sessionStorage failures gracefully', () => {
    const originalSetItem = sessionStorage.setItem
    sessionStorage.setItem = () => {
      throw new Error('quota')
    }
    try {
      // Should not throw even if sessionStorage write fails.
      expect(() => setLogoutReason('cross-tab')).not.toThrow()
    } finally {
      sessionStorage.setItem = originalSetItem
    }
  })
})

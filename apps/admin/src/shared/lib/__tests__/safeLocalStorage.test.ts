import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  STORAGE_KEYS,
  STORAGE_PREFIX,
  safeGet,
  safeGetJson,
  safeRemove,
  safeSet,
  safeSetJson,
} from '../safeLocalStorage'

describe('safeLocalStorage', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  describe('STORAGE_KEYS catalogue', () => {
    it('uses the shared prefix for new app-owned keys', () => {
      expect(STORAGE_KEYS.authToken.startsWith(STORAGE_PREFIX)).toBe(true)
      expect(STORAGE_KEYS.ragSearchHistory.startsWith(STORAGE_PREFIX)).toBe(true)
    })

    it('preserves legacy keys verbatim to avoid orphaning user state', () => {
      expect(STORAGE_KEYS.viewAs).toBe('reactor-admin-view-as')
      expect(STORAGE_KEYS.mcpServerTags).toBe('mcp-server-tags')
      expect(STORAGE_KEYS.sidebarCollapsedLegacy).toBe('reactor-sidebar-collapsed')
    })

    it('does not contain duplicates', () => {
      const values = Object.values(STORAGE_KEYS)
      expect(new Set(values).size).toBe(values.length)
    })
  })

  describe('safeGet / safeSet', () => {
    it('round-trips a string value', () => {
      expect(safeSet('test-key', 'hello')).toBe(true)
      expect(safeGet('test-key')).toBe('hello')
    })

    it('returns the default value when key is missing', () => {
      expect(safeGet('missing-key')).toBeNull()
      expect(safeGet('missing-key', 'fallback')).toBe('fallback')
    })

    it('returns the default value when getItem throws', () => {
      vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
        throw new Error('storage disabled')
      })
      expect(safeGet('any-key', 'fallback')).toBe('fallback')
    })

    it('returns false from safeSet when setItem throws', () => {
      vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
        throw new Error('storage disabled')
      })
      expect(safeSet('any-key', 'value')).toBe(false)
    })

    it('logs a warning on QuotaExceededError', () => {
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
      vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
        const err = new DOMException('quota', 'QuotaExceededError')
        throw err
      })
      expect(safeSet('big-key', 'x'.repeat(10))).toBe(false)
      expect(warn).toHaveBeenCalledWith(expect.stringContaining('quota exceeded for "big-key"'))
    })
  })

  describe('safeGetJson / safeSetJson', () => {
    it('round-trips a JSON object', () => {
      const value = { foo: 'bar', count: 3 }
      expect(safeSetJson('json-key', value)).toBe(true)
      expect(safeGetJson<typeof value>('json-key')).toEqual(value)
    })

    it('returns the default when JSON parsing fails', () => {
      window.localStorage.setItem('bad-json', '{not json')
      expect(safeGetJson<{ foo: string }>('bad-json', { foo: 'fallback' })).toEqual({
        foo: 'fallback',
      })
    })

    it('returns the default when key is missing', () => {
      expect(safeGetJson<string[]>('missing-json', [])).toEqual([])
      expect(safeGetJson<string[]>('missing-json')).toBeNull()
    })

    it('returns false from safeSetJson on serialisation failure', () => {
      const circular: Record<string, unknown> = {}
      circular.self = circular
      expect(safeSetJson('cycle', circular)).toBe(false)
    })
  })

  describe('safeRemove', () => {
    it('removes a stored key', () => {
      window.localStorage.setItem('to-remove', 'present')
      safeRemove('to-remove')
      expect(window.localStorage.getItem('to-remove')).toBeNull()
    })

    it('does not throw when removeItem throws', () => {
      vi.spyOn(window.localStorage, 'removeItem').mockImplementation(() => {
        throw new Error('storage disabled')
      })
      expect(() => safeRemove('any-key')).not.toThrow()
    })
  })
})

import { describe, it, expect } from 'vitest'
import {
  inferTypeFromKey,
  inferTypeFromValue,
  validateJson,
  serializeValue,
} from '../schema'

describe('inferTypeFromKey', () => {
  it('maps *.enabled / *.disabled / *.active / *.flag suffixes to boolean', () => {
    expect(inferTypeFromKey('feature.enabled')).toBe('boolean')
    expect(inferTypeFromKey('beta.disabled')).toBe('boolean')
    expect(inferTypeFromKey('cache.active')).toBe('boolean')
    expect(inferTypeFromKey('some.flag')).toBe('boolean')
  })

  it('maps is*/has*/should*/allow*/deny* prefixes to boolean', () => {
    expect(inferTypeFromKey('isProduction')).toBe('boolean')
    expect(inferTypeFromKey('has_admin')).toBe('boolean')
    expect(inferTypeFromKey('should-retry')).toBe('boolean')
  })

  it('maps numeric-ish suffixes to number', () => {
    expect(inferTypeFromKey('menu.order')).toBe('number')
    expect(inferTypeFromKey('cache.max')).toBe('number')
    expect(inferTypeFromKey('server.port')).toBe('number')
    expect(inferTypeFromKey('http.timeout')).toBe('number')
    expect(inferTypeFromKey('session.ttl')).toBe('number')
    expect(inferTypeFromKey('queue.priority')).toBe('number')
    expect(inferTypeFromKey('rateLimit.requestsPerMinute')).toBe('number')
    expect(inferTypeFromKey('api.requestsPerSecond')).toBe('number')
    expect(inferTypeFromKey('retry.delay')).toBe('number')
    expect(inferTypeFromKey('alert.threshold')).toBe('number')
  })

  it('returns null for keys with no known pattern', () => {
    expect(inferTypeFromKey('app.name')).toBeNull()
    expect(inferTypeFromKey('welcome.message')).toBeNull()
  })
})

describe('inferTypeFromValue', () => {
  it('recognises booleans', () => {
    expect(inferTypeFromValue('true')).toBe('boolean')
    expect(inferTypeFromValue('false')).toBe('boolean')
  })

  it('recognises integers and decimals as number', () => {
    expect(inferTypeFromValue('42')).toBe('number')
    expect(inferTypeFromValue('-7')).toBe('number')
    expect(inferTypeFromValue('3.14')).toBe('number')
  })

  it('recognises JSON objects', () => {
    expect(inferTypeFromValue('{"a":1}')).toBe('object')
    expect(inferTypeFromValue('  {"nested":{"x":true}}  ')).toBe('object')
  })

  it('recognises JSON arrays', () => {
    expect(inferTypeFromValue('[1,2,3]')).toBe('array')
    expect(inferTypeFromValue('[]')).toBe('array')
  })

  it('falls back to string for everything else', () => {
    expect(inferTypeFromValue('hello')).toBe('string')
    expect(inferTypeFromValue('{not-json')).toBe('string')
    expect(inferTypeFromValue('[incomplete')).toBe('string')
    expect(inferTypeFromValue('')).toBe('string')
  })
})

describe('validateJson', () => {
  it('accepts a well-formed JSON object', () => {
    expect(validateJson('{"a":1}', 'object')).toEqual({ valid: true })
  })

  it('rejects a JSON array when object is expected', () => {
    const res = validateJson('[1,2]', 'object')
    expect(res.valid).toBe(false)
    // Error text now goes through i18n.t(); unit tests run without the global
    // i18n initialized so the lookup may return undefined or the i18n key. We
    // only assert validity here; localized text is asserted via render tests.
  })

  it('accepts a well-formed JSON array', () => {
    expect(validateJson('[1,2,3]', 'array')).toEqual({ valid: true })
  })

  it('rejects a JSON object when array is expected', () => {
    const res = validateJson('{"a":1}', 'array')
    expect(res.valid).toBe(false)
    // See note above on i18n.t() in unit-test environment.
  })

  it('returns parse-error location from JSON.parse', () => {
    const res = validateJson('{a:1}', 'object')
    expect(res.valid).toBe(false)
    expect(typeof res.error).toBe('string')
    expect((res.error ?? '').length).toBeGreaterThan(0)
  })

  it('rejects empty input', () => {
    const res = validateJson('', 'object')
    expect(res.valid).toBe(false)
  })
})

describe('serializeValue', () => {
  it('passes string values through unchanged', () => {
    expect(serializeValue('hello', 'string')).toBe('hello')
    expect(serializeValue('  padded  ', 'string')).toBe('  padded  ')
  })

  it('normalizes numbers', () => {
    expect(serializeValue('42', 'number')).toBe('42')
    expect(serializeValue('3.14', 'number')).toBe('3.14')
    expect(serializeValue(' 5 ', 'number')).toBe('5')
  })

  it('normalizes booleans to canonical true/false', () => {
    expect(serializeValue('true', 'boolean')).toBe('true')
    expect(serializeValue('false', 'boolean')).toBe('false')
    expect(serializeValue('anything-else', 'boolean')).toBe('false')
  })

  it('re-stringifies JSON objects to strip whitespace', () => {
    expect(serializeValue('{"a": 1 ,  "b":  2}', 'object')).toBe('{"a":1,"b":2}')
  })

  it('re-stringifies JSON arrays', () => {
    expect(serializeValue('[1,  2, 3]', 'array')).toBe('[1,2,3]')
  })

  it('throws for invalid JSON so callers can surface the error', () => {
    expect(() => serializeValue('{bad json}', 'object')).toThrow()
  })
})

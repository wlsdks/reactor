import { describe, expect, it } from 'vitest'
import { keywordsToPattern } from '../schema'

describe('keywordsToPattern', () => {
  it('converts a single keyword to a simple alternation group', () => {
    expect(keywordsToPattern('Phoenix')).toBe('(?:Phoenix)')
  })

  it('converts multiple comma-separated keywords', () => {
    expect(keywordsToPattern('Phoenix, Titan, secret')).toBe('(?:Phoenix|Titan|secret)')
  })

  it('trims whitespace around keywords', () => {
    expect(keywordsToPattern('  hello ,  world  ')).toBe('(?:hello|world)')
  })

  it('returns empty string when input is empty', () => {
    expect(keywordsToPattern('')).toBe('')
  })

  it('returns empty string when input is only commas and spaces', () => {
    expect(keywordsToPattern(' , ,  , ')).toBe('')
  })

  it('escapes regex special characters in keywords', () => {
    expect(keywordsToPattern('file.txt, price$100')).toBe('(?:file\\.txt|price\\$100)')
  })

  it('handles Korean keywords', () => {
    expect(keywordsToPattern('내부용, 기밀')).toBe('(?:내부용|기밀)')
  })

  it('escapes parentheses and brackets', () => {
    expect(keywordsToPattern('fn(), arr[0]')).toBe('(?:fn\\(\\)|arr\\[0\\])')
  })
})

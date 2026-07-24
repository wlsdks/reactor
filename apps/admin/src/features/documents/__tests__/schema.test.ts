import { describe, it, expect } from 'vitest'
import { bulkSeedSchema } from '../schema'

describe('bulkSeedSchema', () => {
  const valid = { key: 'k1', title: 'T', content: 'C' }

  it('accepts a minimal valid entry', () => {
    expect(bulkSeedSchema.safeParse({ entries: [valid] }).success).toBe(true)
  })

  it('rejects empty entries array', () => {
    expect(bulkSeedSchema.safeParse({ entries: [] }).success).toBe(false)
  })

  it('rejects more than 50 entries', () => {
    const entries = Array.from({ length: 51 }, (_, i) => ({ ...valid, key: `k${i}` }))
    expect(bulkSeedSchema.safeParse({ entries }).success).toBe(false)
  })

  it('accepts exactly 50 entries', () => {
    const entries = Array.from({ length: 50 }, (_, i) => ({ ...valid, key: `k${i}` }))
    expect(bulkSeedSchema.safeParse({ entries }).success).toBe(true)
  })

  it('rejects entry with missing key', () => {
    expect(
      bulkSeedSchema.safeParse({ entries: [{ title: 'T', content: 'C' }] }).success,
    ).toBe(false)
  })

  it('rejects entry with empty key', () => {
    expect(bulkSeedSchema.safeParse({ entries: [{ ...valid, key: '' }] }).success).toBe(false)
  })

  it('rejects key longer than 128', () => {
    expect(bulkSeedSchema.safeParse({ entries: [{ ...valid, key: 'a'.repeat(129) }] }).success).toBe(
      false,
    )
  })

  it('accepts key of exactly 128 chars', () => {
    expect(bulkSeedSchema.safeParse({ entries: [{ ...valid, key: 'a'.repeat(128) }] }).success).toBe(
      true,
    )
  })

  it('rejects title longer than 300', () => {
    expect(
      bulkSeedSchema.safeParse({ entries: [{ ...valid, title: 'a'.repeat(301) }] }).success,
    ).toBe(false)
  })

  it('rejects content longer than 100,000', () => {
    expect(
      bulkSeedSchema.safeParse({ entries: [{ ...valid, content: 'a'.repeat(100_001) }] }).success,
    ).toBe(false)
  })

  it('accepts optional category/spaceKey/url', () => {
    const entry = {
      ...valid,
      category: 'safety',
      spaceKey: 'engineering',
      url: 'https://example.com/doc',
    }
    expect(bulkSeedSchema.safeParse({ entries: [entry] }).success).toBe(true)
  })

  it('rejects malformed url', () => {
    expect(
      bulkSeedSchema.safeParse({ entries: [{ ...valid, url: 'not-a-url' }] }).success,
    ).toBe(false)
  })

  it('rejects category longer than 64 (BE limit)', () => {
    expect(
      bulkSeedSchema.safeParse({ entries: [{ ...valid, category: 'a'.repeat(65) }] }).success,
    ).toBe(false)
  })

  it('rejects spaceKey longer than 64 (BE limit)', () => {
    expect(
      bulkSeedSchema.safeParse({ entries: [{ ...valid, spaceKey: 'a'.repeat(65) }] }).success,
    ).toBe(false)
  })

  it('rejects url longer than 500 (BE limit)', () => {
    const longUrl = 'https://example.com/' + 'a'.repeat(490)
    expect(bulkSeedSchema.safeParse({ entries: [{ ...valid, url: longUrl }] }).success).toBe(false)
  })

  it('rejects non-array entries', () => {
    expect(bulkSeedSchema.safeParse({ entries: 'not-an-array' }).success).toBe(false)
  })
})

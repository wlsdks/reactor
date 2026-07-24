import { describe, it, expect } from 'vitest'
import { searchRecords, type SearchableRecord } from '../searchIndex'

function record(
  id: string,
  title: string,
  haystackExtras: string[] = [],
  scope: SearchableRecord['scope'] = 'persona',
  navigateTo = `/x/${id}`,
): SearchableRecord {
  return {
    id,
    scope,
    title,
    navigateTo,
    haystack: [title, ...haystackExtras].join(' ').toLowerCase(),
  }
}

describe('searchRecords', () => {
  it('returns empty array for empty query', () => {
    const records = [record('1', 'Alpha'), record('2', 'Beta')]
    expect(searchRecords('', records)).toEqual([])
    expect(searchRecords('   ', records)).toEqual([])
  })

  it('returns no matches when query has no overlap', () => {
    const records = [record('1', 'Alpha'), record('2', 'Beta')]
    expect(searchRecords('zzz-nope', records)).toEqual([])
  })

  it('ranks title startsWith above title includes above haystack only', () => {
    const records = [
      record('a', 'Other content', ['marketing']), // haystack only → score 1
      record('b', 'Marketing tips'), // title startsWith → score 3
      record('c', 'Best marketing'), // title includes → score 2
    ]
    const result = searchRecords('marketing', records)
    expect(result.map((r) => r.id)).toEqual(['b', 'c', 'a'])
  })

  it('breaks ties alphabetically by title', () => {
    const records = [
      record('z', 'Zen node'),
      record('a', 'Alpha node'),
      record('m', 'Middle node'),
    ]
    // All match title-includes (score 2) — tie broken by title asc.
    const result = searchRecords('node', records)
    expect(result.map((r) => r.title)).toEqual(['Alpha node', 'Middle node', 'Zen node'])
  })

  it('respects the limit parameter', () => {
    const records = Array.from({ length: 25 }, (_, i) =>
      record(`id-${i}`, `match-${String(i).padStart(2, '0')}`),
    )
    const result = searchRecords('match', records, 5)
    expect(result).toHaveLength(5)
  })

  it('defaults to a limit of 20', () => {
    const records = Array.from({ length: 50 }, (_, i) =>
      record(`id-${i}`, `match-${String(i).padStart(2, '0')}`),
    )
    expect(searchRecords('match', records)).toHaveLength(20)
  })

  it('matches case-insensitively', () => {
    const records = [record('1', 'Persona Foo')]
    expect(searchRecords('PERSONA', records)).toHaveLength(1)
    expect(searchRecords('persona', records)).toHaveLength(1)
    expect(searchRecords('FoO', records)).toHaveLength(1)
  })

  it('handles special characters without throwing', () => {
    const records = [
      record('1', 'C++ guide', ['notes (advanced)']),
      record('2', 'Email: user@example.com'),
    ]
    expect(() => searchRecords('c++', records)).not.toThrow()
    expect(() => searchRecords('a@b', records)).not.toThrow()
    expect(() => searchRecords('(advanced)', records)).not.toThrow()
    expect(searchRecords('c++', records).map((r) => r.id)).toEqual(['1'])
    expect(searchRecords('user@example', records).map((r) => r.id)).toEqual(['2'])
    expect(searchRecords('(advanced)', records).map((r) => r.id)).toEqual(['1'])
  })

  it('respects a limit of 0 (returns empty)', () => {
    const records = [record('1', 'Alpha')]
    expect(searchRecords('a', records, 0)).toEqual([])
  })

  it('treats negative limit as 0', () => {
    const records = [record('1', 'Alpha')]
    expect(searchRecords('a', records, -5)).toEqual([])
  })

  it('does not mutate the input array', () => {
    const records = [record('1', 'B'), record('2', 'A')]
    const before = records.map((r) => r.id)
    searchRecords('a', records)
    expect(records.map((r) => r.id)).toEqual(before)
  })
})

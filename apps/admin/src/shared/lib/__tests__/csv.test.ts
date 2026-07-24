import { describe, it, expect } from 'vitest'
import { generateCsv } from '../csv'

describe('generateCsv', () => {
  it('generates CSV with headers and rows', () => {
    const columns = [
      { key: 'name', header: 'Name' },
      { key: 'age', header: 'Age' },
    ]
    const rows = [
      { name: 'Alice', age: 30 },
      { name: 'Bob', age: 25 },
    ]
    const result = generateCsv(columns, rows)
    expect(result).toBe('Name,Age\nAlice,30\nBob,25')
  })

  it('escapes commas and quotes in values', () => {
    const columns = [{ key: 'text', header: 'Text' }]
    const rows = [
      { text: 'hello, world' },
      { text: 'say "hi"' },
    ]
    const result = generateCsv(columns, rows)
    expect(result).toBe('Text\n"hello, world"\n"say ""hi"""')
  })

  it('handles null and undefined values', () => {
    const columns = [
      { key: 'a', header: 'A' },
      { key: 'b', header: 'B' },
    ]
    const rows = [{ a: null, b: undefined }]
    const result = generateCsv(columns, rows)
    expect(result).toBe('A,B\n,')
  })

  it('returns only header row for empty data', () => {
    const columns = [{ key: 'x', header: 'X' }]
    const result = generateCsv(columns, [])
    expect(result).toBe('X')
  })
})

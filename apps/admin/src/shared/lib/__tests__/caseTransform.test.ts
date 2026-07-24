import { describe, it, expect } from 'vitest'
import { snakeToCamel } from '../caseTransform'

describe('snakeToCamel', () => {
  it('converts flat object keys from snake_case to camelCase', () => {
    const input = { trace_id: 'abc', total_duration_ms: 120, span_count: 3 }
    expect(snakeToCamel(input)).toEqual({
      traceId: 'abc',
      totalDurationMs: 120,
      spanCount: 3,
    })
  })

  it('converts nested objects recursively', () => {
    const input = { outer_key: { inner_key: 'value', deep_nest: { leaf_key: 42 } } }
    expect(snakeToCamel(input)).toEqual({
      outerKey: { innerKey: 'value', deepNest: { leafKey: 42 } },
    })
  })

  it('converts arrays of objects', () => {
    const input = [
      { run_id: '1', tool_name: 'search' },
      { run_id: '2', tool_name: 'read' },
    ]
    expect(snakeToCamel(input)).toEqual([
      { runId: '1', toolName: 'search' },
      { runId: '2', toolName: 'read' },
    ])
  })

  it('passes primitives through unchanged', () => {
    expect(snakeToCamel('hello')).toBe('hello')
    expect(snakeToCamel(42)).toBe(42)
    expect(snakeToCamel(true)).toBe(true)
    expect(snakeToCamel(null)).toBeNull()
    expect(snakeToCamel(undefined)).toBeUndefined()
  })

  it('handles keys that are already camelCase', () => {
    const input = { alreadyCamel: 'ok', mixedSnake_case: 'also ok' }
    expect(snakeToCamel(input)).toEqual({
      alreadyCamel: 'ok',
      mixedSnakeCase: 'also ok',
    })
  })

  it('handles empty objects and arrays', () => {
    expect(snakeToCamel({})).toEqual({})
    expect(snakeToCamel([])).toEqual([])
  })

  it('handles mixed arrays with primitives and objects', () => {
    const input = [{ snake_key: 1 }, 'string', 42, null]
    expect(snakeToCamel(input)).toEqual([{ snakeKey: 1 }, 'string', 42, null])
  })

  it('handles multiple underscores in keys', () => {
    const input = { estimated_cost_usd: 0.05, avg_latency_ms: 120 }
    expect(snakeToCamel(input)).toEqual({
      estimatedCostUsd: 0.05,
      avgLatencyMs: 120,
    })
  })
})

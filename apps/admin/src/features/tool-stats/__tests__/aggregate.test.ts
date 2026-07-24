import { describe, expect, it } from 'vitest'

import { aggregateByTool } from '../aggregate'
import type { ToolStatsByToolTuple } from '../types'

describe('aggregateByTool', () => {
  it('collapses (tool, server, outcome) tuples to one row per tool', () => {
    const tuples: ToolStatsByToolTuple[] = [
      { tool: 'web.search', server: 'mcp-a', outcome: 'ok', count: 10 },
      { tool: 'web.search', server: 'mcp-a', outcome: 'error', count: 2 },
      { tool: 'web.search', server: 'mcp-b', outcome: 'ok', count: 5 },
      { tool: 'fs.read', server: 'mcp-a', outcome: 'ok', count: 3 },
    ]

    const result = aggregateByTool(tuples)

    expect(result).toHaveLength(2)
    expect(result[0]).toMatchObject({
      tool: 'web.search',
      servers: ['mcp-a', 'mcp-b'],
      total: 17,
      ok: 15,
      error: 2,
      timeout: 0,
      successRate: 15 / 17,
      errorRate: 2 / 17,
      timeoutRate: 0,
    })
    expect(result[1]).toMatchObject({
      tool: 'fs.read',
      servers: ['mcp-a'],
      total: 3,
      ok: 3,
      error: 0,
      timeout: 0,
      successRate: 1,
      errorRate: 0,
      timeoutRate: 0,
    })
  })

  it('returns empty array for empty input', () => {
    expect(aggregateByTool([])).toEqual([])
  })

  it('orders rows by descending total', () => {
    const tuples: ToolStatsByToolTuple[] = [
      { tool: 'low', server: 's', outcome: 'ok', count: 1 },
      { tool: 'high', server: 's', outcome: 'ok', count: 100 },
      { tool: 'mid', server: 's', outcome: 'ok', count: 10 },
    ]

    const result = aggregateByTool(tuples)

    expect(result.map((r) => r.tool)).toEqual(['high', 'mid', 'low'])
  })

  it('handles unknown outcome buckets without throwing (folds into total only)', () => {
    const tuples: ToolStatsByToolTuple[] = [
      { tool: 't', server: 's', outcome: 'unknown_state', count: 4 },
      { tool: 't', server: 's', outcome: 'ok', count: 6 },
    ]

    const result = aggregateByTool(tuples)

    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      tool: 't',
      total: 10,
      ok: 6,
      error: 0,
      timeout: 0,
    })
    // Unknown outcomes contribute to `total` but not the canonical buckets.
    expect(result[0].successRate).toBeCloseTo(0.6)
  })

  it('returns zero rates when total is zero (defensive against malformed BE rows)', () => {
    const tuples: ToolStatsByToolTuple[] = [
      { tool: 't', server: 's', outcome: 'ok', count: 0 },
    ]

    const result = aggregateByTool(tuples)

    expect(result[0]).toMatchObject({
      tool: 't',
      total: 0,
      successRate: 0,
      errorRate: 0,
      timeoutRate: 0,
    })
  })

  it('deduplicates server names per tool', () => {
    const tuples: ToolStatsByToolTuple[] = [
      { tool: 't', server: 'mcp-a', outcome: 'ok', count: 1 },
      { tool: 't', server: 'mcp-a', outcome: 'error', count: 1 },
      { tool: 't', server: 'mcp-a', outcome: 'timeout', count: 1 },
    ]

    const result = aggregateByTool(tuples)

    expect(result[0].servers).toEqual(['mcp-a'])
  })

  it('sorts the servers list alphabetically for stable display', () => {
    const tuples: ToolStatsByToolTuple[] = [
      { tool: 't', server: 'zeta', outcome: 'ok', count: 1 },
      { tool: 't', server: 'alpha', outcome: 'ok', count: 1 },
      { tool: 't', server: 'mu', outcome: 'ok', count: 1 },
    ]

    const result = aggregateByTool(tuples)

    expect(result[0].servers).toEqual(['alpha', 'mu', 'zeta'])
  })
})

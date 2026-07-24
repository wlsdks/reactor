import type { ToolStatsByToolTuple } from './types'

/**
 * One row per unique tool, derived from the BE's
 * `(tool, server, outcome, count)` tuples (`/api/admin/tools/stats#byTool`).
 *
 * `successRate`, `errorRate`, and `timeoutRate` are fractions of `total` —
 * the renderer multiplies by 100 for display. Unknown outcomes contribute
 * to `total` but not to any canonical rate, so unknown traffic dilutes the
 * three displayed rates without surfacing a phantom bucket.
 */
export interface AggregatedToolRow {
  tool: string
  servers: string[]
  total: number
  ok: number
  error: number
  timeout: number
  successRate: number
  errorRate: number
  timeoutRate: number
}

interface AggregationAccumulator {
  servers: Set<string>
  ok: number
  error: number
  timeout: number
  total: number
}

function emptyAccumulator(): AggregationAccumulator {
  return { servers: new Set<string>(), ok: 0, error: 0, timeout: 0, total: 0 }
}

/**
 * Collapse the BE's per-(tool, server, outcome) tuples to one row per tool,
 * sorted by descending total so the highest-traffic tools surface first.
 *
 * Outcome routing:
 * - `ok` → `ok`
 * - `error` → `error`
 * - `timeout` → `timeout`
 * - any other label (`not_found`, `invalid_arg`, etc.) → only contributes to
 *   `total`, leaving the canonical buckets untouched. The product surface
 *   exposes the three canonical rates with the understanding that the
 *   denominator includes every counted call.
 */
export function aggregateByTool(
  tuples: ToolStatsByToolTuple[],
): AggregatedToolRow[] {
  const map = new Map<string, AggregationAccumulator>()

  for (const tuple of tuples) {
    const entry = map.get(tuple.tool) ?? emptyAccumulator()
    entry.servers.add(tuple.server)
    entry.total += tuple.count
    if (tuple.outcome === 'ok') entry.ok += tuple.count
    else if (tuple.outcome === 'error') entry.error += tuple.count
    else if (tuple.outcome === 'timeout') entry.timeout += tuple.count
    map.set(tuple.tool, entry)
  }

  return [...map.entries()]
    .map(([tool, e]) => ({
      tool,
      servers: [...e.servers].sort(),
      total: e.total,
      ok: e.ok,
      error: e.error,
      timeout: e.timeout,
      successRate: e.total === 0 ? 0 : e.ok / e.total,
      errorRate: e.total === 0 ? 0 : e.error / e.total,
      timeoutRate: e.total === 0 ? 0 : e.timeout / e.total,
    }))
    .sort((a, b) => b.total - a.total)
}

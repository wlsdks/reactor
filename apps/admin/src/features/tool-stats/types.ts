/**
 * Type definitions for the `/api/admin/tools/stats` and `/api/admin/tools/accuracy`
 * endpoints. Sourced from the `reactor.agent.tool.outcome` Micrometer counter, which
 * records one tuple per `(tool, server, outcome)` combination.
 *
 * The BE returns:
 * - `byOutcome` and `byServer` as plain `Record<string, number>` maps because
 *   the set of outcome / server labels is open-ended (drivers can emit custom
 *   `outcome` values such as `not_found`, `invalid_arg`, etc.). The UI treats
 *   `ok`, `error`, and `timeout` as the canonical buckets.
 * - `byTool` as an array of per-tuple snapshots, capped at the top 50 by count.
 *   The UI collapses these to one row per tool via `aggregateByTool()`.
 *
 * `/accuracy` returns a scalar plus sub-rates (no time series — see
 * `aggregateByTool` for how multiple BE rows are folded for the table view).
 */

export type ToolOutcomeBucket = Record<string, number>

export interface ToolStatsByToolTuple {
  tool: string
  server: string
  outcome: string
  count: number
}

export interface ToolStatsResponse {
  total: number
  byOutcome: ToolOutcomeBucket
  byServer: ToolOutcomeBucket
  byTool: ToolStatsByToolTuple[]
  accuracy: number
}

export interface ToolAccuracyResponse {
  total: number
  ok: number
  accuracy: number
  invalidCallRate: number
  timeoutRate: number
  notFoundRate: number
}

export interface ToolStatsParams {
  server?: string
}

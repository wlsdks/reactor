import { api } from '../../shared/api/client'

import type {
  ToolAccuracyResponse,
  ToolStatsParams,
  ToolStatsResponse,
} from './types'

/**
 * GET /api/admin/tools/stats — outcome distribution summary.
 *
 * The BE response includes `total`, `accuracy`, `byOutcome` (Map), `byServer`
 * (Map) and `byTool` (array of `(tool, server, outcome, count)` tuples capped
 * at the top 50 by count). The optional `server` filter scopes the counters
 * to a single MCP server when set.
 *
 * No `days` window — counter readings are cumulative since process start.
 * The aggregation in `aggregate.ts` collapses the per-tuple `byTool` rows to
 * one row per tool for the ranking table.
 */
export const getToolStats = (
  params?: ToolStatsParams,
): Promise<ToolStatsResponse> => {
  const searchParams: Record<string, string> = {}
  if (params?.server && params.server.length > 0) {
    searchParams.server = params.server
  }
  return api.get('admin/tools/stats', { searchParams }).json()
}

/**
 * GET /api/admin/tools/accuracy — single accuracy gauge plus sub-rates.
 *
 * Used by the headline accuracy stat card; mirrors the BE Alertmanager surface
 * (e.g. trigger when accuracy drops below 0.85 over a 1h window).
 */
export const getToolAccuracy = (): Promise<ToolAccuracyResponse> =>
  api.get('admin/tools/accuracy').json()

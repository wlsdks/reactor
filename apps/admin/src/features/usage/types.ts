/** User cost detail from GET /api/admin/users/usage/cost */
export interface UserUsageSummary {
  userId: string
  sessionCount: number
  totalTokens: number
  totalCostUsd: number
  avgLatencyMs: number
  // 백엔드 응답은 ISO 8601 문자열 (예: "2026-04-16T19:01:06.262586+09:00"). epoch ms 아님.
  lastActivity: string
}

/** Daily usage point from GET /api/admin/users/usage/daily */
export interface UsageDailyPoint {
  day: string
  sessionCount: number
  totalTokens: number
  totalCostUsd: number
  uniqueUsers: number
}

/** Model usage from GET /api/admin/users/usage/by-model. */
export interface ModelUsageBreakdown {
  model: string
  provider: string | null
  callCount: number
  promptTokens: number
  completionTokens: number
  totalTokens: number
  totalCostUsd: number
  lastActivity: string | null
}

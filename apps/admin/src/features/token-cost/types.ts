/** Per-message cost entry from GET /api/admin/token-cost/by-session */
export interface MessageCost {
  runId: string
  model: string
  provider: string
  stepType: string
  promptTokens: number
  completionTokens: number
  totalTokens: number
  estimatedCostUsd: number
  time: number
}

/** Daily cost aggregation from GET /api/admin/token-cost/daily */
export interface DailyCost {
  day: string
  model: string
  promptTokens: number
  completionTokens: number
  totalTokens: number
  totalCostUsd: number
}

/** Top expensive session from GET /api/admin/token-cost/top-expensive */
export interface TopExpensiveSession {
  runId: string
  totalTokens: number
  totalCostUsd: number
  model: string
  time: number
}

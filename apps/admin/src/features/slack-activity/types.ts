export interface SlackChannelStats {
  channel: string
  sessionCount: number
  uniqueUsers: number
  totalTokens: number
  totalCostUsd: number
  avgLatencyMs: number
}

export interface SlackDailyStats {
  day: string
  messageCount: number
  uniqueUsers: number
  successCount: number
  failureCount: number
}

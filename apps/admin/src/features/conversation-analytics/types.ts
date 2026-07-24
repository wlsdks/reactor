export interface ChannelConversationStats {
  channel: string
  total: number
  success: number
  failure: number
  successRate: number
  avgDurationMs: number
}

export interface FailurePattern {
  errorClass: string
  count: number
  latest: string
}

export interface LatencyBucket {
  bucket: string
  count: number
}

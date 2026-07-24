export interface RagStatusSummary {
  status: string
  count: number
  latestCaptured: string
}

export interface RagChannelStats {
  channel: string
  candidateCount: number
  ingested: number
  pending: number
  rejected: number
}

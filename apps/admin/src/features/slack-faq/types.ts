export type FaqAutoReplyMode = 'OFF' | 'AUTO' | 'SUGGEST'

export interface FaqChannel {
  channelId: string
  channelName?: string
  enabled: boolean
  autoReplyMode: FaqAutoReplyMode
  confidenceThreshold: number
  daysBack: number
  reIngestIntervalHours: number
  createdAt: number
  updatedAt: number
  lastIngestedAt?: number
}

export interface CreateFaqChannelRequest {
  channelId: string
  channelName?: string
  enabled?: boolean
  autoReplyMode?: FaqAutoReplyMode
  confidenceThreshold?: number
  daysBack?: number
  reIngestIntervalHours?: number
}

export type UpdateFaqChannelRequest = Partial<Omit<CreateFaqChannelRequest, 'channelId'>>

export interface FaqChannelStats {
  channelId: string
  totalQueries: number
  matchedQueries: number
  avgConfidence: number
  hitRate: number
  windowDays: number
}

export interface FaqOrgStats {
  totalChannels: number
  totalQueries7d: number
  avgHitRate7d: number
}

export type FaqEventOutcome = 'MATCH' | 'MISS' | 'BELOW_THRESHOLD' | 'ERROR'

export interface FaqEvent {
  id: string
  ts: number
  userId?: string
  query: string
  matchedFaqId?: string
  confidence?: number
  outcome: FaqEventOutcome
}

export type FaqFeedbackRating = 'UP' | 'DOWN'

export interface FaqFeedback {
  id: string
  eventId: string
  rating: FaqFeedbackRating
  comment?: string
  ts: number
}

export interface FaqProbeRequest {
  query: string
  topK?: number
}

export interface FaqProbeMatch {
  faqId: string
  title: string
  body?: string
  confidence: number
}

export interface FaqProbeResult {
  query: string
  matches: FaqProbeMatch[]
}

export interface FaqDryRunRequest {
  query: string
  userId?: string
  asMention?: boolean
}

export type FaqDryRunDecision = 'WOULD_REPLY' | 'WOULD_SUGGEST' | 'WOULD_SKIP'

export interface FaqDryRunResult {
  decision: FaqDryRunDecision
  reason?: string
  match?: FaqProbeMatch
}

export type FaqSchedulerStatus = 'OK' | 'DEGRADED' | 'DOWN'

export type FaqSchedulerHealth =
  | { enabled: true; status: FaqSchedulerStatus; lastRunAt?: number; nextRunAt?: number }
  | { enabled: false }

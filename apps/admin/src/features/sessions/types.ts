export type { Channel, TrustStatus } from '../../shared/types/common'
import type { Channel, TrustStatus } from '../../shared/types/common'
export type FeedbackStatus = 'positive' | 'negative' | null
export type SessionExportFormat = 'json' | 'markdown'

export interface ModelInfo {
  name: string
  isDefault: boolean
}

export interface ModelsResponse {
  models: ModelInfo[]
  defaultModel: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  offset: number
  limit: number
}

export interface SessionRow {
  sessionId: string
  userId: string
  channel: Channel
  threadId?: string
  traceId?: string
  status?: string
  createdAt?: number
  updatedAt?: number
  personaId?: string | null
  personaName?: string | null
  messageCount?: number
  preview: string
  lastActivity?: number
  duration?: number
  trust?: TrustStatus
  feedback?: FeedbackStatus
  tags?: SessionTag[]
}

export interface SessionTag {
  id: string
  label: string
  comment: string | null
  createdBy: string
  createdAt: number
}

export interface SessionDetailData {
  sessionId: string
  userId: string
  threadId?: string
  traceId?: string
  status?: string
  createdAt?: number
  updatedAt?: number
  preview?: string
  runtime?: SessionRuntimeSummary
  email?: string
  ipAddress?: string
  channel: Channel
  personaId?: string | null
  personaName?: string | null
  model?: string | null
  messageCount?: number
  duration?: number
  startedAt?: number
  lastActivity?: number
  trust?: TrustStatus
  feedback?: FeedbackStatus
  tags?: SessionTag[]
  messages: ChatMessage[]
}

export interface SessionRuntimeSummary {
  runtime?: string
  graph?: string
  graphProfile?: string
  modelProvider?: string
  model?: string
  approvalStatus?: string
  outputGuardStatus?: string
  hooksStatus?: string
  stopReason?: string
  tokenUsage?: {
    inputTokens: number
    outputTokens: number
    totalTokens: number
  }
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  timestamp: number
  model?: string
  durationMs?: number
  grounded?: boolean
  blockReason?: string | null
  verifiedSourceCount?: number
}

export interface UserSummary {
  userId: string
  sessionCount: number
  lastActiveAt?: number
  lastSessionId?: string
  totalMessages?: number
  lastActive?: number
  firstSeen?: number
  trustIssueCount?: number
  negativeFeedbackCount?: number
  positiveFeedbackCount?: number
}

export interface ConversationOverview {
  totalSessions: number
  activeUsers: number
  statusCounts: Record<string, number>
}

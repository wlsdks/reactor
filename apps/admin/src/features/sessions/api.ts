import { api } from '../../shared/api/client'
import type {
  ConversationOverview,
  SessionRow,
  SessionDetailData,
  UserSummary,
  PaginatedResponse,
  SessionExportFormat,
  SessionTag,
  ModelsResponse,
  ChatMessage,
} from './types'

interface SessionQuery {
  q?: string
}

function finiteNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

function arrayValue<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function normalizeNumberRecord(value: unknown): Record<string, number> {
  return Object.fromEntries(
    Object.entries(objectRecord(value)).map(([key, count]) => [key, finiteNumber(count)]),
  )
}

function textValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
}

function timestampValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string') return undefined
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) ? timestamp : undefined
}

function normalizeChannel(value: unknown): SessionRow['channel'] {
  return ['web', 'slack', 'teams', 'discord', 'api'].includes(String(value))
    ? (value as SessionRow['channel'])
    : 'unknown'
}

function normalizeSessionRow(value: unknown): SessionRow | null {
  const row = objectRecord(value)
  const sessionId = textValue(row.sessionId)
  if (!sessionId) return null

  return {
    sessionId,
    userId: textValue(row.userId) ?? 'unknown',
    channel: normalizeChannel(row.channel),
    threadId: textValue(row.threadId),
    traceId: textValue(row.traceId),
    status: textValue(row.status),
    createdAt: timestampValue(row.createdAt),
    updatedAt: timestampValue(row.updatedAt),
    preview: textValue(row.preview) ?? '',
    personaId: textValue(row.personaId) ?? null,
    personaName: textValue(row.personaName) ?? null,
    messageCount: typeof row.messageCount === 'number' && Number.isFinite(row.messageCount)
      ? row.messageCount
      : undefined,
    lastActivity: timestampValue(row.lastActivity),
    duration: typeof row.duration === 'number' && Number.isFinite(row.duration)
      ? row.duration
      : undefined,
    trust: ['clean', 'flagged', 'blocked'].includes(String(row.trust))
      ? (row.trust as SessionRow['trust'])
      : undefined,
    feedback: ['positive', 'negative'].includes(String(row.feedback))
      ? (row.feedback as SessionRow['feedback'])
      : null,
    tags: arrayValue<SessionTag>(row.tags),
  }
}

function normalizeSessionPage(value: unknown): PaginatedResponse<SessionRow> {
  const page = objectRecord(value)
  return {
    items: arrayValue<unknown>(page.items).flatMap((item) => {
      const session = normalizeSessionRow(item)
      return session ? [session] : []
    }),
    total: finiteNumber(page.total),
    offset: finiteNumber(page.offset),
    limit: finiteNumber(page.limit),
  }
}

function normalizeUserSummary(value: unknown): UserSummary | null {
  const user = objectRecord(value)
  const userId = textValue(user.userId)
  if (!userId) return null

  return {
    userId,
    sessionCount: finiteNumber(user.sessionCount),
    lastActiveAt: timestampValue(user.lastActiveAt),
    lastSessionId: textValue(user.lastSessionId),
    totalMessages: typeof user.totalMessages === 'number' && Number.isFinite(user.totalMessages)
      ? user.totalMessages
      : undefined,
    lastActive: timestampValue(user.lastActive),
    firstSeen: timestampValue(user.firstSeen),
    trustIssueCount: typeof user.trustIssueCount === 'number' && Number.isFinite(user.trustIssueCount)
      ? user.trustIssueCount
      : undefined,
    negativeFeedbackCount:
      typeof user.negativeFeedbackCount === 'number' && Number.isFinite(user.negativeFeedbackCount)
        ? user.negativeFeedbackCount
        : undefined,
    positiveFeedbackCount:
      typeof user.positiveFeedbackCount === 'number' && Number.isFinite(user.positiveFeedbackCount)
        ? user.positiveFeedbackCount
        : undefined,
  }
}

function normalizeUserPage(value: unknown): PaginatedResponse<UserSummary> {
  const page = objectRecord(value)
  return {
    items: arrayValue<unknown>(page.items).flatMap((item) => {
      const user = normalizeUserSummary(item)
      return user ? [user] : []
    }),
    total: finiteNumber(page.total),
    offset: finiteNumber(page.offset),
    limit: finiteNumber(page.limit),
  }
}

function normalizeSessionDetail(value: unknown): SessionDetailData {
  const row = objectRecord(value)
  const metadata = objectRecord(row.metadata)
  const tokenUsage = objectRecord(metadata.tokenUsage)
  const sessionId = textValue(row.sessionId) ?? ''

  return {
    sessionId,
    threadId: textValue(row.threadId),
    traceId: textValue(row.traceId),
    userId: textValue(row.userId) ?? 'unknown',
    status: textValue(row.status),
    preview: textValue(row.preview),
    createdAt: timestampValue(row.createdAt),
    updatedAt: timestampValue(row.updatedAt),
    channel: normalizeChannel(row.channel),
    messages: arrayValue<unknown>(row.messages).flatMap((value, index) => {
      const message = objectRecord(value)
      const role = textValue(message.role)
      const content = textValue(message.content)
      if (!content || !['user', 'assistant', 'system', 'tool'].includes(role ?? '')) return []
      return [{
        id: typeof message.id === 'number' ? message.id : index,
        role: role as ChatMessage['role'],
        content,
        timestamp: timestampValue(message.timestamp) ?? 0,
      }]
    }),
    tags: arrayValue<SessionTag>(row.tags),
    trust: ['clean', 'flagged', 'blocked'].includes(String(row.trust))
      ? (row.trust as SessionDetailData['trust'])
      : undefined,
    runtime: {
      runtime: textValue(metadata.runtime) ?? textValue(metadata.model_runtime),
      graph: textValue(metadata.graph),
      graphProfile: textValue(metadata.graphProfile) ?? textValue(metadata.graph_profile),
      modelProvider: textValue(metadata.modelProvider) ?? textValue(metadata.model_provider),
      model: textValue(metadata.model) ?? textValue(metadata.selected_model),
      approvalStatus: textValue(metadata.approval_status),
      outputGuardStatus: textValue(metadata.output_guard_status),
      hooksStatus: textValue(metadata.hooks_status),
      stopReason: textValue(metadata.stop_reason),
      tokenUsage: Object.keys(tokenUsage).length > 0 ? {
        inputTokens: finiteNumber(tokenUsage.inputTokens),
        outputTokens: finiteNumber(tokenUsage.outputTokens),
        totalTokens: finiteNumber(tokenUsage.totalTokens),
      } : undefined,
    },
  }
}

function normalizeOverview(value: unknown): ConversationOverview {
  const overview = objectRecord(value)

  return {
    totalSessions: finiteNumber(overview.totalSessions),
    activeUsers: finiteNumber(overview.activeUsers ?? overview.uniqueUsers),
    statusCounts: normalizeNumberRecord(overview.statusCounts),
  }
}

export const getConversationOverview = async (period: string): Promise<ConversationOverview> => {
  const raw: unknown = await api
    .get('admin/sessions/overview', { searchParams: { period } })
    .json()
  return normalizeOverview(raw)
}

export const listSessionsFeed = async (
  filters: SessionQuery,
  offset: number,
  limit: number,
): Promise<PaginatedResponse<SessionRow>> => {
  const searchParams = buildSessionSearchParams(filters, offset, limit)
  const raw: unknown = await api.get('admin/sessions', { searchParams }).json()
  return normalizeSessionPage(raw)
}

export const getAdminSessionDetail = async (sessionId: string): Promise<SessionDetailData> => {
  const raw: unknown = await api.get(`admin/sessions/${sessionId}`).json()
  return normalizeSessionDetail(raw)
}

export const listUsers = async (params: {
  q?: string
  offset?: number
  limit?: number
}): Promise<PaginatedResponse<UserSummary>> => {
  const searchParams: Record<string, string> = {}
  if (params.q) searchParams.q = params.q
  searchParams.offset = String(params.offset ?? 0)
  searchParams.limit = String(params.limit ?? 30)
  const raw: unknown = await api.get('admin/users', { searchParams }).json()
  return normalizeUserPage(raw)
}

export const listUserSessions = async (
  userId: string,
  filters: SessionQuery,
  offset: number,
  limit: number,
): Promise<PaginatedResponse<SessionRow>> => {
  const searchParams = buildSessionSearchParams(filters, offset, limit)
  const raw: unknown = await api.get(`admin/users/${userId}/sessions`, { searchParams }).json()
  return normalizeSessionPage(raw)
}

export const deleteAdminSession = (sessionId: string): Promise<void> =>
  api.delete(`admin/sessions/${sessionId}`).then(() => undefined)

export const exportAdminSession = (sessionId: string, format: SessionExportFormat): Promise<Blob> =>
  api.get(`admin/sessions/${sessionId}/export`, { searchParams: { format } }).blob()

export const addSessionTag = (
  sessionId: string,
  label: string,
  comment?: string,
): Promise<SessionTag> =>
  api.post(`admin/sessions/${sessionId}/tags`, { json: { label, comment } }).json()

export const removeSessionTag = (sessionId: string, tagId: string): Promise<void> =>
  api.delete(`admin/sessions/${sessionId}/tags/${tagId}`).then(() => undefined)

// Legacy API — used by chat-inspector for model listing
export const listModels = (): Promise<ModelsResponse> =>
  api.get('models').json()

// --- helpers ---

function buildSessionSearchParams(
  filters: SessionQuery,
  offset: number,
  limit: number,
): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.q) params.set('q', filters.q)
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  return params
}

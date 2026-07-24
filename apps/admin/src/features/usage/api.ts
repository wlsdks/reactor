import { api } from '../../shared/api/client'
import type { UserUsageSummary, UsageDailyPoint, ModelUsageBreakdown } from './types'

type RecordLike = Record<string, unknown>

function records(value: unknown): RecordLike[] {
  return Array.isArray(value)
    ? value.filter((item): item is RecordLike => typeof item === 'object' && item !== null)
    : []
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function optionalText(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

function finite(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function field(row: RecordLike, snake: string, camel: string): unknown {
  return row[snake] ?? row[camel]
}

export const getUsersCost = async (days = 30, limit = 20): Promise<UserUsageSummary[]> => {
  const raw: unknown = await api.get('admin/users/usage/cost', {
    searchParams: { days, limit },
  }).json()
  return records(raw).map((row) => ({
    userId: text(field(row, 'user_id', 'userId')),
    sessionCount: finite(field(row, 'session_count', 'sessionCount')),
    totalTokens: finite(field(row, 'total_tokens', 'totalTokens')),
    totalCostUsd: finite(field(row, 'total_cost_usd', 'totalCostUsd')),
    avgLatencyMs: finite(field(row, 'avg_latency_ms', 'avgLatencyMs')),
    lastActivity: text(field(row, 'last_activity', 'lastActivity')),
  })).filter((row) => row.userId.length > 0)
}

export const getUsageDaily = async (days = 30): Promise<UsageDailyPoint[]> => {
  const raw: unknown = await api.get('admin/users/usage/daily', {
    searchParams: { days },
  }).json()
  return records(raw).map((row) => ({
    day: text(row.day),
    sessionCount: finite(field(row, 'session_count', 'sessionCount')),
    totalTokens: finite(field(row, 'total_tokens', 'totalTokens')),
    totalCostUsd: finite(field(row, 'total_cost_usd', 'totalCostUsd')),
    uniqueUsers: finite(field(row, 'unique_users', 'uniqueUsers')),
  })).filter((row) => row.day.length > 0)
}

export const getUsageByModel = async (days = 7): Promise<ModelUsageBreakdown[]> => {
  const raw: unknown = await api.get('admin/users/usage/by-model', {
    searchParams: { days },
  }).json()
  return records(raw).map((row) => ({
    model: text(row.model),
    provider: optionalText(row.provider),
    callCount: finite(field(row, 'call_count', 'callCount')),
    promptTokens: finite(field(row, 'prompt_tokens', 'promptTokens')),
    completionTokens: finite(field(row, 'completion_tokens', 'completionTokens')),
    totalTokens: finite(field(row, 'total_tokens', 'totalTokens')),
    totalCostUsd: finite(field(row, 'total_cost_usd', 'totalCostUsd')),
    lastActivity: optionalText(field(row, 'last_activity', 'lastActivity')),
  })).filter((row) => row.model.length > 0)
}

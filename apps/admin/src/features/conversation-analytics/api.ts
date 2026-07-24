import { api } from '../../shared/api/client'
import { snakeToCamel } from '../../shared/lib/caseTransform'
import type { ChannelConversationStats, FailurePattern, LatencyBucket } from './types'

export const getConversationsByChannel = async (
  days = 30,
): Promise<ChannelConversationStats[]> => {
  const raw = await api
    .get('admin/conversation-analytics/by-channel', {
      searchParams: { days, limit: 200 },
    })
    .json()
  return snakeToCamel(raw) as ChannelConversationStats[]
}

export const getFailurePatterns = async (days = 30): Promise<FailurePattern[]> => {
  const raw = await api
    .get('admin/conversation-analytics/failure-patterns', {
      searchParams: { days, limit: 200 },
    })
    .json()
  return snakeToCamel(raw) as FailurePattern[]
}

export const getLatencyDistribution = async (days = 7): Promise<LatencyBucket[]> => {
  const raw = await api
    .get('admin/conversation-analytics/latency-distribution', {
      searchParams: { days, limit: 200 },
    })
    .json()
  return snakeToCamel(raw) as LatencyBucket[]
}

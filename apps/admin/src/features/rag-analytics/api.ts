import { api } from '../../shared/api/client'
import { snakeToCamel } from '../../shared/lib/caseTransform'
import type { RagStatusSummary, RagChannelStats } from './types'

export const getRagStatus = async (): Promise<RagStatusSummary[]> => {
  const raw = await api
    .get('admin/rag-analytics/status', {
      searchParams: { limit: 200 },
    })
    .json()
  return snakeToCamel(raw) as RagStatusSummary[]
}

export const getRagByChannel = async (days = 30): Promise<RagChannelStats[]> => {
  const raw = await api
    .get('admin/rag-analytics/by-channel', {
      searchParams: { days, limit: 200 },
    })
    .json()
  return snakeToCamel(raw) as RagChannelStats[]
}

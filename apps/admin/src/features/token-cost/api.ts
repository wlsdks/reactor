import { api } from '../../shared/api/client'
import { snakeToCamel } from '../../shared/lib/caseTransform'
import type { MessageCost, DailyCost, TopExpensiveSession } from './types'

export const getSessionCosts = async (sessionId: string): Promise<MessageCost[]> => {
  const raw = await api.get('admin/token-cost/by-session', {
    searchParams: { sessionId, limit: 200 },
  }).json()
  return snakeToCamel(raw) as MessageCost[]
}

export const getDailyCost = async (days = 30): Promise<DailyCost[]> => {
  const raw = await api.get('admin/token-cost/daily', {
    searchParams: { days, limit: 200 },
  }).json()
  return snakeToCamel(raw) as DailyCost[]
}

export const getTopExpensive = async (days = 7, limit = 20): Promise<TopExpensiveSession[]> => {
  const raw = await api.get('admin/token-cost/top-expensive', {
    searchParams: { days, limit },
  }).json()
  return snakeToCamel(raw) as TopExpensiveSession[]
}

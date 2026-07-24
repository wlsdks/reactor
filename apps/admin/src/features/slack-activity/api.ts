import { api } from '../../shared/api/client'
import { snakeToCamel } from '../../shared/lib/caseTransform'
import type { SlackChannelStats, SlackDailyStats } from './types'

export const getSlackChannels = async (days = 30): Promise<SlackChannelStats[]> => {
  const raw = await api.get('admin/slack-activity/channels', { searchParams: { days, limit: 200 } }).json()
  return snakeToCamel(raw) as SlackChannelStats[]
}

export const getSlackDaily = async (days = 30): Promise<SlackDailyStats[]> => {
  const raw = await api.get('admin/slack-activity/daily', { searchParams: { days, limit: 200 } }).json()
  return snakeToCamel(raw) as SlackDailyStats[]
}

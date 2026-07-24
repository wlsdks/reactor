import { http, HttpResponse } from 'msw'
import { DAY, NOW } from './shared'
import type { SlackChannelStats, SlackDailyStats } from '../../features/slack-activity/types'

export const mockSlackChannels: SlackChannelStats[] = [
  { channel: '#general', sessionCount: 245, uniqueUsers: 42, totalTokens: 185000, totalCostUsd: 12.5, avgLatencyMs: 320 },
  { channel: '#support', sessionCount: 180, uniqueUsers: 28, totalTokens: 132000, totalCostUsd: 9.2, avgLatencyMs: 410 },
  { channel: '#engineering', sessionCount: 120, uniqueUsers: 15, totalTokens: 98000, totalCostUsd: 6.8, avgLatencyMs: 280 },
]

function generateDailyStats(days: number): SlackDailyStats[] {
  const result: SlackDailyStats[] = []
  for (let i = days; i >= 0; i--) {
    const d = new Date(NOW - i * DAY)
    const day = d.toISOString().split('T')[0]
    const messageCount = Math.round(40 + Math.random() * 60)
    const uniqueUsers = Math.round(8 + Math.random() * 20)
    const successCount = Math.round(messageCount * (0.85 + Math.random() * 0.12))
    const failureCount = messageCount - successCount
    result.push({ day, messageCount, uniqueUsers, successCount, failureCount })
  }
  return result
}

export const mockSlackDaily = generateDailyStats(30)

export const slackActivityHandlers = [
  http.get('/api/admin/slack-activity/channels', () => {
    return HttpResponse.json(mockSlackChannels.map((c) => ({
      channel: c.channel,
      session_count: c.sessionCount,
      unique_users: c.uniqueUsers,
      total_tokens: c.totalTokens,
      total_cost_usd: c.totalCostUsd,
      avg_latency_ms: c.avgLatencyMs,
    })))
  }),

  http.get('/api/admin/slack-activity/daily', () => {
    return HttpResponse.json(mockSlackDaily.map((d) => ({
      day: d.day,
      message_count: d.messageCount,
      unique_users: d.uniqueUsers,
      success_count: d.successCount,
      failure_count: d.failureCount,
    })))
  }),
]

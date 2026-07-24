import { http, HttpResponse } from 'msw'
import { NOW } from './shared'
import type { ChannelConversationStats, FailurePattern, LatencyBucket } from '../../features/conversation-analytics/types'

export const mockChannelConversationStats: ChannelConversationStats[] = [
  { channel: 'web', total: 1250, success: 1100, failure: 150, successRate: 88.0, avgDurationMs: 1200 },
  { channel: 'slack', total: 860, success: 810, failure: 50, successRate: 94.2, avgDurationMs: 980 },
  { channel: 'teams', total: 340, success: 295, failure: 45, successRate: 86.8, avgDurationMs: 1450 },
]

export const mockFailurePatterns: FailurePattern[] = [
  { errorClass: 'LLM_TIMEOUT', count: 85, latest: new Date(NOW - 1800000).toISOString() },
  { errorClass: 'CONTEXT_OVERFLOW', count: 42, latest: new Date(NOW - 3600000).toISOString() },
  { errorClass: 'TOOL_EXECUTION_ERROR', count: 28, latest: new Date(NOW - 7200000).toISOString() },
  { errorClass: 'GUARD_BLOCKED', count: 15, latest: new Date(NOW - 86400000).toISOString() },
]

export const mockLatencyBuckets: LatencyBucket[] = [
  { bucket: '< 1s', count: 820 },
  { bucket: '1-3s', count: 1450 },
  { bucket: '3-5s', count: 380 },
  { bucket: '5-10s', count: 120 },
  { bucket: '> 10s', count: 30 },
]

export const conversationAnalyticsHandlers = [
  http.get('/api/admin/conversation-analytics/by-channel', () => {
    return HttpResponse.json(mockChannelConversationStats.map((c) => ({
      channel: c.channel,
      total: c.total,
      success: c.success,
      failure: c.failure,
      success_rate: c.successRate,
      avg_duration_ms: c.avgDurationMs,
    })))
  }),

  http.get('/api/admin/conversation-analytics/failure-patterns', () => {
    return HttpResponse.json(mockFailurePatterns.map((f) => ({
      error_class: f.errorClass,
      count: f.count,
      latest: f.latest,
    })))
  }),

  http.get('/api/admin/conversation-analytics/latency-distribution', () => {
    return HttpResponse.json(mockLatencyBuckets.map((b) => ({
      bucket: b.bucket,
      count: b.count,
    })))
  }),
]

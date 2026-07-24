import { http, HttpResponse } from 'msw'
import { NOW } from './shared'
import type { RagStatusSummary, RagChannelStats } from '../../features/rag-analytics/types'

export const mockRagStatuses: RagStatusSummary[] = [
  { status: 'PENDING', count: 24, latestCaptured: new Date(NOW - 3600000).toISOString() },
  { status: 'INGESTED', count: 1832, latestCaptured: new Date(NOW - 7200000).toISOString() },
  { status: 'REJECTED', count: 47, latestCaptured: new Date(NOW - 86400000).toISOString() },
]

export const mockRagByChannel: RagChannelStats[] = [
  { channel: '#support', candidateCount: 420, ingested: 380, pending: 15, rejected: 25 },
  { channel: '#engineering', candidateCount: 310, ingested: 290, pending: 8, rejected: 12 },
  { channel: '#general', candidateCount: 180, ingested: 162, pending: 1, rejected: 17 },
]

export const ragAnalyticsHandlers = [
  http.get('/api/admin/rag-analytics/status', () => {
    return HttpResponse.json(mockRagStatuses.map((s) => ({
      status: s.status,
      count: s.count,
      latest_captured: s.latestCaptured,
    })))
  }),

  http.get('/api/admin/rag-analytics/by-channel', () => {
    return HttpResponse.json(mockRagByChannel.map((c) => ({
      channel: c.channel,
      candidate_count: c.candidateCount,
      ingested: c.ingested,
      pending: c.pending,
      rejected: c.rejected,
    })))
  }),
]

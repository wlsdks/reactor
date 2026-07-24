import { http, HttpResponse } from 'msw'

import type {
  FaqChannel,
  FaqChannelStats,
  FaqDryRunResult,
  FaqEvent,
  FaqFeedback,
  FaqOrgStats,
  FaqProbeResult,
  FaqSchedulerHealth,
} from '../../features/slack-faq/types'

let mockChannels: FaqChannel[] = [
  {
    channelId: 'C-FAQ-DEMO',
    channelName: 'general',
    enabled: true,
    autoReplyMode: 'AUTO',
    confidenceThreshold: 0.7,
    daysBack: 30,
    reIngestIntervalHours: 24,
    createdAt: 1700000000000,
    updatedAt: 1700100000000,
    lastIngestedAt: 1700200000000,
  },
]

const mockStats: Record<string, FaqChannelStats> = {
  'C-FAQ-DEMO': {
    channelId: 'C-FAQ-DEMO',
    totalQueries: 12,
    matchedQueries: 9,
    avgConfidence: 0.84,
    hitRate: 0.75,
    windowDays: 7,
  },
}

const mockOrgStats: FaqOrgStats = {
  totalChannels: 1,
  totalQueries7d: 12,
  avgHitRate7d: 0.75,
}

const mockEvents: Record<string, FaqEvent[]> = {
  'C-FAQ-DEMO': [
    {
      id: 'ev-1',
      ts: 1700300000000,
      userId: 'U-001',
      query: 'how to reset password',
      matchedFaqId: 'F-1',
      confidence: 0.92,
      outcome: 'MATCH',
    },
    {
      id: 'ev-2',
      ts: 1700300100000,
      userId: 'U-002',
      query: 'unrelated topic',
      outcome: 'MISS',
    },
  ],
}

const mockFeedback: Record<string, FaqFeedback[]> = {
  'C-FAQ-DEMO': [
    { id: 'fb-1', eventId: 'ev-1', rating: 'UP', comment: 'helpful', ts: 1700300050000 },
    { id: 'fb-2', eventId: 'ev-2', rating: 'DOWN', ts: 1700300150000 },
  ],
}

const mockHealth: FaqSchedulerHealth = { enabled: true, status: 'OK' }

export function resetSlackFaqMocks() {
  mockChannels = [
    {
      channelId: 'C-FAQ-DEMO',
      channelName: 'general',
      enabled: true,
      autoReplyMode: 'AUTO',
      confidenceThreshold: 0.7,
      daysBack: 30,
      reIngestIntervalHours: 24,
      createdAt: 1700000000000,
      updatedAt: 1700100000000,
      lastIngestedAt: 1700200000000,
    },
  ]
}

export const slackFaqHandlers = [
  // List channels
  http.get('/api/admin/slack/channels/faq', () => HttpResponse.json(mockChannels)),

  // Org stats — note: must come BEFORE the {channelId} handler in MSW order
  // since it's a more specific route under the same prefix.
  http.get('/api/admin/slack/channels/faq/stats', () => HttpResponse.json(mockOrgStats)),

  // Scheduler health
  http.get('/api/admin/slack/channels/faq/scheduler/health', () =>
    HttpResponse.json(mockHealth),
  ),

  // Get one channel
  http.get('/api/admin/slack/channels/faq/:channelId', ({ params }) => {
    const found = mockChannels.find((c) => c.channelId === params.channelId)
    if (!found) return new HttpResponse(null, { status: 404 })
    return HttpResponse.json(found)
  }),

  // Channel stats
  http.get('/api/admin/slack/channels/faq/:channelId/stats', ({ params }) => {
    const id = params.channelId as string
    return HttpResponse.json(mockStats[id] ?? mockStats['C-FAQ-DEMO'])
  }),

  // Channel events
  http.get('/api/admin/slack/channels/faq/:channelId/events', ({ params }) => {
    return HttpResponse.json(mockEvents[params.channelId as string] ?? [])
  }),

  // Channel feedback
  http.get('/api/admin/slack/channels/faq/:channelId/feedback', ({ params }) => {
    return HttpResponse.json(mockFeedback[params.channelId as string] ?? [])
  }),

  // Create channel
  http.post('/api/admin/slack/channels/faq', async ({ request }) => {
    const body = (await request.json()) as Partial<FaqChannel>
    const channel: FaqChannel = {
      channelId: body.channelId ?? 'C-NEW',
      channelName: body.channelName,
      enabled: body.enabled ?? true,
      autoReplyMode: body.autoReplyMode ?? 'OFF',
      confidenceThreshold: body.confidenceThreshold ?? 0.7,
      daysBack: body.daysBack ?? 30,
      reIngestIntervalHours: body.reIngestIntervalHours ?? 24,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    }
    mockChannels = [...mockChannels, channel]
    return HttpResponse.json(channel, { status: 201 })
  }),

  // Update channel
  http.patch('/api/admin/slack/channels/faq/:channelId', async ({ params, request }) => {
    const id = params.channelId as string
    const body = (await request.json()) as Partial<FaqChannel>
    let updated: FaqChannel | undefined
    mockChannels = mockChannels.map((c) => {
      if (c.channelId !== id) return c
      updated = { ...c, ...body, updatedAt: Date.now() }
      return updated
    })
    if (!updated) return new HttpResponse(null, { status: 404 })
    return HttpResponse.json(updated)
  }),

  // Delete channel
  http.delete('/api/admin/slack/channels/faq/:channelId', ({ params }) => {
    const id = params.channelId as string
    const before = mockChannels.length
    mockChannels = mockChannels.filter((c) => c.channelId !== id)
    if (mockChannels.length === before) {
      return new HttpResponse(null, { status: 404 })
    }
    return new HttpResponse(null, { status: 204 })
  }),

  // Ingest (re-index)
  http.post('/api/admin/slack/channels/faq/:channelId/ingest', () => {
    return new HttpResponse(null, { status: 202 })
  }),

  // Probe
  http.post('/api/admin/slack/channels/faq/:channelId/probe', async ({ request }) => {
    const body = (await request.json()) as { query?: string }
    const result: FaqProbeResult = {
      query: body.query ?? '',
      matches: [
        { faqId: 'F-1', title: 'Reset password', confidence: 0.92 },
        { faqId: 'F-2', title: 'Forgot password', body: 'Use the reset flow', confidence: 0.71 },
      ],
    }
    return HttpResponse.json(result)
  }),

  // Dry-run
  http.post('/api/admin/slack/channels/faq/:channelId/dry-run', async () => {
    const result: FaqDryRunResult = {
      decision: 'WOULD_REPLY',
      reason: 'High confidence match',
      match: { faqId: 'F-1', title: 'Reset password', confidence: 0.92 },
    }
    return HttpResponse.json(result)
  }),
]

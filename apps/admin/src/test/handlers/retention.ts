import { http, HttpResponse } from 'msw'
import type { RetentionPolicy } from '../../features/retention/types'

export const mockRetentionPolicy: RetentionPolicy = {
  sessionRetentionDays: 90,
  conversationRetentionDays: 365,
  auditRetentionDays: 730,
  metricRetentionDays: 180,
  checkpointRetentionDays: 90,
}

let currentPolicy = { ...mockRetentionPolicy }

export const retentionHandlers = [
  http.get('/api/admin/retention', () => {
    return HttpResponse.json(currentPolicy)
  }),

  http.put('/api/admin/retention', async ({ request }) => {
    const body = await request.json() as Partial<RetentionPolicy>
    currentPolicy = { ...currentPolicy, ...body }
    return HttpResponse.json(currentPolicy)
  }),
]

import { http, HttpResponse } from 'msw'
import { NOW } from './shared'

interface BackendLatencyPoint {
  time: string
  avgMs: number
  p95Ms: number
  count: number
}

function generateTimeSeries(): BackendLatencyPoint[] {
  const points: BackendLatencyPoint[] = []
  const intervalMs = 5 * 60 * 1000 // 5 minutes
  const count = 288 // 24h of 5-min intervals

  for (let i = 0; i < count; i++) {
    const timestamp = NOW - (count - i) * intervalMs
    const hourOfDay = new Date(timestamp).getHours()

    const loadFactor = hourOfDay >= 9 && hourOfDay <= 17 ? 1.3 : 0.8
    const noise = () => (Math.random() - 0.5) * 40
    const spike = Math.random() > 0.95 ? 2.5 : 1

    const avgMs = Math.max(50, Math.round((180 + noise() * 2) * loadFactor * spike))
    const p95Ms = Math.max(200, Math.round((750 + noise() * 4) * loadFactor * spike))
    const requestCount = Math.round((120 + Math.random() * 80) * loadFactor)

    points.push({
      time: new Date(timestamp).toISOString(),
      avgMs,
      p95Ms,
      count: requestCount,
    })
  }

  return points
}

export const mockLatencySummary = {
  p50: 195,
  p95: 820,
  p99: 1950,
}

export const mockLatencyTimeSeries = generateTimeSeries()

export const latencyHandlers = [
  http.get('/api/admin/metrics/latency/timeseries', () => {
    return HttpResponse.json(mockLatencyTimeSeries)
  }),

  http.get('/api/admin/metrics/latency/summary', () => {
    return HttpResponse.json(mockLatencySummary)
  }),
]

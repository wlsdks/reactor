import { api } from '../../shared/api/client'
import type { LatencyDataPoint, LatencySummary } from './types'

function finiteNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function validTimestamp(value: unknown): number | null {
  if (typeof value !== 'string' && typeof value !== 'number') return null
  const timestamp = new Date(value).getTime()
  return Number.isFinite(timestamp) ? timestamp : null
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : null
}

export const getLatencyTimeSeries = async (days = 1): Promise<LatencyDataPoint[]> => {
  const raw: unknown = await api
    .get('admin/metrics/latency/timeseries', {
      searchParams: { days, limit: 200 },
    })
    .json()
  if (!Array.isArray(raw)) return []

  return raw.flatMap((value) => {
    const point = record(value)
    if (!point) return []
    const timestamp = validTimestamp(point.time ?? point.bucket)
    if (timestamp == null) return []
    const hasP95 = typeof point.p95Ms === 'number' && Number.isFinite(point.p95Ms)
    return [
      {
        timestamp,
        avg: finiteNumber(point.avgMs ?? point.averageMs),
        p95: finiteNumber(point.p95Ms),
        p95Available: hasP95 ? 1 : 0,
        count: finiteNumber(point.count),
      },
    ]
  })
}

export const getLatencySummary = async (): Promise<LatencySummary> => {
  const raw: unknown = await api.get('admin/metrics/latency/summary').json()
  const summary = record(raw) ?? {}
  const p50 = finiteNumber(summary.p50 ?? summary.p50Ms)
  const p95 = finiteNumber(summary.p95 ?? summary.p95Ms)
  const p99 = finiteNumber(summary.p99 ?? summary.p99Ms)
  const explicitCount = finiteNumber(summary.count)
  const legacyHasSamples =
    explicitCount === 0 &&
    summary.count == null &&
    [p50, p95, p99].some((value) => value > 0)

  return {
    count: legacyHasSamples ? 1 : explicitCount,
    p50,
    p95,
    p99,
  }
}

/** Backend: LatencyPoint(time, avgMs, p95Ms, count) — transformed in API layer */
export interface LatencyDataPoint {
  timestamp: number
  avg: number
  p95: number
  /** Numeric chart-safe marker; 1 only when the backend supplied a real p95 value. */
  p95Available: number
  count: number
  [key: string]: number
}

/** Backend: Map<String, Long> with keys p50, p95, p99 */
export interface LatencySummary {
  count: number
  p50: number
  p95: number
  p99: number
}

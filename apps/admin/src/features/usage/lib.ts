import type { UsageDailyPoint } from './types'

/**
 * Map raw daily trend points to chart data sorted ascending by date.
 *
 * The backend returns points in descending order (newest first), but
 * time-series charts must render past (left) to present (right). This
 * helper normalises the order so the X-axis direction is always correct.
 */
export function buildCostTrendChartData(
  dailyTrend: { day: string; totalCostUsd: number }[],
): { date: string; cost: number }[] {
  return [...dailyTrend]
    .sort((a, b) => a.day.localeCompare(b.day))
    .map((d) => ({
      date: d.day,
      cost: d.totalCostUsd,
    }))
}

// ─────────────────────────────────────────────────────────────────────────────
// Period aggregation helpers
//
// The backend exposes a single daily-resolution endpoint. The dashboard /
// usage cost cards need today / week / month roll-ups + delta vs prior period.
// We derive everything client-side from the existing dailyTrend response so we
// don't need a new endpoint. Day strings are ISO `YYYY-MM-DD` per backend.
// ─────────────────────────────────────────────────────────────────────────────

const DAY_MS = 24 * 60 * 60 * 1000

/** Format a Date in ISO `YYYY-MM-DD` (UTC). */
function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

/** Sum totalCostUsd across daily points. */
export function sumDailyCost(points: UsageDailyPoint[]): number {
  return points.reduce((acc, p) => acc + (Number.isFinite(p.totalCostUsd) ? p.totalCostUsd : 0), 0)
}

export interface PeriodCost {
  totalCostUsd: number
  totalTokens: number
}

/** Aggregate dailyTrend points whose `day` falls within the [from, to] window (inclusive). */
export function aggregateDailyCost(
  points: UsageDailyPoint[],
  fromIso: string,
  toIso: string,
): PeriodCost {
  let cost = 0
  let tokens = 0
  for (const p of points) {
    if (p.day >= fromIso && p.day <= toIso) {
      cost += Number.isFinite(p.totalCostUsd) ? p.totalCostUsd : 0
      tokens += Number.isFinite(p.totalTokens) ? p.totalTokens : 0
    }
  }
  return { totalCostUsd: cost, totalTokens: tokens }
}

export interface CostPeriodAggregates {
  /** Today's cost (single day matching `now`). */
  today: PeriodCost
  /** Cost for the trailing 7 days inclusive of today. */
  week: PeriodCost
  /** Cost for the trailing 30 days inclusive of today. */
  month: PeriodCost
  /** Yesterday's cost (for today-vs-yesterday delta). */
  yesterday: PeriodCost
  /** Prior 7 days (for week-over-week delta). */
  priorWeek: PeriodCost
  /** Prior 30 days (for month-over-month delta). */
  priorMonth: PeriodCost
}

/**
 * Compute today / week / month roll-ups plus prior-period equivalents from a
 * single dailyTrend payload. `nowMs` is injected for testability.
 */
export function computeCostPeriodAggregates(
  points: UsageDailyPoint[],
  nowMs: number = Date.now(),
): CostPeriodAggregates {
  const today = new Date(nowMs)
  today.setUTCHours(0, 0, 0, 0)

  const todayIso = toISODate(today)
  const yesterdayIso = toISODate(new Date(today.getTime() - DAY_MS))

  const weekFromIso = toISODate(new Date(today.getTime() - 6 * DAY_MS))
  const priorWeekFromIso = toISODate(new Date(today.getTime() - 13 * DAY_MS))
  const priorWeekToIso = toISODate(new Date(today.getTime() - 7 * DAY_MS))

  const monthFromIso = toISODate(new Date(today.getTime() - 29 * DAY_MS))
  const priorMonthFromIso = toISODate(new Date(today.getTime() - 59 * DAY_MS))
  const priorMonthToIso = toISODate(new Date(today.getTime() - 30 * DAY_MS))

  return {
    today: aggregateDailyCost(points, todayIso, todayIso),
    yesterday: aggregateDailyCost(points, yesterdayIso, yesterdayIso),
    week: aggregateDailyCost(points, weekFromIso, todayIso),
    priorWeek: aggregateDailyCost(points, priorWeekFromIso, priorWeekToIso),
    month: aggregateDailyCost(points, monthFromIso, todayIso),
    priorMonth: aggregateDailyCost(points, priorMonthFromIso, priorMonthToIso),
  }
}

/**
 * Percentage delta between current and prior period.
 * Returns 0 when prior is 0 (avoids divide-by-zero / Infinity surprises in UI).
 */
export function percentDelta(current: number, prior: number): number {
  if (!Number.isFinite(prior) || prior <= 0) return 0
  return ((current - prior) / prior) * 100
}

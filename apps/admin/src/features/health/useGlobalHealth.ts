import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../../shared/lib/queryKeys'
import { STALE_TIMES } from '../../shared/lib/staleTimes'
import { getDoctorSummary, getDoctorReport } from '../doctor/api'
import { deriveDoctorDisplayStatus } from '../doctor/healthStatus'
import type { DoctorReport, DoctorSummary } from '../doctor/types'

/**
 * Shared hook for the header health badge and any other consumer that needs
 * a high-level operational status without managing its own polling cadence.
 *
 * Reuses the canonical `queryKeys.doctor.summary()` cache slot so the data is
 * shared with `DoctorBanner` on the dashboard — TanStack Query dedupes the
 * fetch and both components stay in sync.
 *
 * Detail (per-check pass/total counts) comes from the full `/admin/doctor`
 * report. The report query is enabled lazily only when the summary is loaded
 * (and the user is on a route that already mounts the badge), so we don't pay
 * the cost on first paint or on the login screen.
 */
export interface GlobalHealth {
  summary: DoctorSummary | undefined
  report: DoctorReport | undefined
  isLoading: boolean
  isError: boolean
  error: unknown
  passed: number
  total: number
  criticalCount: number
  warnCount: number
  generatedAt: string | undefined
  effectiveStatus: 'OK' | 'WARN' | 'ERROR' | undefined
}

export function useGlobalHealth(): GlobalHealth {
  const summaryQuery = useQuery({
    queryKey: queryKeys.doctor.summary(),
    queryFn: getDoctorSummary,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    staleTime: STALE_TIMES.STANDARD,
  })

  const reportQuery = useQuery({
    queryKey: queryKeys.doctor.report(),
    queryFn: getDoctorReport,
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
    staleTime: STALE_TIMES.SLOW,
    enabled: summaryQuery.data !== undefined,
  })

  const sections = reportQuery.data?.sections ?? []
  const total = sections.length
  const passed = sections.filter((section) => section.status === 'OK').length
  const criticalCount = sections.filter((section) => section.status === 'ERROR').length
  const warnCount = sections.filter((section) => section.status === 'WARN' || section.status === 'SKIPPED').length

  return {
    summary: summaryQuery.data,
    report: reportQuery.data,
    isLoading: summaryQuery.isLoading,
    isError: summaryQuery.isError,
    error: summaryQuery.error,
    passed,
    total,
    criticalCount,
    warnCount,
    generatedAt: summaryQuery.data?.generatedAt,
    effectiveStatus: reportQuery.data
      ? deriveDoctorDisplayStatus(reportQuery.data)
      : summaryQuery.data?.status,
  }
}

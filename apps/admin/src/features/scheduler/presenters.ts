import type { ScheduledJobExecutionResponse } from './types'

/**
 * Keeps scheduler timing readable in the Korean operator console without
 * exposing the millisecond storage unit in routine status views.
 */
export function formatSchedulerDuration(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '-'
  if (value < 1_000) return `${Math.round(value)}밀리초`
  if (value < 60_000) return `${Math.round(value / 100) / 10}초`

  const totalSeconds = Math.round(value / 1_000)
  const hours = Math.floor(totalSeconds / 3_600)
  const minutes = Math.floor((totalSeconds % 3_600) / 60)
  const seconds = totalSeconds % 60
  const parts = [hours ? `${hours}시간` : '', minutes ? `${minutes}분` : '', seconds ? `${seconds}초` : ''].filter(Boolean)
  return parts.join(' ')
}

/**
 * Common scheduler time zones are presented as a familiar operating region;
 * an unfamiliar but valid IANA value remains visible rather than guessed.
 */
export function formatSchedulerTimezone(timezone: string | null | undefined): string {
  if (!timezone) return '-'
  if (timezone === 'Asia/Seoul') return '한국 표준시 (서울)'
  if (timezone === 'UTC') return '협정 세계시 (UTC)'
  return timezone
}

export function executionSummary(execution: ScheduledJobExecutionResponse): string {
  if (execution.failureReason) return execution.failureReason
  if (execution.resultPreview) return execution.resultPreview
  return '—'
}

export function executionTimestamp(execution: ScheduledJobExecutionResponse): number {
  return execution.completedAt ?? execution.startedAt
}

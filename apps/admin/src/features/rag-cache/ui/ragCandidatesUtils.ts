import { formatDateTimeCompact } from '../../../shared/lib/formatters'
import type { RagCandidateStatus } from '../types'

export type StatusFilter = 'ALL' | RagCandidateStatus

export const STATUS_OPTIONS: StatusFilter[] = ['ALL', 'PENDING', 'APPROVED', 'REJECTED']

export function truncate(text: string, max = 80): string {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max)}...` : text
}

export function formatDate(ts: number): string {
  return formatDateTimeCompact(ts) || String(ts)
}

/**
 * Look up the Korean label for a backend candidate review status. Falls back
 * to a safe localized unknown state when the backend introduces a new enum.
 */
export function localizeReviewStatus(status: string, t: (key: string) => string): string {
  const key = `ragCachePage.statusLabels.${status.toLowerCase()}`
  const localized = t(key)
  return localized === key ? t('ragCachePage.statusLabels.unknown') : localized
}

import i18n from 'i18next'

/**
 * Localized relative time helper. Returns a human-readable Korean string
 * (e.g. "방금 전", "24분 전", "3일 전") for the elapsed duration between the
 * supplied timestamp and `Date.now()`.
 *
 * Inputs that are negative (future timestamps), null/undefined/invalid all
 * collapse to "방금 전" / empty string respectively so callers can drop the
 * result straight into JSX without conditional guards.
 */
export function formatRelativeTimeKo(input: Date | string | number | null | undefined): string {
  if (input === null || input === undefined || input === '') return ''
  const date = input instanceof Date ? input : new Date(input)
  const epochMs = date.getTime()
  if (Number.isNaN(epochMs)) return ''

  const diffMs = Date.now() - epochMs
  if (diffMs < 60_000) return i18n.t('common.relativeTime.justNow')

  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 60) return i18n.t('common.relativeTime.minutesAgo', { count: minutes })

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return i18n.t('common.relativeTime.hoursAgo', { count: hours })

  const days = Math.floor(hours / 24)
  if (days < 30) return i18n.t('common.relativeTime.daysAgo', { count: days })

  const months = Math.floor(days / 30)
  if (months < 12) return i18n.t('common.relativeTime.monthsAgo', { count: months })

  const years = Math.floor(days / 365)
  return i18n.t('common.relativeTime.yearsAgo', { count: years })
}

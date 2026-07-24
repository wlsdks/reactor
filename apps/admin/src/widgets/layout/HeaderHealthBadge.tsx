import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useGlobalHealth } from '../../features/health'
import { formatRelativeTimeKo } from '../../shared/lib/formatRelativeTimeKo'
import { getErrorMessage } from '../../shared/lib/getErrorMessage'
import type { TFunction } from 'i18next'

type BadgeIntent = 'ok' | 'warn' | 'error' | 'unknown' | 'unavailable'

function intentForStatus(
  isLoading: boolean,
  isError: boolean,
  status: 'OK' | 'WARN' | 'ERROR' | undefined,
): BadgeIntent {
  if (isError) return 'unavailable'
  if (isLoading || !status) return 'unknown'
  if (status === 'ERROR') return 'error'
  if (status === 'WARN') return 'warn'
  return 'ok'
}

const INTENT_TOKEN: Record<BadgeIntent, string> = {
  ok: 'var(--color-success)',
  warn: 'var(--color-warning)',
  error: 'var(--color-error)',
  unknown: 'var(--color-neutral)',
  unavailable: 'var(--color-error)',
}

const INTENT_LABEL_KEY: Record<BadgeIntent, string> = {
  ok: 'header.health.statusOk',
  warn: 'header.health.statusWarn',
  error: 'header.health.statusError',
  unknown: 'header.health.statusUnknown',
  unavailable: 'header.health.statusUnavailable',
}

/**
 * Keeps status labels registered with the static i18n verifier. The runtime
 * resolves these keys through INTENT_LABEL_KEY, which the verifier cannot
 * follow as literal `t()` call sites.
 */
export function markHeaderHealthKeysForI18nVerifier(t: TFunction): void {
  void t('header.health.statusOk')
  void t('header.health.statusWarn')
  void t('header.health.statusError')
  void t('header.health.statusUnknown')
  void t('header.health.statusUnavailable')
}

/**
 * Compact operational health indicator for the global header. Surfaces the
 * outcome of `/api/admin/doctor/summary` as a tiny dot + status word, with a
 * critical-issue counter when the platform is in WARN/ERROR state. Clicking
 * navigates to the full health page.
 *
 * The polling fetch is shared (via TanStack Query cache key) with the
 * dashboard `DoctorBanner`, so mounting this badge globally does not double
 * the request rate.
 */
export function HeaderHealthBadge() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const {
    summary,
    isLoading,
    isError,
    error,
    passed,
    total,
    criticalCount,
    generatedAt,
    effectiveStatus,
  } = useGlobalHealth()

  const intent = intentForStatus(isLoading, isError, effectiveStatus ?? summary?.status)
  const label = t(INTENT_LABEL_KEY[intent])
  const dotColor = INTENT_TOKEN[intent]

  // Tooltip composition: status-line + (when known) per-check progress + last update.
  const tooltipParts: string[] = [label]
  if (intent !== 'unknown' && intent !== 'unavailable' && total > 0) {
    tooltipParts.push(t('header.health.tooltipPassed', { passed, total }))
  }
  if (intent === 'unavailable') {
    const reason = getErrorMessage(error)
    if (reason) tooltipParts.push(reason)
  }
  if (generatedAt) {
    tooltipParts.push(
      t('header.health.tooltipUpdated', {
        time: formatRelativeTimeKo(generatedAt),
      }),
    )
  }
  tooltipParts.push(t('header.health.clickHint'))

  const tooltip = tooltipParts.join('\n')

  // Critical count badge appears for WARN and ERROR states only when we have
  // counts from the report. Falls back gracefully when the report query has
  // not finished yet.
  const showCount = (intent === 'warn' || intent === 'error') && criticalCount > 0

  // Compose the visible aria-label so screen readers announce the full status.
  const ariaLabelParts: string[] = [t('common.health'), label]
  if (showCount) {
    ariaLabelParts.push(
      t('header.health.tooltipPassed', { passed, total }),
    )
  }

  return (
    <button
      type="button"
      className={`header-health-badge header-health-badge--${intent}`}
      onClick={() => { void navigate('/health') }}
      aria-label={ariaLabelParts.join(' · ')}
      title={tooltip}
      data-status={intent}
    >
      <span
        className="header-health-badge__dot"
        style={{ background: dotColor }}
        aria-hidden="true"
      />
      <span className="header-health-badge__label">{label}</span>
      {showCount && (
        <span className="header-health-badge__count" aria-hidden="true">
          {criticalCount}
        </span>
      )}
    </button>
  )
}

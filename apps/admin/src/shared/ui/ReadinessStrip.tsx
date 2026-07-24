import { useTranslation } from 'react-i18next'
import type { OpsStatus } from '../lib/ops'
import { StatusBadge } from './StatusBadge'
import './ReadinessStrip.css'

export interface ReadinessCheck {
  id: string
  label: string
  status: OpsStatus
  description: string
}

interface ReadinessStripProps {
  checks: ReadinessCheck[]
  /** Optional override for the summary label. Defaults to the i18n key `common.readinessChecksTitle`. */
  summaryLabel?: string
}

/**
 * Collapsible readiness strip that consolidates per-signal PASS/WARN/FAIL rows
 * into a single panel. Defaults to collapsed when every check passes, and
 * expands automatically when any check reports WARN or FAIL so operators
 * immediately see the failure reason.
 */
export function ReadinessStrip({ checks, summaryLabel }: ReadinessStripProps) {
  const { t } = useTranslation()

  const hasIssue = checks.some((check) => check.status !== 'PASS')
  const warnCount = checks.filter((check) => check.status === 'WARN').length
  const failCount = checks.filter((check) => check.status === 'FAIL').length
  const overallStatus: OpsStatus = failCount > 0 ? 'FAIL' : warnCount > 0 ? 'WARN' : 'PASS'

  const title = summaryLabel ?? t('common.readinessChecksTitle', '준비 상태 점검')
  const translatedStatus = (status: OpsStatus) => t(`common.statuses.${status}`, {
    defaultValue: status,
  })

  return (
    <details className="readiness-strip" open={hasIssue}>
      <summary className="readiness-strip-summary">
        <span className="readiness-strip-chevron" aria-hidden="true" />
        <span className="readiness-strip-title">{title}</span>
        <span className="readiness-strip-meta">
          {t('common.readinessPassCount', '{{count}}/{{total}} 통과', {
            count: checks.length - warnCount - failCount,
            total: checks.length,
          })}
        </span>
        <StatusBadge status={overallStatus} label={translatedStatus(overallStatus)} />
      </summary>
      <ul className="readiness-strip-list" role="list">
        {checks.map((check) => (
          <li key={check.id} className="readiness-strip-row">
            <div className="readiness-strip-row-head">
              <span className="readiness-strip-row-label">{check.label}</span>
              <StatusBadge status={check.status} label={translatedStatus(check.status)} />
            </div>
            <p className="readiness-strip-row-desc">{check.description}</p>
          </li>
        ))}
      </ul>
    </details>
  )
}

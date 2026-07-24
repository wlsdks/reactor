import { useTranslation } from 'react-i18next'
import { useRelativeTime } from '../../../shared/lib'
import type { PlatformReadiness } from '../readiness'
import type { IssueCenterSnapshot } from '../../issues'

interface DashboardHealthBarProps {
  readiness: PlatformReadiness | null
  issueSnapshot: IssueCenterSnapshot | undefined
  mcpConnected: number
  mcpTotal: number
  groundedPercent: number
  updatedAt?: number | null
}

function getStatusColor(level: string | undefined): string {
  switch (level) {
    case 'GREEN': return 'var(--green)'
    case 'YELLOW': return 'var(--yellow)'
    case 'RED': return 'var(--red)'
    default: return 'var(--text-dim)'
  }
}

export function DashboardHealthBar({
  readiness,
  issueSnapshot,
  mcpConnected,
  mcpTotal,
  groundedPercent,
  updatedAt,
}: DashboardHealthBarProps) {
  const { t } = useTranslation()
  const relativeUpdated = useRelativeTime(updatedAt && updatedAt > 0 ? updatedAt : null)
  void issueSnapshot
  void mcpConnected
  void mcpTotal
  void groundedPercent

  return (
    <div className="health-bar" role="status" aria-live="polite">
      <span
        className="health-bar__dot"
        style={{ background: getStatusColor(readiness?.level) }}
        aria-hidden="true"
      />
      <div className="health-bar__copy">
        <strong>{readiness ? t(readiness.labelKey) : t('dashboard.healthBar.unknown')}</strong>
        {readiness && <span>{t(readiness.actionKey)}</span>}
      </div>
      {relativeUpdated && (
        <span className="health-bar__timestamp">
          {t('dashboard.healthBar.lastUpdated')} · {relativeUpdated}
        </span>
      )}
    </div>
  )
}

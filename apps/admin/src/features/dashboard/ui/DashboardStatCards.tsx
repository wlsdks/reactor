import { useTranslation } from 'react-i18next'
import { SkeletonTable } from '../../../shared/ui/Skeleton'
import { formatMetricValue } from '../../../shared/lib/formatters'
import type { IssueCenterSnapshot } from '../../issues'
import type { DashboardResponse } from '../types'

interface DashboardStatCardsProps {
  data: DashboardResponse
  issueSnapshot: IssueCenterSnapshot | undefined
  connectedCount: number
}

interface StatusFactProps {
  label: string
  value: string
  tone?: 'danger' | 'warning' | 'success'
}

function StatusFact({ label, value, tone }: StatusFactProps) {
  return (
    <span className={`dashboard-status-fact${tone ? ` is-${tone}` : ''}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </span>
  )
}

export function DashboardStatCards({ data, issueSnapshot, connectedCount }: DashboardStatCardsProps) {
  const { t } = useTranslation()
  const criticalCount = issueSnapshot?.criticalCount ?? 0
  const warningCount = issueSnapshot?.warningCount ?? 0
  const guardRejected = data.responseTrust.outputGuardRejected
  const groundedPercent = data.employeeValue?.groundedRatePercent ?? 0

  return (
    <section className="dashboard-status-summary" aria-labelledby="dashboard-status-summary-title">
      <header className="dashboard-status-summary__header">
        <div>
          <h2 id="dashboard-status-summary-title">{t('dashboard.statCards.title')}</h2>
          <p>{t('dashboard.statCards.description')}</p>
        </div>
      </header>

      <dl className="dashboard-status-table">
        <div className="dashboard-status-row">
          <dt>{t('dashboard.statCards.health')}</dt>
          <dd>
            <StatusFact label={t('dashboard.statCards.critical')} value={formatMetricValue(criticalCount)} tone={criticalCount > 0 ? 'danger' : undefined} />
            <StatusFact label={t('dashboard.statCards.warnings')} value={formatMetricValue(warningCount)} tone={warningCount > 0 ? 'warning' : undefined} />
            <StatusFact label={t('dashboard.statCards.rejected')} value={formatMetricValue(guardRejected)} tone={guardRejected > 0 ? 'danger' : undefined} />
          </dd>
        </div>
        <div className="dashboard-status-row">
          <dt>{t('dashboard.statCards.infrastructure')}</dt>
          <dd>
            <StatusFact label={t('dashboard.statCards.connected')} value={formatMetricValue(connectedCount)} tone={connectedCount > 0 ? 'success' : undefined} />
            <StatusFact label={t('dashboard.statCards.totalServers')} value={formatMetricValue(data.mcp.total)} />
            <StatusFact label={t('dashboard.statCards.runningJobs')} value={formatMetricValue(data.scheduler.runningJobs)} />
          </dd>
        </div>
        <div className="dashboard-status-row">
          <dt>{t('dashboard.statCards.quality')}</dt>
          <dd>
            <StatusFact label={t('dashboard.statCards.grounded')} value={`${groundedPercent}%`} />
            <StatusFact label={t('dashboard.statCards.observed')} value={formatMetricValue(data.employeeValue?.observedResponses ?? 0)} />
            <StatusFact label={t('dashboard.statCards.pending')} value={formatMetricValue(data.approvals.pendingCount)} />
          </dd>
        </div>
      </dl>
    </section>
  )
}

export function DashboardStatCardsSkeleton() {
  return <SkeletonTable rows={3} columns={4} className="dashboard-status-table--loading" />
}

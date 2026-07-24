import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { formatMetricValue } from '../../../shared/lib/formatters'
import type { IssueCenterSnapshot } from '../../issues'

interface DashboardActionCardsProps {
  issueSnapshot: IssueCenterSnapshot | undefined
  pendingApprovals: number
  guardRejected: number
  guardModified: number
}

export function DashboardActionCards({
  issueSnapshot,
  pendingApprovals,
  guardRejected,
  guardModified,
}: DashboardActionCardsProps) {
  const { t } = useTranslation()
  const criticalCount = issueSnapshot?.criticalCount ?? 0
  const criticalItems = (issueSnapshot?.items ?? [])
    .filter((item) => item.severity === 'critical')
    .slice(0, 3)
  const guardTotal = guardRejected + guardModified
  const outstandingSignalCount = criticalCount + pendingApprovals + guardTotal

  return (
    <section className="dashboard-priority" aria-labelledby="dashboard-priority-title">
      <div className="dashboard-priority__header">
        <h2 id="dashboard-priority-title" className="dashboard-priority__title">
          {t('dashboard.actions.priorityTitle')}
        </h2>
        <p className="dashboard-priority__summary">
          {t('dashboard.actions.prioritySummary', { count: outstandingSignalCount })}
        </p>
      </div>

      <ul className="dashboard-action-queue">
        {criticalCount > 0 && (
          <li className="dashboard-action-queue__item">
          <Link to="/issues" className="dashboard-action-row dashboard-action-row--critical">
            <span className="dashboard-action-row__dot" aria-hidden="true" />
            <div className="dashboard-action-row__copy">
              <h3>{t('dashboard.actions.criticalIssues')}</h3>
              <ul className="dashboard-action-row__issues">
                {criticalItems.map((issue) => (
                  <li key={issue.id}>{t(issue.title.key, issue.title.values)}</li>
                ))}
              </ul>
            </div>
            <strong className="dashboard-action-row__count">
              {formatMetricValue(criticalCount)}
            </strong>
            <ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />
          </Link>
          </li>
        )}

        {pendingApprovals > 0 && (
          <li className="dashboard-action-queue__item">
          <Link to="/approvals" className="dashboard-action-row dashboard-action-row--warning">
            <span className="dashboard-action-row__dot" aria-hidden="true" />
            <div className="dashboard-action-row__copy">
              <h3>{t('dashboard.actions.pendingApprovals')}</h3>
              <p>{t('dashboard.actions.pendingSummary', { count: pendingApprovals })}</p>
            </div>
            <strong className="dashboard-action-row__count">
              {formatMetricValue(pendingApprovals)}
            </strong>
            <ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />
          </Link>
          </li>
        )}

        {guardTotal > 0 && (
          <li className="dashboard-action-queue__item">
          <Link to="/safety-rules" className="dashboard-action-row dashboard-action-row--guard">
            <span className="dashboard-action-row__dot" aria-hidden="true" />
            <div className="dashboard-action-row__copy">
              <h3>{t('dashboard.actions.outputGuard')}</h3>
              <p className="dashboard-action-row__facts">
                <span>{t('dashboard.actions.guardRejected', { count: guardRejected })}</span>
                <span>{t('dashboard.actions.guardModified', { count: guardModified })}</span>
              </p>
            </div>
            <strong className="dashboard-action-row__count">
              {formatMetricValue(guardTotal)}
            </strong>
            <ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />
          </Link>
          </li>
        )}
      </ul>
    </section>
  )
}

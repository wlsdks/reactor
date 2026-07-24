import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { SkeletonTable } from '../../../shared/ui/Skeleton'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getUsageDaily } from '../../usage/api'
import { computeCostPeriodAggregates, percentDelta } from '../../usage/lib'

export const COST_ALERT_THRESHOLD_PERCENT = 25

function formatUsd(amount: number): string {
  if (!Number.isFinite(amount) || amount <= 0) return '$0.00'
  if (amount < 1) return `$${amount.toFixed(4)}`
  if (amount < 100) return `$${amount.toFixed(2)}`
  return `$${amount.toFixed(0)}`
}

function formatDelta(delta: number): string {
  const sign = delta > 0 ? '+' : ''
  return `${sign}${delta.toFixed(1)}%`
}

export function DashboardCostAlertPanel() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data: dailyTrend, isLoading } = useQuery({
    queryKey: queryKeys.usage.daily(60),
    queryFn: () => getUsageDaily(60),
  })

  if (isLoading || !dailyTrend) {
    return (
      <div className="dashboard-cost-alert" data-testid="dashboard-cost-alert-loading">
        <SkeletonTable rows={1} columns={3} />
      </div>
    )
  }

  const aggregates = computeCostPeriodAggregates(dailyTrend)
  const monthCost = aggregates.month.totalCostUsd
  const delta = percentDelta(monthCost, aggregates.priorMonth.totalCostUsd)
  const isAlert = delta > COST_ALERT_THRESHOLD_PERCENT

  return (
    <section
      className="dashboard-cost-alert"
      aria-label={t('dashboardPage.cost.regionLabel')}
      data-testid="dashboard-cost-alert"
      data-alert={isAlert ? 'true' : 'false'}
    >
      <header className="dashboard-cost-alert__header">
        <div>
          <h2>{t('dashboardPage.cost.title')}</h2>
          <p>{t('dashboardPage.cost.description')}</p>
        </div>
      </header>
      <button
        type="button"
        className="dashboard-cost-row"
        onClick={() => navigate('/usage')}
        aria-label={`${t('dashboardPage.cost.thisMonth')} ${formatUsd(monthCost)}`}
      >
        <span>{t('dashboardPage.cost.thisMonth')}</span>
        <strong>{formatUsd(monthCost)}</strong>
        <span className={isAlert ? 'dashboard-cost-row__delta is-warning' : 'dashboard-cost-row__delta'}>
          {formatDelta(delta)} · {t('dashboardPage.cost.vsPriorMonth')}
        </span>
        <ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />
      </button>
      {isAlert && (
        <p className="dashboard-cost-alert__warning" role="status" data-testid="dashboard-cost-alert-warning">
          {t('dashboardPage.cost.alert', { percent: Math.round(delta) })}
        </p>
      )}
    </section>
  )
}

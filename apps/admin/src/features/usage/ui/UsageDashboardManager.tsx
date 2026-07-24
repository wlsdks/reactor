import './UsageDashboardManager.css'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from 'recharts'
import { DataTable } from '../../../shared/ui/DataTable'
import { SkeletonChart, SkeletonTable } from '../../../shared/ui/Skeleton'
import { EmptyState } from '../../../shared/ui/EmptyState'
import { SectionErrorBoundary } from '../../../shared/ui/SectionErrorBoundary'
import { ChartTooltip } from '../../../shared/ui/ChartTooltip'
import { PageHeader } from '../../../shared/ui/PageHeader'
import { HelpHint } from '../../../shared/ui/HelpHint'
import { Tooltip } from '../../../shared/ui/Tooltip'
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  getAreaSeriesProps,
  paletteColor,
} from '../../../shared/ui/ChartConfig'
import type { Column } from '../../../shared/ui/DataTable'
import { formatNumber, formatCurrency } from '../../../shared/lib/formatters'
import { formatRelativeTimeKo } from '../../../shared/lib/formatRelativeTimeKo'
import { queryKeys } from '../../../shared/lib/queryKeys'
import type { UserUsageSummary, ModelUsageBreakdown } from '../types'
import { getUsersCost, getUsageDaily, getUsageByModel } from '../api'
import { buildCostTrendChartData } from '../lib'

function formatCost(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '$0.00'
  return formatCurrency(value, { minDecimals: 2 })
}

const DAYS_OPTIONS = [1, 7, 30, 90] as const

function readDays(value: string | null): number {
  const parsed = Number(value)
  return DAYS_OPTIONS.includes(parsed as (typeof DAYS_OPTIONS)[number]) ? parsed : 30
}

function displayUserId(userId: string, t: TFunction): string {
  if (userId === 'local-user') return t('usagePage.localUser')
  const normalized = userId.trim()
  const withoutPrefix = normalized.replace(/^(?:user|usr)[_-]?/i, '') || normalized
  const compact = withoutPrefix.length <= 7
    ? `#${withoutPrefix.toUpperCase()}`
    : `#${withoutPrefix.slice(0, 4).toUpperCase()}…${withoutPrefix.slice(-3).toUpperCase()}`
  return t('usagePage.anonymousUser', { id: compact })
}

function displayProvider(provider: string | null, t: TFunction): string | null {
  if (!provider) return null
  if (provider.toLowerCase() === 'ollama') return t('usagePage.providerLabels.ollama')
  if (provider.toLowerCase() === 'openai') return t('usagePage.providerLabels.openai')
  if (provider.toLowerCase() === 'anthropic') return t('usagePage.providerLabels.anthropic')
  return t('usagePage.providerLabels.unknown')
}

function displayModel(model: string, t: TFunction): string {
  const normalized = model.trim().toLowerCase().replace(/[_.:-]+/g, '')
  if (normalized.includes('gpt5mini')) return t('usagePage.modelLabels.gpt5Mini')
  if (normalized.includes('claudesonnet')) return t('usagePage.modelLabels.claudeSonnet')
  if (normalized.includes('claudehaiku')) return t('usagePage.modelLabels.claudeHaiku')
  if (normalized.includes('claudeopus')) return t('usagePage.modelLabels.claudeOpus')
  if (normalized.includes('gemma')) return t('usagePage.modelLabels.gemma')
  return t('usagePage.modelLabels.unknown')
}

export function UsageDashboardManager() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const days = readDays(searchParams.get('days'))

  const usersQuery = useQuery({
    queryKey: queryKeys.usage.dashboard(days),
    queryFn: () => getUsersCost(days, 100),
  })
  const dailyQuery = useQuery({
    queryKey: queryKeys.usage.daily(days),
    queryFn: () => getUsageDaily(days),
  })
  const modelsQuery = useQuery({
    queryKey: queryKeys.usage.byModel(days),
    queryFn: () => getUsageByModel(days),
  })

  const users = usersQuery.data ?? []
  const dailyTrend = dailyQuery.data ?? []
  const byModel = modelsQuery.data ?? []
  const queries = [usersQuery, dailyQuery, modelsQuery]
  const isLoading = queries.some((query) => query.isLoading)
  const failedCount = queries.filter((query) => query.isError).length
  const allFailed = failedCount === queries.length

  const totalCost = users.reduce((sum, user) => sum + user.totalCostUsd, 0)
  const totalTokens = users.reduce((sum, user) => sum + user.totalTokens, 0)
  const totalSessions = users.reduce((sum, user) => sum + user.sessionCount, 0)
  const chartData = buildCostTrendChartData(dailyTrend)
  const hasBillableCost = chartData.some((point) => point.cost > 0)

  const userColumns: Column<UserUsageSummary>[] = [
    {
      key: 'userId',
      header: t('usagePage.userId'),
      responsivePriority: 1,
      render: (row) => (
        <Tooltip content={row.userId}>
          <span className="usage-user-name">{displayUserId(row.userId, t)}</span>
        </Tooltip>
      ),
      sortable: true,
    },
    {
      key: 'sessionCount',
      header: t('usagePage.sessions'),
      responsivePriority: 1,
      render: (row) => <span className="data-mono">{formatNumber(row.sessionCount)}</span>,
      sortable: true,
    },
    {
      key: 'totalTokens',
      header: (
        <span className="text-with-hint">
          <span>{t('usagePage.tokens')}</span>
          <HelpHint title={t('usagePage.tokens')} label={t('usagePage.tokensHelp')} />
        </span>
      ),
      responsivePriority: 1,
      render: (row) => <span className="data-mono">{formatNumber(row.totalTokens)}</span>,
      sortable: true,
    },
    {
      key: 'totalCostUsd',
      header: t('usagePage.cost'),
      responsivePriority: 1,
      render: (row) => <span className="data-mono">{formatCost(row.totalCostUsd)}</span>,
      sortable: true,
    },
    {
      key: 'avgLatencyMs',
      header: t('usagePage.avgResponseTime'),
      responsivePriority: 2,
      render: (row) => <span className="data-mono">{formatNumber(row.avgLatencyMs)}ms</span>,
      sortable: true,
    },
    {
      key: 'lastActivity',
      header: t('usagePage.lastActive'),
      responsivePriority: 2,
      render: (row) => row.lastActivity ? formatRelativeTimeKo(row.lastActivity) : '-',
      sortable: true,
    },
  ]

  const modelColumns: Column<ModelUsageBreakdown>[] = [
    {
      key: 'model',
      header: t('usagePage.model'),
      responsivePriority: 1,
      render: (row) => {
        const provider = displayProvider(row.provider, t)
        return (
          <Tooltip content={[row.provider, row.model].filter(Boolean).join(' · ')}>
            <div className="usage-model-name">
              <span>{displayModel(row.model, t)}</span>
              {provider ? <span>{provider}</span> : null}
            </div>
          </Tooltip>
        )
      },
    },
    {
      key: 'callCount',
      header: t('usagePage.requests'),
      responsivePriority: 1,
      render: (row) => <span className="data-mono">{formatNumber(row.callCount)}</span>,
      sortable: true,
    },
    {
      key: 'promptTokens',
      header: t('usagePage.inputTokens'),
      responsivePriority: 2,
      render: (row) => <span className="data-mono">{formatNumber(row.promptTokens)}</span>,
    },
    {
      key: 'completionTokens',
      header: t('usagePage.outputTokens'),
      responsivePriority: 2,
      render: (row) => <span className="data-mono">{formatNumber(row.completionTokens)}</span>,
    },
    {
      key: 'totalCostUsd',
      header: t('usagePage.cost'),
      responsivePriority: 1,
      render: (row) => <span className="data-mono">{formatCost(row.totalCostUsd)}</span>,
      sortable: true,
    },
    {
      key: 'lastActivity',
      header: t('usagePage.lastActive'),
      responsivePriority: 3,
      render: (row) => row.lastActivity ? formatRelativeTimeKo(row.lastActivity) : '-',
    },
  ]

  const retryAll = () => {
    void Promise.all(queries.map((query) => query.refetch()))
  }

  return (
    <div className="page usage-dashboard">
      <PageHeader
        title={t('usagePage.title')}
        description={t('usagePage.description')}
        actions={(
          <select
            className="form-select usage-dashboard__period"
            value={days}
            onChange={(event) => {
              const next = new URLSearchParams(searchParams)
              next.set('days', event.target.value)
              setSearchParams(next, { replace: true })
            }}
            aria-label={t('usagePage.daysLabel')}
          >
            {DAYS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {t('tracesPage.filters.lastNDays', { count: option })}
              </option>
            ))}
          </select>
        )}
      />

      {isLoading ? (
        <div className="usage-dashboard__loading">
          <SkeletonChart height={200} />
          <SkeletonTable rows={6} columns={6} />
        </div>
      ) : allFailed ? (
        <EmptyState
          message={t('usagePage.loadErrorTitle')}
          description={t('usagePage.loadErrorDescription')}
          actionLabel={t('common.retry')}
          onAction={retryAll}
        />
      ) : (
        <>
          {failedCount > 0 && (
            <div className="usage-dashboard__notice" role="status">
              <div>
                <strong>{t('usagePage.partialErrorTitle')}</strong>
                <span>{t('usagePage.partialErrorDescription', { count: failedCount })}</span>
              </div>
              <button className="btn btn-secondary btn-sm" type="button" onClick={retryAll}>
                {t('common.retry')}
              </button>
            </div>
          )}

          <dl className="usage-dashboard__summary" role="region" aria-label={t('usagePage.summaryStats')}>
            <div className="usage-dashboard__summary-primary">
              <dt>{t('usagePage.totalCostLabel')}</dt>
              <dd>{usersQuery.isError ? '-' : formatCost(totalCost)}</dd>
              <span>{t('usagePage.totalCostHint', { count: days })}</span>
            </div>
            <div><dt>{t('usagePage.totalUsers')}</dt><dd>{usersQuery.isError ? '-' : formatNumber(users.length)}</dd></div>
            <div><dt>{t('usagePage.totalSessions')}</dt><dd>{usersQuery.isError ? '-' : formatNumber(totalSessions)}</dd></div>
            <div><dt>{t('usagePage.totalTokensLabel')}</dt><dd>{usersQuery.isError ? '-' : formatNumber(totalTokens)}</dd></div>
          </dl>

          <SectionErrorBoundary name="usage-trend-chart">
            <section className="usage-dashboard__section">
              <div className="usage-dashboard__section-heading">
                <div><h2>{t('usagePage.costTrend')}</h2><p>{t('usagePage.costTrendDescription')}</p></div>
              </div>
              {dailyQuery.isError ? (
                <EmptyState message={t('usagePage.trendLoadError')} />
              ) : chartData.length > 1 && hasBillableCost ? (
                <div className="usage-dashboard__chart">
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                      <defs><linearGradient id="usageTrendGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={paletteColor(0)} stopOpacity={0.22} /><stop offset="95%" stopColor={paletteColor(0)} stopOpacity={0} /></linearGradient></defs>
                      <CartesianGrid {...CHART_GRID_STYLE} />
                      <XAxis dataKey="date" tick={CHART_AXIS_STYLE.tick} axisLine={false} tickLine={false} />
                      <YAxis tick={CHART_AXIS_STYLE.tick} axisLine={false} tickLine={false} tickFormatter={(value: number) => `$${value}`} />
                      <RechartsTooltip content={<ChartTooltip formatValue={formatCost} />} />
                      <Area type="monotone" dataKey="cost" name={t('usagePage.cost')} {...getAreaSeriesProps(0)} fill="url(#usageTrendGrad)" animationDuration={500} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : chartData.length > 1 ? (
                <div className="usage-dashboard__no-cost" role="status">
                  <strong>{t('usagePage.noCostTitle')}</strong>
                  <span>{t('usagePage.noCostDescription')}</span>
                </div>
              ) : (
                <EmptyState message={t('usagePage.insufficientTrend')} description={t('usagePage.insufficientTrendDescription')} />
              )}
            </section>
          </SectionErrorBoundary>

          <section className="usage-dashboard__section">
            <div className="usage-dashboard__section-heading"><div><h2>{t('usagePage.topUsers')}</h2><p>{t('usagePage.usersDescription')}</p></div></div>
            {usersQuery.isError ? <EmptyState message={t('usagePage.usersLoadError')} /> : users.length > 0 ? (
              <DataTable
                columns={userColumns}
                data={users}
                keyFn={(row) => row.userId}
                tableId="usage-users"
                urlStateKey="usage-users"
                onRowClick={(row) => void navigate(`/sessions/users/${encodeURIComponent(row.userId)}`)}
              />
            ) : <EmptyState message={t('usagePage.noUsers')} description={t('usagePage.noUsersDescription')} />}
          </section>

          <section className="usage-dashboard__section">
            <div className="usage-dashboard__section-heading"><div><h2>{t('usagePage.byModel')}</h2><p>{t('usagePage.modelsDescription')}</p></div></div>
            {modelsQuery.isError ? <EmptyState message={t('usagePage.modelsLoadError')} /> : byModel.length > 0 ? (
              <DataTable columns={modelColumns} data={byModel} keyFn={(row) => `${row.provider ?? 'unknown'}:${row.model}`} tableId="usage-models" urlStateKey="usage-models" />
            ) : <EmptyState message={t('usagePage.noByModel')} />}
          </section>
        </>
      )}
    </div>
  )
}

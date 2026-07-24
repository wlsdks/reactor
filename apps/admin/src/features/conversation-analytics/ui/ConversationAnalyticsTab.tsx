import './ConversationAnalyticsTab.css'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import {
  DataTable,
  SkeletonCard,
  SkeletonChart,
  SkeletonTable,
  ChartTooltip,
  EmptyState,
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  getAreaSeriesProps,
  paletteColor,
  HelpHint,
} from '../../../shared/ui'
import type { Column } from '../../../shared/ui'
import { BucketDistribution } from '../../../shared/ui/BucketDistribution'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { formatNumber, formatPercent } from '../../../shared/lib/formatters'
import { getConversationsByChannel, getFailurePatterns, getLatencyDistribution } from '../api'
import type { FailurePattern } from '../types'

const DAYS_OPTIONS = [7, 30, 90] as const

const FAILURE_LABEL_KEYS: Record<string, string> = {
  LLM_TIMEOUT: 'conversationAnalyticsTab.failureTypes.llmTimeout',
  CONTEXT_OVERFLOW: 'conversationAnalyticsTab.failureTypes.contextOverflow',
  TOOL_EXECUTION_ERROR: 'conversationAnalyticsTab.failureTypes.toolExecution',
  GUARD_BLOCKED: 'conversationAnalyticsTab.failureTypes.safetyBlocked',
}

export function ConversationAnalyticsTab() {
  const { t } = useTranslation()
  const [days, setDays] = useState<number>(30)

  const channelQuery = useQuery({
    queryKey: queryKeys.conversationAnalytics.byChannel(days),
    queryFn: () => getConversationsByChannel(days),
  })

  const failuresQuery = useQuery({
    queryKey: queryKeys.conversationAnalytics.failurePatterns(days),
    queryFn: () => getFailurePatterns(days),
  })

  const latencyQuery = useQuery({
    queryKey: queryKeys.conversationAnalytics.latencyDistribution(days),
    queryFn: () => getLatencyDistribution(days),
  })

  const channelStats = channelQuery.data ?? []
  const failures = failuresQuery.data ?? []
  const latencyBuckets = latencyQuery.data ?? []
  const queries = [channelQuery, failuresQuery, latencyQuery]
  const isLoading = queries.some((query) => query.isLoading)
  const failedCount = queries.filter((query) => query.isError).length
  const allFailed = failedCount === queries.length

  const retryAll = () => {
    void Promise.all(queries.map((query) => query.refetch()))
  }

  const totalConversations = channelStats.reduce((sum, c) => sum + c.total, 0)
  const totalSuccess = channelStats.reduce((sum, c) => sum + c.success, 0)
  const totalFailure = channelStats.reduce((sum, c) => sum + c.failure, 0)
  const overallSuccessRateLabel =
    totalConversations > 0 ? formatPercent(totalSuccess / totalConversations) : '0.0%'
  const avgLatency =
    channelStats.length > 0
      ? Math.round(channelStats.reduce((sum, c) => sum + c.avgDurationMs, 0) / channelStats.length)
      : 0

  const totalFailureCount = failures.reduce((sum, f) => sum + f.count, 0)

  const failureColumns: Column<FailurePattern>[] = [
    {
      key: 'errorClass',
      header: t('conversationAnalyticsTab.errorClass'),
      width: '35%',
      render: (row) => (
        <span className="conversation-analytics-tab__failure-reason">
          <span>{t(FAILURE_LABEL_KEYS[row.errorClass.toUpperCase()] ?? 'conversationAnalyticsTab.failureTypes.unknown')}</span>
          <HelpHint
            title={t('conversationAnalyticsTab.technicalCode')}
            label={t('conversationAnalyticsTab.technicalCodeDescription', {
              code: row.errorClass,
            })}
          />
        </span>
      ),
    },
    {
      key: 'count',
      header: t('conversationAnalyticsTab.count'),
      width: '20%',
      render: (row) => <span className="data-mono">{formatNumber(row.count)}</span>,
    },
    {
      key: 'pct',
      header: t('conversationAnalyticsTab.pctOfTotal'),
      width: '20%',
      render: (row) => (
        <span className="data-mono">
          {totalFailureCount > 0 ? formatPercent(row.count / totalFailureCount) : '0.0%'}
        </span>
      ),
    },
    {
      key: 'latest',
      header: t('conversationAnalyticsTab.latest'),
      width: '25%',
      render: (row) => row.latest,
    },
  ]

  if (isLoading) {
    return (
      <div className="conversation-analytics-tab">
        <div className="stat-grid">
          <SkeletonCard height={92} />
          <SkeletonCard height={92} />
          <SkeletonCard height={92} />
          <SkeletonCard height={92} />
        </div>
        <div style={{ marginTop: 'var(--space-4)' }}>
          <SkeletonChart height={220} />
        </div>
        <div className="detail-panel detail-panel--compact" style={{ marginTop: 'var(--space-4)' }}>
          <SkeletonTable rows={5} columns={4} />
        </div>
      </div>
    )
  }

  // 대화 수집이 0 이고 실패/지연 데이터도 전무한 상태 — 빈 상태 안내로 전환해
  // 모든 stat 카드와 차트가 "0" 또는 "데이터 없음"으로 도배되는 혼란 방지.
  const hasAnyData =
    totalConversations > 0 || failures.length > 0 || latencyBuckets.length > 0

  return (
    <div className="conversation-analytics-tab">
      <div className="conversation-analytics-tab__header">
        <div>
          <h2>{t('conversationAnalyticsTab.title')}</h2>
          <p>{t('conversationAnalyticsTab.description')}</p>
        </div>
        <div className="date-range-presets">
          {DAYS_OPTIONS.map((d) => (
            <button
              key={d}
              type="button"
              className={`btn btn-sm btn-secondary ${days === d ? 'active-filter' : ''}`}
              onClick={() => setDays(d)}
            >
              {t('tracesPage.filters.lastNDays', { count: d })}
            </button>
          ))}
        </div>
      </div>

      {allFailed ? (
        <EmptyState
          message={t('conversationAnalyticsTab.loadErrorTitle')}
          description={t('conversationAnalyticsTab.loadErrorDescription')}
          actionLabel={t('common.retry')}
          onAction={retryAll}
        />
      ) : !hasAnyData && failedCount > 0 ? (
        <EmptyState
          message={t('conversationAnalyticsTab.partialErrorTitle')}
          description={t('conversationAnalyticsTab.partialErrorDescription', { count: failedCount })}
          actionLabel={t('common.retry')}
          onAction={retryAll}
        />
      ) : !hasAnyData ? (
        <EmptyState
          message={t('conversationAnalyticsTab.emptyTitle')}
          description={t('conversationAnalyticsTab.emptyDescription')}
        />
      ) : (
        <>
          {failedCount > 0 && (
            <div className="conversation-analytics-tab__notice" role="status">
              <div>
                <strong>{t('conversationAnalyticsTab.partialErrorTitle')}</strong>
                <span>{t('conversationAnalyticsTab.partialErrorDescription', { count: failedCount })}</span>
              </div>
              <button className="btn btn-secondary btn-sm" type="button" onClick={retryAll}>
                {t('common.retry')}
              </button>
            </div>
          )}

          <dl className="conversation-analytics-tab__summary" aria-label={t('conversationAnalyticsTab.summaryLabel')}>
            <div className="conversation-analytics-tab__summary-primary">
              <dt>{t('conversationAnalyticsTab.successRate')}</dt>
              <dd>{overallSuccessRateLabel}</dd>
              <span>{t('conversationAnalyticsTab.completedHint')}</span>
            </div>
            <div><dt>{t('conversationAnalyticsTab.totalConversations')}</dt><dd>{formatNumber(totalConversations)}</dd></div>
            <div><dt>{t('conversationAnalyticsTab.avgLatency')}</dt><dd>{`${avgLatency}ms`}</dd></div>
            <div><dt>{t('conversationAnalyticsTab.failures')}</dt><dd>{formatNumber(totalFailure)}</dd></div>
          </dl>

          <section className="conversation-analytics-tab__section" aria-labelledby="conversation-channel-trend">
            <div className="conversation-analytics-tab__section-heading">
              <h3 id="conversation-channel-trend">{t('conversationAnalyticsTab.channelTrend')}</h3>
              <p>{t('conversationAnalyticsTab.channelTrendDescription')}</p>
            </div>
            {channelStats.length > 1 ? (
              <div className="conversation-analytics-tab__chart">
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={channelStats} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                    <defs>
                      <linearGradient id="convSuccessGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={paletteColor(1)} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={paletteColor(1)} stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="convFailureGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={paletteColor(4)} stopOpacity={0.2} />
                        <stop offset="95%" stopColor={paletteColor(4)} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid {...CHART_GRID_STYLE} />
                    <XAxis dataKey="channel" tick={CHART_AXIS_STYLE.tick} axisLine={false} tickLine={false} />
                    <YAxis tick={CHART_AXIS_STYLE.tick} axisLine={false} tickLine={false} />
                    <Tooltip content={<ChartTooltip />} />
                    <Area type="monotone" dataKey="success" name={t('conversationAnalyticsTab.success')} {...getAreaSeriesProps(1)} fill="url(#convSuccessGrad)" animationDuration={500} />
                    <Area type="monotone" dataKey="failure" name={t('conversationAnalyticsTab.failure')} {...getAreaSeriesProps(4)} fill="url(#convFailureGrad)" animationDuration={500} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="conversation-analytics-tab__empty-note">{t('conversationAnalyticsTab.channelTrendEmpty')}</p>
            )}
          </section>

          {latencyBuckets.length > 0 && (
            <section
              className="conversation-analytics-tab__section"
              aria-label={t('conversationAnalyticsTab.latencyDistribution')}
            >
              <BucketDistribution
                buckets={latencyBuckets.map((b) => ({ label: b.bucket, count: b.count }))}
                title={t('conversationAnalyticsTab.latencyDistribution')}
              />
            </section>
          )}

          {failures.length > 0 && (
            <section className="conversation-analytics-tab__section" aria-labelledby="conversation-failure-patterns">
              <div className="conversation-analytics-tab__section-heading">
                <h3 id="conversation-failure-patterns">{t('conversationAnalyticsTab.failurePatterns')}</h3>
                <p>{t('conversationAnalyticsTab.failurePatternsDescription')}</p>
              </div>
              <DataTable columns={failureColumns} data={failures} keyFn={(row) => row.errorClass} />
            </section>
          )}
        </>
      )}
    </div>
  )
}

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  ChartTooltip,
  DataTable,
  EmptyState,
  paletteColor,
  SkeletonChart,
  SkeletonTable,
} from '../../../shared/ui'
import type { Column } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { formatNumber } from '../../../shared/lib/formatters'
import { getRagStatus, getRagByChannel } from '../api'
import type { RagChannelStats } from '../types'
import './rag-analytics.css'

const DAYS_OPTIONS = [7, 30] as const

export function RagAnalyticsTab() {
  const { t } = useTranslation()
  const [days, setDays] = useState<number>(30)

  const { data: statuses = [], isLoading: loadingStatus } = useQuery({
    queryKey: queryKeys.ragAnalytics.status(),
    queryFn: getRagStatus,
  })

  const { data: byChannel = [], isLoading: loadingChannel } = useQuery({
    queryKey: queryKeys.ragAnalytics.byChannel(days),
    queryFn: () => getRagByChannel(days),
  })

  const pendingCount = statuses.find((status) => status.status === 'PENDING')?.count ?? 0
  const ingestedCount = statuses.find((status) => status.status === 'INGESTED')?.count ?? 0
  const rejectedCount = statuses.find((status) => status.status === 'REJECTED')?.count ?? 0
  const totalCount = pendingCount + ingestedCount + rejectedCount

  const channelColumns: Column<RagChannelStats>[] = [
    {
      key: 'channel',
      header: t('ragAnalyticsTab.channel'),
      width: '28%',
      responsivePriority: 1,
      render: (row) => <span className="rag-analytics-channel-name">{row.channel}</span>,
    },
    {
      key: 'candidateCount',
      header: t('ragAnalyticsTab.total'),
      width: '18%',
      responsivePriority: 2,
      render: (row) => formatNumber(row.candidateCount),
    },
    {
      key: 'ingested',
      header: t('ragAnalyticsTab.knowledgeSaved'),
      width: '18%',
      responsivePriority: 1,
      render: (row) => formatNumber(row.ingested),
    },
    {
      key: 'pending',
      header: t('ragAnalyticsTab.reviewPending'),
      width: '18%',
      responsivePriority: 1,
      render: (row) => formatNumber(row.pending),
    },
    {
      key: 'rejected',
      header: t('ragAnalyticsTab.excluded'),
      width: '18%',
      responsivePriority: 2,
      render: (row) => formatNumber(row.rejected),
    },
  ]

  if (loadingStatus || loadingChannel) {
    return (
      <div className="rag-analytics-workspace">
        <div className="rag-analytics-loading-summary" />
        <div className="rag-analytics-loading-chart"><SkeletonChart height={240} /></div>
        <SkeletonTable rows={5} columns={5} />
      </div>
    )
  }

  return (
    <div className="rag-analytics-workspace">
      <header className="rag-analytics-header">
        <div>
          <h2>{t('ragAnalyticsTab.title')}</h2>
          <p>{t('ragAnalyticsTab.description')}</p>
        </div>
        <div className="rag-analytics-range" aria-label={t('ragAnalyticsTab.periodLabel')}>
          {DAYS_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              className={days === option ? 'is-active' : ''}
              aria-pressed={days === option}
              onClick={() => setDays(option)}
            >
              {t('tracesPage.filters.lastNDays', { count: option })}
            </button>
          ))}
        </div>
      </header>

      <dl className="rag-analytics-summary" aria-label={t('ragAnalyticsTab.summaryLabel')}>
        <div><dt>{t('ragAnalyticsTab.total')}</dt><dd>{formatNumber(totalCount)}</dd></div>
        <div><dt>{t('ragAnalyticsTab.knowledgeSaved')}</dt><dd>{formatNumber(ingestedCount)}</dd></div>
        <div><dt>{t('ragAnalyticsTab.reviewPending')}</dt><dd>{formatNumber(pendingCount)}</dd></div>
        <div><dt>{t('ragAnalyticsTab.excluded')}</dt><dd>{formatNumber(rejectedCount)}</dd></div>
      </dl>

      <section className="rag-analytics-surface" aria-labelledby="rag-analytics-channel-title">
        <div className="rag-analytics-surface__heading">
          <div>
            <h3 id="rag-analytics-channel-title">{t('ragAnalyticsTab.channelComparison')}</h3>
            <p>{t('ragAnalyticsTab.channelComparisonDescription', { count: days })}</p>
          </div>
        </div>

        {byChannel.length === 0 ? (
          <EmptyState
            message={t('ragAnalyticsTab.emptyTitle')}
            description={t('ragAnalyticsTab.emptyDescription')}
          />
        ) : (
          <>
            <div className="rag-analytics-chart">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={byChannel} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
                  <CartesianGrid {...CHART_GRID_STYLE} vertical={false} />
                  <XAxis dataKey="channel" tick={CHART_AXIS_STYLE.tick} axisLine={false} tickLine={false} />
                  <YAxis tick={CHART_AXIS_STYLE.tick} axisLine={false} tickLine={false} />
                  <Tooltip content={<ChartTooltip />} />
                  <Legend />
                  <Bar
                    dataKey="ingested"
                    name={t('ragAnalyticsTab.knowledgeSaved')}
                    fill={paletteColor(1)}
                    radius={[3, 3, 0, 0]}
                  />
                  <Bar
                    dataKey="pending"
                    name={t('ragAnalyticsTab.reviewPending')}
                    fill={paletteColor(3)}
                    radius={[3, 3, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="rag-analytics-table">
              <h4>{t('ragAnalyticsTab.byChannel')}</h4>
              <DataTable
                tableId="document-rag-analytics-by-channel"
                columns={channelColumns}
                data={byChannel}
                keyFn={(row) => row.channel}
              />
            </div>
          </>
        )}
      </section>
    </div>
  )
}

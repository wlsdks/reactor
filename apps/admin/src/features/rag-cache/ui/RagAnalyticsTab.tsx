import type { TFunction } from 'i18next'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  ChartTooltip,
  paletteColor,
  SkeletonCard,
  SkeletonChart,
} from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { formatDateTimeCompact, formatNumber } from '../../../shared/lib/formatters'
import * as ragCacheApi from '../api'
import type { RagChannelStat, RagStatusStat } from '../types'

interface StatusSummary {
  count: number
  latestCaptured: string | null
}

function summarizeStatus(stats: RagStatusStat[], status: string): StatusSummary {
  let count = 0
  let latestCaptured: string | null = null
  let latestCapturedMs = Number.NEGATIVE_INFINITY

  for (const stat of stats) {
    if (stat.status?.toUpperCase() !== status) continue
    count += stat.count ?? 0

    if (!stat.latestCaptured) continue
    const capturedMs = new Date(stat.latestCaptured).getTime()
    if (Number.isNaN(capturedMs) || capturedMs <= latestCapturedMs) continue
    latestCaptured = stat.latestCaptured
    latestCapturedMs = capturedMs
  }

  return { count, latestCaptured }
}

function latestCapturedLabel(
  latestCaptured: string | null,
  t: TFunction,
): string {
  const formatted = formatDateTimeCompact(latestCaptured)
  return formatted
    ? t('ragCachePage.analytics.latestCaptured', { time: formatted })
    : t('ragCachePage.analytics.latestCapturedMissing')
}

function computeApprovalRate(row: RagChannelStat): number {
  const total = row.pendingCount + row.approvedCount + row.rejectedCount
  if (total === 0) return 0
  return Math.round((row.approvedCount / total) * 100)
}

export function RagAnalyticsTab() {
  const { t } = useTranslation()

  const { data: statusStats = [], isLoading: loadingStatus } = useQuery({
    queryKey: queryKeys.ragCache.analyticsStatus(),
    queryFn: ragCacheApi.getRagStatusStats,
  })

  const { data: channelStats = [], isLoading: loadingChannel } = useQuery({
    queryKey: queryKeys.ragCache.analyticsByChannel(),
    queryFn: ragCacheApi.getRagChannelStats,
  })

  if (loadingStatus || loadingChannel) {
    return (
      <div>
        <div className="stat-row">
          <SkeletonCard height={92} />
          <SkeletonCard height={92} />
          <SkeletonCard height={92} />
        </div>
        <div className="detail-panel detail-panel--compact" style={{ marginTop: 'var(--space-4)' }}>
          <SkeletonChart height={320} />
        </div>
      </div>
    )
  }

  const pending = summarizeStatus(statusStats, 'PENDING')
  const approved = summarizeStatus(statusStats, 'APPROVED')
  const rejected = summarizeStatus(statusStats, 'REJECTED')
  const hasAnyData = statusStats.length > 0 || channelStats.length > 0

  const chartData = channelStats.map((row) => ({
    channel: row.channel,
    approvalRate: computeApprovalRate(row),
    approved: row.approvedCount,
    pending: row.pendingCount,
    rejected: row.rejectedCount,
  }))

  return (
    <div>
      <div className="rag-analytics-header">
        <h2 className="section-title">{t('ragCachePage.analytics.title')}</h2>
        <p>{t('ragCachePage.analytics.description')}</p>
      </div>

      <dl className="rag-summary-list">
        <div>
          <dt>{t('ragCachePage.analytics.totalPending')}</dt>
          <dd><strong>{formatNumber(pending.count)}</strong><span>{latestCapturedLabel(pending.latestCaptured, t)}</span></dd>
        </div>
        <div>
          <dt>{t('ragCachePage.analytics.totalApproved')}</dt>
          <dd><strong>{formatNumber(approved.count)}</strong><span>{latestCapturedLabel(approved.latestCaptured, t)}</span></dd>
        </div>
        <div>
          <dt>{t('ragCachePage.analytics.totalRejected')}</dt>
          <dd><strong>{formatNumber(rejected.count)}</strong><span>{latestCapturedLabel(rejected.latestCaptured, t)}</span></dd>
        </div>
      </dl>

      <section className="rag-analytics-channel">
        <h2 className="section-title">{t('ragCachePage.analytics.byChannel')}</h2>
        {!hasAnyData || chartData.length === 0 ? (
          <div className="rag-inline-state">
            <div>
              <strong>{t('ragCachePage.analytics.empty')}</strong>
              <p>{t('ragCachePage.analytics.emptyDesc')}</p>
            </div>
          </div>
        ) : (
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <BarChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: -16 }}>
                <CartesianGrid {...CHART_GRID_STYLE} />
                <XAxis
                  dataKey="channel"
                  tick={CHART_AXIS_STYLE.tick}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={CHART_AXIS_STYLE.tick}
                  axisLine={false}
                  tickLine={false}
                  unit="%"
                  domain={[0, 100]}
                />
                <Tooltip content={<ChartTooltip />} />
                <Legend />
                <Bar
                  dataKey="approvalRate"
                  name={t('ragCachePage.analytics.approvalRate')}
                  fill={paletteColor(2)}
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>
    </div>
  )
}

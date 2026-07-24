import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
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
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  ChartTooltip,
  DataTable,
  getAreaSeriesProps,
  paletteColor,
  ReleaseWorkflowBacklink,
  SkeletonCard,
  SkeletonChart,
  SkeletonTable,
  StatCard,
} from '../../../shared/ui'
import type { Column } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { formatNumber } from '../../../shared/lib/formatters'
import {
  RELEASE_SLACK_GATEWAY_PATH,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../../shared/releaseWorkflow'
import { getSlackChannels, getSlackDaily } from '../api'
import type { SlackChannelStats } from '../types'

const DAYS_OPTIONS = [7, 30, 90] as const

export function SlackActivityTab() {
  const { t } = useTranslation()
  const [days, setDays] = useState<number>(30)

  const { data: channels = [], isLoading: loadingChannels } = useQuery({
    queryKey: queryKeys.slackActivity.channels(days),
    queryFn: () => getSlackChannels(days),
  })

  const { data: daily = [], isLoading: loadingDaily } = useQuery({
    queryKey: queryKeys.slackActivity.daily(days),
    queryFn: () => getSlackDaily(days),
  })

  const isLoading = loadingChannels || loadingDaily

  const totalSessions = channels.reduce((sum, c) => sum + c.sessionCount, 0)
  const totalUniqueUsers = channels.reduce((sum, c) => sum + c.uniqueUsers, 0)
  const totalTokens = channels.reduce((sum, c) => sum + c.totalTokens, 0)
  const avgLatency =
    channels.length > 0
      ? Math.round(channels.reduce((sum, c) => sum + c.avgLatencyMs, 0) / channels.length)
      : 0

  const columns: Column<SlackChannelStats>[] = [
    {
      key: 'channel',
      header: t('slackActivityTab.channel'),
      width: '20%',
      render: (row) => row.channel,
    },
    {
      key: 'sessionCount',
      header: t('slackActivityTab.sessions'),
      width: '15%',
      render: (row) => <span className="data-mono">{formatNumber(row.sessionCount)}</span>,
    },
    {
      key: 'uniqueUsers',
      header: t('slackActivityTab.uniqueUsers'),
      width: '15%',
      render: (row) => <span className="data-mono">{formatNumber(row.uniqueUsers)}</span>,
    },
    {
      key: 'totalTokens',
      header: t('slackActivityTab.tokens'),
      width: '15%',
      render: (row) => <span className="data-mono">{formatNumber(row.totalTokens)}</span>,
    },
    {
      key: 'totalCostUsd',
      header: t('slackActivityTab.cost'),
      width: '15%',
      render: (row) => <span className="data-mono">${row.totalCostUsd.toFixed(2)}</span>,
    },
    {
      key: 'avgLatencyMs',
      header: t('slackActivityTab.avgLatency'),
      width: '20%',
      render: (row) => <span className="data-mono">{Math.round(row.avgLatencyMs)}ms</span>,
    },
  ]

  if (isLoading) {
    return (
      <div className="slack-activity-tab">
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
          <SkeletonTable rows={6} columns={6} />
        </div>
      </div>
    )
  }

  return (
    <div className="slack-activity-tab">
      <div className="slack-activity-tab__header">
        <h3 className="section-title">{t('slackActivityTab.title')}</h3>
        <div className="date-range-presets">
          <ReleaseWorkflowBacklink stepId="integrations" />
          <Link className="btn btn-sm btn-secondary" to={RELEASE_SLACK_GATEWAY_PATH}>
            <span className="data-mono">{RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations}</span>
            {t('integrationsPage.releaseSmoke.workflowSlack')}
          </Link>
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

      <div className="stat-grid">
        <StatCard label={t('slackActivityTab.totalSessions')} value={formatNumber(totalSessions)} />
        <StatCard label={t('slackActivityTab.uniqueUsers')} value={formatNumber(totalUniqueUsers)} />
        <StatCard label={t('slackActivityTab.totalTokens')} value={formatNumber(totalTokens)} />
        <StatCard label={t('slackActivityTab.avgLatency')} value={`${avgLatency}ms`} />
      </div>

      <div
        className="chart-panel"
        role="region"
        aria-label={t('slackActivityTab.dailyTrend')}
      >
        <h4 className="chart-panel__title">{t('slackActivityTab.dailyTrend')}</h4>
        {daily.length > 1 ? (
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={daily} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <defs>
                <linearGradient id="slackDailyGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={paletteColor(2)} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={paletteColor(2)} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...CHART_GRID_STYLE} />
              <XAxis
                dataKey="day"
                tick={CHART_AXIS_STYLE.tick}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={CHART_AXIS_STYLE.tick}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<ChartTooltip />} />
              <Area
                type="monotone"
                dataKey="messageCount"
                name={t('slackActivityTab.messages')}
                {...getAreaSeriesProps(2)}
                fill="url(#slackDailyGrad)"
                animationDuration={800}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ textAlign: 'center', padding: 'var(--space-4)', color: 'var(--text-muted)' }}>
            {t('common.noData')}
          </div>
        )}
      </div>

      <div className="detail-panel detail-panel--compact" style={{ marginTop: 'var(--space-4)' }}>
        <h4 className="section-title">{t('slackActivityTab.channelStats')}</h4>
        <DataTable
          columns={columns}
          data={channels}
          keyFn={(row) => row.channel}
        />
      </div>
    </div>
  )
}

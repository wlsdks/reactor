import './LatencyDashboardManager.css'
import { lazy, Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { EmptyState } from '../../../shared/ui/EmptyState'
import { SkeletonCard, SkeletonChart } from '../../../shared/ui/Skeleton'
import { SectionErrorBoundary } from '../../../shared/ui/SectionErrorBoundary'
import { HelpHint } from '../../../shared/ui/HelpHint'
import { paletteColor } from '../../../shared/ui/ChartConfig'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getLatencyTimeSeries, getLatencySummary } from '../api'

// Lazy-load the chart so the controls and summary remain immediately available.
const PercentileChart = lazy(() =>
  import('../../../shared/ui/PercentileChart').then((m) => ({ default: m.PercentileChart })),
)
function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

const DAYS_OPTIONS = [1, 3, 7, 30]

// Latency overlay reuses palette indices that pair with PercentileChart's
// defaults so the legend color story stays consistent across the page:
//   p95 → idx 1 (emerald, like PercentileChart's p95 default)
//   avg → idx 0 (mist blue, neutral primary trend)
function buildLatencyDataKeys(t: (key: string) => string) {
  return [
    {
      key: 'p95',
      name: t('performancePage.legend.p95'),
      stroke: paletteColor(1),
      strokeWidth: 1.5,
      gradientId: 'latencyP95Grad',
      gradientColor: paletteColor(1),
      gradientOpacity: 0.2,
    },
    {
      key: 'avg',
      name: t('performancePage.legend.avg'),
      stroke: paletteColor(0),
      strokeWidth: 2,
      gradientId: 'latencyAvgGrad',
      gradientColor: paletteColor(0),
      gradientOpacity: 0.3,
    },
  ]
}

export function LatencyDashboardManager() {
  const { t } = useTranslation()
  const [days, setDays] = useState(1)

  const {
    data: timeSeries,
    isLoading: timeSeriesLoading,
    isError: timeSeriesError,
    refetch: refetchTimeSeries,
  } = useQuery({
    queryKey: queryKeys.latency.timeSeries(days),
    queryFn: () => getLatencyTimeSeries(days),
  })

  const {
    data: summary,
    isLoading: summaryLoading,
    isError: summaryError,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: queryKeys.latency.summary(),
    queryFn: getLatencySummary,
  })

  const isLoading = timeSeriesLoading || summaryLoading
  const isError = timeSeriesError || summaryError
  const chartPoints = (timeSeries ?? []).filter((point) => point.count > 0)
  const hasSamples = (summary?.count ?? 0) > 0 || chartPoints.length > 0
  const latencyDataKeys = buildLatencyDataKeys(t).filter(
    (series) => series.key !== 'p95' || chartPoints.some((point) => point.p95Available === 1),
  )

  return (
    <div className="latency-dashboard">
      <div className="latency-dashboard__header">
        <select
          className="trace-viewer-status-filter"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          aria-label={t('latencyPage.daysLabel')}
        >
          {DAYS_OPTIONS.map((d) => (
            <option key={d} value={d}>
              {t('tracesPage.filters.lastNDays', { count: d })}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        // Match the final summary + chart footprint to avoid first-paint shift.
        <>
          <div className="latency-dashboard__summary-skeleton">
            <SkeletonCard height={80} />
            <SkeletonCard height={80} />
            <SkeletonCard height={80} />
          </div>
          <div className="latency-dashboard__chart">
            <SkeletonChart height={260} />
          </div>
        </>
      ) : isError ? (
        <EmptyState
          message={t('latencyPage.loadErrorTitle')}
          description={t('latencyPage.loadErrorDescription')}
          actionLabel={t('common.retry')}
          onAction={() => {
            void Promise.all([refetchTimeSeries(), refetchSummary()])
          }}
        />
      ) : !hasSamples ? (
        <EmptyState
          message={t('latencyPage.emptyTitle')}
          description={t('latencyPage.emptyDescription')}
        />
      ) : (
        <>
          <dl
            className="latency-dashboard__summary"
            role="region"
            aria-label={t('latencyPage.summaryStats')}
          >
            <div className="latency-dashboard__summary-primary">
              <dt>{t('latencyPage.currentP50')}</dt>
              <dd>{summary ? formatMs(summary.p50) : '—'}</dd>
              <span>{t('latencyPage.currentP50Hint')}</span>
            </div>
            <div>
              <dt className="text-with-hint">
                <span>{t('latencyPage.currentP95')}</span>
                <HelpHint title={t('latencyPage.currentP95')} label={t('latencyPage.currentP95Hint')} />
              </dt>
              <dd>{summary ? formatMs(summary.p95) : '—'}</dd>
            </div>
            <div>
              <dt className="text-with-hint">
                <span>{t('latencyPage.currentP99')}</span>
                <HelpHint title={t('latencyPage.currentP99')} label={t('latencyPage.currentP99Hint')} />
              </dt>
              <dd>{summary ? formatMs(summary.p99) : '—'}</dd>
            </div>
            <div>
              <dt>{t('latencyPage.sampleCount')}</dt>
              <dd>
                {summary?.count ?? chartPoints.reduce((sum, point) => sum + point.count, 0)}
              </dd>
            </div>
          </dl>

          <SectionErrorBoundary name="latency-chart">
            <div className="latency-dashboard__chart">
              <h3 className="latency-dashboard__chart-title">
                {t('latencyPage.latencyOverTime')}
              </h3>
              {chartPoints.length > 0 ? (
                <Suspense fallback={<SkeletonChart height={260} />}>
                  <PercentileChart
                    data={chartPoints}
                    height={260}
                    dataKeys={latencyDataKeys}
                    showLegend
                  />
                </Suspense>
              ) : (
                <div
                  style={{
                    textAlign: 'center',
                    padding: 'var(--space-4)',
                    color: 'var(--text-muted)',
                  }}
                >
                  {t('common.noData')}
                </div>
              )}
            </div>
          </SectionErrorBoundary>
        </>
      )}
    </div>
  )
}

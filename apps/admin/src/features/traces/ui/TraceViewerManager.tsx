import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  PageHeader,
  DataTable,
  EmptyState,
  SkeletonTable,
  HelpHint,
} from '../../../shared/ui'
import { WorkspaceUnavailable } from '../../../shared/ui/WorkspaceUnavailable'
import type { Column } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { formatDateTime, formatDuration, formatPercent } from '../../../shared/lib/formatters'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { usePageHelp } from '../../../shared/lib/usePageHelp'
import { listTraces } from '../api'
import type { TraceListItem } from '../types'
import { TraceDetailDrawer } from './TraceDetailDrawer'
import './TraceViewerManager.css'

const STATUS_OPTIONS: Array<{ value: string; labelKey: string }> = [
  { value: '', labelKey: 'tracesPage.filters.allStatuses' },
  { value: 'error', labelKey: 'tracesPage.filters.error' },
]

const DAYS_OPTIONS = [1, 3, 7, 14, 30]

function statusToBadge(success: boolean): string {
  return success ? 'SUCCESS' : 'ERROR'
}

/**
 * Maps the raw badge status (uppercase string from `statusToBadge` or any
 * future server-supplied state) to its Korean label key under
 * `tracesPage.statusLabels.*`. Falls back to `unknown` so we never render
 * the raw uppercase code in the UI.
 */
function statusLabelKey(status: string): string {
  switch (status.toUpperCase()) {
    case 'SUCCESS':
      return 'tracesPage.statusLabels.success'
    case 'ERROR':
    case 'FAIL':
    case 'FAILED':
      return 'tracesPage.statusLabels.error'
    case 'PARTIAL':
      return 'tracesPage.statusLabels.partial'
    case 'TIMEOUT':
    case 'TIMED_OUT':
      return 'tracesPage.statusLabels.timeout'
    default:
      return 'tracesPage.statusLabels.unknown'
  }
}

function operatorRunId(value: string): string {
  const normalized = value.replace(/^run[_-]?/i, '')
  return `#${(normalized || value).slice(0, 8).toUpperCase()}`
}

export function TraceViewerManager() {
  const { t } = useTranslation()
  usePageHelp({ helpKey: 'tracesPage.help' })

  const [days, setDays] = useState(7)
  const [statusFilter, setStatusFilter] = useState('')
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: queryKeys.traces.list(days, undefined, statusFilter || undefined),
    queryFn: () =>
      listTraces({
        days,
        limit: 200,
        status: statusFilter || undefined,
      }),
    placeholderData: keepPreviousData,
  })
  const traces = data ?? []
  const isInitialLoading = isLoading && data === undefined
  const hasUnavailableSnapshot = Boolean(error) && data === undefined

  // Compute stats from available traces.
  //
  // NOTE: The backend endpoint GET /api/admin/traces returns only the raw
  // per-trace list (no pre-computed P50/P95/P99 aggregates), so the client
  // must derive avg and P95 locally. If the backend later exposes percentile
  // fields on a stats endpoint, switch to those — they will be more accurate
  // than a client-side percentile over a paginated slice (limit=200).
  const errorCount = traces.filter((tr) => !tr.success).length
  const errorRateLabel = traces.length > 0 ? formatPercent(errorCount / traces.length) : '0.0%'
  const avgDuration = traces.length > 0
    ? Math.round(traces.reduce((sum, tr) => sum + tr.totalDurationMs, 0) / traces.length)
    : 0
  // Nearest-rank P95: index = ceil(0.95 * n) - 1, clamped to [0, n-1].
  // Previously used Math.floor(n * 0.95), which degenerates to the minimum
  // for n = 1 and is one rank higher than the canonical nearest-rank formula.
  const sortedDurations = [...traces].map((tr) => tr.totalDurationMs).sort((a, b) => a - b)
  const p95Index = Math.min(
    sortedDurations.length - 1,
    Math.max(0, Math.ceil(sortedDurations.length * 0.95) - 1),
  )
  const p95Duration = sortedDurations.length > 0 ? sortedDurations[p95Index] : 0

  const handleRowClick = (trace: TraceListItem) => {
    setSelectedTraceId(trace.traceId)
    setDrawerOpen(true)
  }

  const handleDrawerClose = () => {
    setDrawerOpen(false)
  }

  const columns: Column<TraceListItem>[] = [
    {
      key: 'time',
      header: t('tracesPage.columns.timestamp'),
      sortable: true,
      // Time is the primary scan column on /traces — keep visible at all widths.
      responsivePriority: 1,
      exportAccessor: (row) => formatDateTime(row.time),
      render: (row) => (
        <span className="mono">{formatDateTime(row.time)}</span>
      ),
    },
    {
      key: 'success',
      header: t('tracesPage.columns.status'),
      width: '120px',
      // Status is the second-most-important signal — always visible.
      responsivePriority: 1,
      exportAccessor: (row) => statusToBadge(row.success),
      render: (row) => {
        const status = statusToBadge(row.success)
        return (
          <span className="trace-status" data-status={row.success ? 'success' : 'error'}>
            {t(statusLabelKey(status))}
          </span>
        )
      },
    },
    {
      key: 'runId',
      header: (
        <span className="text-with-hint">
          {t('tracesPage.columns.runId')}
          <HelpHint label={t('tracesPage.helpHints.runId')} />
        </span>
      ),
      // runId is a long opaque UUID — secondary on narrow screens, falls into
      // the responsive expander (≥3) below 900px.
      responsivePriority: 3,
      exportAccessor: (row) => row.runId ?? null,
      render: (row) => {
        // runId is a long UUID-like string; show the first 8 chars to keep
        // the column scannable while the full value remains accessible via
        // hover (`title`) and screen readers (`aria-label`).
        const fullId = row.runId ?? ''
        if (!fullId) {
          return <span className="text-muted">-</span>
        }
        return (
          <span className="mono" title={fullId} aria-label={fullId}>
            {operatorRunId(fullId)}
          </span>
        )
      },
    },
    {
      key: 'totalDurationMs',
      header: t('tracesPage.columns.duration'),
      sortable: true,
      width: '110px',
      // The mobile master row keeps only time and outcome; duration remains
      // available in the responsive detail and the selected execution drawer.
      responsivePriority: 3,
      render: (row) => <span className="mono">{formatDuration(row.totalDurationMs)}</span>,
    },
    {
      key: 'spanCount',
      header: (
        <span className="text-with-hint">
          {t('tracesPage.columns.spans')}
          <HelpHint label={t('tracesPage.helpHints.spans')} />
        </span>
      ),
      sortable: true,
      width: '120px',
      // Span count is supplemental detail — collapse into the responsive
      // expander on narrow screens.
      responsivePriority: 3,
      render: (row) => <span>{t('tracesPage.stepCount', { count: row.spanCount })}</span>,
    },
  ]

  return (
    <div className="trace-viewer">
      <PageHeader
        title={t('tracesPage.title')}
        description={t('tracesPage.description')}
      />

      {hasUnavailableSnapshot ? (
        <WorkspaceUnavailable
          title={t('tracesPage.unavailableTitle')}
          description={t('tracesPage.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refetch}
          isRetrying={isFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('tracesPage.recoveryGuideTitle'),
            steps: [
              t('tracesPage.recoveryCheckAccount'),
              t('tracesPage.recoveryCheckConnection'),
              t('tracesPage.recoveryRetry'),
            ],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: getErrorMessage(error),
          }}
        />
      ) : isInitialLoading ? (
        <SkeletonTable rows={8} columns={5} />
      ) : (
        <>
          <div className="trace-viewer-controls">
            <select
              className="trace-viewer-status-filter"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              aria-label={t('tracesPage.filters.daysLabel')}
            >
              {DAYS_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {t('tracesPage.filters.lastNDays', { count: d })}
                </option>
              ))}
            </select>
            <select
              className="trace-viewer-status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              aria-label={t('tracesPage.filters.statusLabel')}
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {t(opt.labelKey)}
                </option>
              ))}
            </select>
          </div>

          {error ? (
            <div className="trace-viewer-revalidation" role="status">
              <div><strong>{t('tracesPage.revalidationTitle')}</strong><span>{t('tracesPage.revalidationDescription')}</span></div>
              <button className="btn btn-secondary btn-sm" type="button" onClick={() => void refetch()} disabled={isFetching}>
                {isFetching ? t('common.retrying') : t('common.retry')}
              </button>
            </div>
          ) : null}

          <dl className="trace-viewer-stats" aria-label={t('tracesPage.stats.summaryLabel')}>
            <div className="trace-viewer-stats__primary"><dt>{t('tracesPage.stats.totalTraces')}</dt><dd>{t('tracesPage.traceCount', { count: traces.length })}</dd></div>
            <div><dt>{t('tracesPage.stats.errorRate')}</dt><dd>{errorRateLabel}</dd></div>
            <div><dt>{t('tracesPage.stats.avgDuration')}</dt><dd>{formatDuration(avgDuration)}</dd></div>
            <div>
              <dt className="text-with-hint">
                {t('tracesPage.stats.p95Duration')}
                <HelpHint label={t('tracesPage.helpHints.p95')} />
              </dt>
              <dd>{formatDuration(p95Duration)}</dd>
            </div>
          </dl>

          {!isLoading && !error && traces.length === 0 && (
            <EmptyState message={t('tracesPage.empty')} />
          )}

          {!isLoading && traces.length > 0 && (
            <DataTable
              columns={columns}
              data={traces}
              keyFn={(row) => row.traceId}
              onRowClick={handleRowClick}
              selectedKey={selectedTraceId}
              tableId="traces"
              urlStateKey="traces"
              exportable={{ filename: 'traces' }}
            />
          )}

          <TraceDetailDrawer
            traceId={selectedTraceId}
            open={drawerOpen}
            onClose={handleDrawerClose}
          />
        </>
      )}
    </div>
  )
}

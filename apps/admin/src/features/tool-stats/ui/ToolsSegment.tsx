import { useState } from 'react'
import { Link } from 'react-router-dom'
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
  DataTable,
  EmptyState,
  HelpHint,
  paletteColor,
  SectionErrorBoundary,
  SkeletonCard,
  SkeletonChart,
  SkeletonTable,
} from '../../../shared/ui'
import type { Column } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'

import { aggregateByTool, type AggregatedToolRow } from '../aggregate'
import { getToolAccuracy, getToolStats } from '../api'
import type { ToolStatsByToolTuple } from '../types'

import './ToolsSegment.css'

/** One stacked bar per server; stack segments by canonical outcome bucket. */
interface ServerOutcomeRow {
  server: string
  ok: number
  error: number
  timeout: number
}

function buildServerOutcomeRows(
  byTool: ToolStatsByToolTuple[],
): ServerOutcomeRow[] {
  const map = new Map<string, ServerOutcomeRow>()
  for (const tuple of byTool) {
    const row = map.get(tuple.server) ?? {
      server: tuple.server,
      ok: 0,
      error: 0,
      timeout: 0,
    }
    if (tuple.outcome === 'ok') row.ok += tuple.count
    else if (tuple.outcome === 'error') row.error += tuple.count
    else if (tuple.outcome === 'timeout') row.timeout += tuple.count
    map.set(tuple.server, row)
  }
  return [...map.values()].sort((a, b) => {
    const totalA = a.ok + a.error + a.timeout
    const totalB = b.ok + b.error + b.timeout
    return totalB - totalA
  })
}

function formatPct(rate: number): string {
  if (!Number.isFinite(rate)) return '-'
  return `${Math.round(rate * 100)}%`
}

/**
 * Backend tool IDs are stable routing keys, not operator-facing names. Keep
 * the recognizable built-ins friendly and give unknown integrations a stable
 * on-screen label for the current ranking. The original key remains available
 * from the adjacent help affordance when support needs it.
 */
function displayToolName(
  tool: string,
  position: number,
  t: (key: string, options?: Record<string, unknown>) => string,
): string {
  const knownNames: Record<string, string> = {
    'web.search': 'performancePage.tools.toolNames.webSearch',
    'fs.read': 'performancePage.tools.toolNames.fileRead',
  }

  const translationKey = knownNames[tool]
  return translationKey
    ? t(translationKey)
    : t('performancePage.tools.toolNames.externalTool', { number: position })
}

interface ServerBreakdownChartProps {
  data: ServerOutcomeRow[]
  successLabel: string
  errorLabel: string
  timeoutLabel: string
}

function ServerBreakdownChart({
  data,
  successLabel,
  errorLabel,
  timeoutLabel,
}: ServerBreakdownChartProps) {
  // Recharts SVG attributes cannot consume CSS custom properties for `fill`,
  // so palette indices resolve to literal hex via paletteColor (DESIGN.md §11).
  const successFill = paletteColor(1) // emerald
  const errorFill = paletteColor(4) // rose
  const timeoutFill = paletteColor(2) // amber

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
        <CartesianGrid {...CHART_GRID_STYLE} />
        <XAxis dataKey="server" {...CHART_AXIS_STYLE} />
        <YAxis {...CHART_AXIS_STYLE} allowDecimals={false} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'var(--bg-hover)' }} />
        <Legend wrapperStyle={{ paddingTop: 8 }} />
        <Bar dataKey="ok" stackId="a" fill={successFill} name={successLabel} />
        <Bar dataKey="error" stackId="a" fill={errorFill} name={errorLabel} />
        <Bar
          dataKey="timeout"
          stackId="a"
          fill={timeoutFill}
          name={timeoutLabel}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function ToolsSegment() {
  const { t } = useTranslation()
  const [serverFilter, setServerFilter] = useState<string>('')

  const statsQuery = useQuery({
    queryKey: queryKeys.toolStats.stats(serverFilter || undefined),
    queryFn: () => getToolStats(serverFilter ? { server: serverFilter } : undefined),
  })

  const accuracyQuery = useQuery({
    queryKey: queryKeys.toolStats.accuracy(),
    queryFn: () => getToolAccuracy(),
  })

  // No manual memoization (useMemo / useCallback / React.memo) — the React
  // Compiler handles memoization automatically per CLAUDE.md.
  const aggregated: AggregatedToolRow[] = statsQuery.data
    ? aggregateByTool(statsQuery.data.byTool)
    : []

  const serverBreakdown: ServerOutcomeRow[] = statsQuery.data
    ? buildServerOutcomeRows(statsQuery.data.byTool)
    : []

  // Use byServer keys so the dropdown reflects every counted server even
  // when the byTool sample is capped at the BE's top-50 limit.
  const serverOptions: string[] = statsQuery.data
    ? Object.keys(statsQuery.data.byServer).sort()
    : []

  const displayedServerIds = [
    ...new Set([
      ...serverOptions,
      ...serverBreakdown.map((row) => row.server),
      ...aggregated.flatMap((row) => row.servers),
    ]),
  ].sort()
  const serverDisplayNames = new Map(
    displayedServerIds.map((server, index) => [
      server,
      t('performancePage.tools.connectionTarget', { number: index + 1 }),
    ]),
  )
  const toolDisplayNames = new Map(
    aggregated.map((row, index) => [
      row.tool,
      displayToolName(row.tool, index + 1, t),
    ]),
  )
  const displayedServerBreakdown = serverBreakdown.map((row) => ({
    ...row,
    server: serverDisplayNames.get(row.server) ?? row.server,
  }))

  const columns: Column<AggregatedToolRow>[] = [
      {
        key: 'tool',
        header: t('performancePage.tools.fields.tool'),
        render: (row) => (
          <span className="tools-segment__tool-cell">
            <span>
              {toolDisplayNames.get(row.tool)
                ?? t('performancePage.tools.toolNames.externalTool', { number: 1 })}
            </span>
            <HelpHint
              label={t('performancePage.tools.technicalToolIdentifier', {
                identifier: row.tool,
              })}
              title={t('performancePage.tools.technicalToolIdentifierTitle')}
            />
          </span>
        ),
        sortable: true,
        responsivePriority: 1,
      },
      {
        key: 'servers',
        header: t('performancePage.tools.fields.servers'),
        render: (row) => (
          <span className="tools-segment__servers-cell">
            {row.servers
              .map((server) => serverDisplayNames.get(server) ?? t('performancePage.tools.connectionTarget', { number: 1 }))
              .join(', ')}
          </span>
        ),
        exportAccessor: (row) => row.servers
          .map((server) => serverDisplayNames.get(server) ?? t('performancePage.tools.connectionTarget', { number: 1 }))
          .join(', '),
        responsivePriority: 3,
      },
      {
        key: 'total',
        header: t('performancePage.tools.fields.calls'),
        render: (row) => (
          <span className="tools-segment__rate-cell">{row.total}</span>
        ),
        exportAccessor: (row) => row.total,
        sortable: true,
        responsivePriority: 1,
      },
      {
        key: 'successRate',
        header: t('performancePage.tools.fields.successPct'),
        render: (row) => (
          <span className="tools-segment__rate-cell">
            {formatPct(row.successRate)}
          </span>
        ),
        exportAccessor: (row) => formatPct(row.successRate),
        sortable: true,
        responsivePriority: 2,
      },
      {
        key: 'errorRate',
        header: t('performancePage.tools.fields.errorPct'),
        render: (row) => (
          <span className="tools-segment__rate-cell">
            {formatPct(row.errorRate)}
          </span>
        ),
        exportAccessor: (row) => formatPct(row.errorRate),
        sortable: true,
        responsivePriority: 3,
      },
      {
        key: 'timeoutRate',
        header: t('performancePage.tools.fields.timeoutPct'),
        render: (row) => (
          <span className="tools-segment__rate-cell">
            {formatPct(row.timeoutRate)}
          </span>
        ),
        exportAccessor: (row) => formatPct(row.timeoutRate),
        sortable: true,
        responsivePriority: 3,
      },
      {
        key: 'actions',
        header: t('performancePage.tools.fields.actions'),
        render: (row) => (
          <Link
            to={`/traces?tool=${encodeURIComponent(row.tool)}`}
            className="tools-segment__action-link"
            aria-label={t('performancePage.tools.viewTracesAction')}
          >
            {t('performancePage.tools.viewTracesAction')}
          </Link>
        ),
        excludeFromExport: true,
        responsivePriority: 2,
      },
    ]

  if (statsQuery.isLoading) {
    return (
      <div data-testid="tools-segment-loading">
        <div className="tools-segment__stats">
          <SkeletonCard height={80} />
          <SkeletonCard height={80} />
          <SkeletonCard height={80} />
          <SkeletonCard height={80} />
        </div>
        <div className="tools-segment__panel">
          <SkeletonChart height={260} />
        </div>
        <div className="tools-segment__panel">
          <SkeletonTable rows={5} />
        </div>
      </div>
    )
  }

  if (statsQuery.isError) {
    return (
      <div
        data-testid="tools-segment-error"
        className="tools-segment__error"
        role="alert"
      >
        {t('performancePage.tools.loadError')}
      </div>
    )
  }

  const stats = statsQuery.data
  if (!stats) {
    // Defensive — TanStack Query's success state implies data is present, but
    // narrow the type here so downstream destructuring stays type-safe.
    return null
  }
  const totalCalls = stats.total
  const denominator = Math.max(totalCalls, 1)
  const successRate = (stats.byOutcome.ok ?? 0) / denominator
  const errorRate = (stats.byOutcome.error ?? 0) / denominator
  const timeoutRate = (stats.byOutcome.timeout ?? 0) / denominator
  const accuracy = accuracyQuery.data?.accuracy ?? stats.accuracy

  if (totalCalls === 0 && aggregated.length === 0) {
    return (
      <div className="tools-segment">
        <div className="tools-segment__header">
          <label className="tools-segment__filter-label">
            <span>{t('performancePage.tools.serverFilterLabel')}</span>
            <select className="trace-viewer-status-filter" value={serverFilter} onChange={(e) => setServerFilter(e.target.value)} aria-label={t('performancePage.tools.serverFilterLabel')}>
              <option value="">{t('performancePage.tools.serverFilterAll')}</option>
              {serverOptions.map((server) => (
                <option key={server} value={server}>
                  {serverDisplayNames.get(server) ?? t('performancePage.tools.connectionTarget', { number: 1 })}
                </option>
              ))}
            </select>
          </label>
        </div>
        <EmptyState message={t('performancePage.tools.emptyTitle')} description={t('performancePage.tools.emptyDescription')} />
      </div>
    )
  }

  return (
    <div className="tools-segment">
      <div className="tools-segment__header">
        <label className="tools-segment__filter-label">
          <span>{t('performancePage.tools.serverFilterLabel')}</span>
          <select
            className="trace-viewer-status-filter"
            value={serverFilter}
            onChange={(e) => setServerFilter(e.target.value)}
            aria-label={t('performancePage.tools.serverFilterLabel')}
          >
            <option value="">
              {t('performancePage.tools.serverFilterAll')}
            </option>
            {serverOptions.map((s) => (
              <option key={s} value={s}>
                {serverDisplayNames.get(s) ?? t('performancePage.tools.connectionTarget', { number: 1 })}
              </option>
            ))}
          </select>
        </label>
      </div>

      <dl className="tools-segment__stats" aria-label={t('performancePage.tools.summaryLabel')}>
        <div className="tools-segment__stat-primary">
          <dt>{t('performancePage.tools.successRate')}</dt>
          <dd>{formatPct(successRate)}</dd>
          <span>{t('performancePage.tools.successRateHint')}</span>
        </div>
        <div><dt>{t('performancePage.tools.totalCalls')}</dt><dd>{totalCalls.toLocaleString()}</dd></div>
        <div><dt>{t('performancePage.tools.errorRate')}</dt><dd>{formatPct(errorRate)}</dd></div>
        <div><dt>{t('performancePage.tools.timeoutRate')}</dt><dd>{formatPct(timeoutRate)}</dd></div>
      </dl>

      <SectionErrorBoundary name="tools-segment-server-breakdown">
        <section className="tools-segment__panel" aria-labelledby="tools-server-title">
          <h3 id="tools-server-title" className="tools-segment__panel-title">
            {t('performancePage.tools.serverBreakdownTitle')}
          </h3>
          {serverBreakdown.length === 0 ? (
            <div className="tools-segment__empty">
              {t('performancePage.tools.serverBreakdownEmpty')}
            </div>
          ) : (
            <ServerBreakdownChart
              data={displayedServerBreakdown}
              successLabel={t('performancePage.tools.fields.success')}
              errorLabel={t('performancePage.tools.fields.error')}
              timeoutLabel={t('performancePage.tools.fields.timeout')}
            />
          )}
        </section>
      </SectionErrorBoundary>

      <SectionErrorBoundary name="tools-segment-ranking">
        <section className="tools-segment__panel" aria-labelledby="tools-ranking-title">
          <h3 id="tools-ranking-title" className="tools-segment__panel-title">
            {t('performancePage.tools.rankingTitle')}
          </h3>
          {aggregated.length === 0 ? (
            <EmptyState message={t('performancePage.tools.rankingEmpty')} />
          ) : (
            <DataTable
              data={aggregated}
              columns={columns}
              keyFn={(row) => row.tool}
              urlStateKey="perf-tools"
              tableId="perf-tools"
              exportable={{ filename: 'tool-stats' }}
            />
          )}
        </section>
      </SectionErrorBoundary>

      <div className="tools-segment__accuracy">
        <div>
          <strong>{t('performancePage.tools.accuracyTitle')}</strong>
          <p>{t('performancePage.tools.accuracySub')}</p>
        </div>
        <b>{formatPct(accuracy)}</b>
      </div>
    </div>
  )
}

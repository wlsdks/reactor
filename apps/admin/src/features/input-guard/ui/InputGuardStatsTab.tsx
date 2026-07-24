import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  StatCard,
  SkeletonCard,
  SkeletonTable,
  EmptyState,
  DataTable,
  type Column,
} from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { formatPercent } from '../../../shared/lib/formatters'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import * as inputGuardApi from '../api'
import type { StageStats } from '../api'

/**
 * Input Guard statistics — aggregate metrics from metric_guard_events.
 *
 * UX rationale:
 * - Four KPI cards (total / allowed / blocked / block rate) always visible.
 * - Period selector (1h / 24h / 7d) matches typical incident-response windows.
 * - By-stage table sorts by triggered count DESC so heaviest stage is first.
 * - Top rejection reasons shown inline per stage for quick incident triage.
 */
export function InputGuardStatsTab() {
  const { t } = useTranslation()
  const [hours, setHours] = useState<number>(24)

  const statsQuery = useQuery({
    queryKey: queryKeys.inputGuard.stats({ hours }),
    queryFn: () => inputGuardApi.getInputGuardStats(hours),
  })

  const stats = statsQuery.data
  const errorMsg = statsQuery.error ? getErrorMessage(statsQuery.error) : null
  // Block rate uses 2 decimal places (existing UX). When stats are missing,
  // render a single dash rather than "-%" to match the prior placeholder.
  const blockRateLabel = stats ? formatPercent(stats.blockRate, 2) : '-'

  const columns: Column<StageStats>[] = [
    {
      key: 'stage',
      header: t('inputGuard.stats.colStage'),
      render: (row) => <code className="ig-stage-name">{row.stage}</code>,
    },
    {
      key: 'triggered',
      header: t('inputGuard.stats.colTriggered'),
      render: (row) => <span className="ig-num">{formatLocaleNumber(row.triggered)}</span>,
    },
    {
      key: 'allowed',
      header: t('inputGuard.stats.allowed'),
      render: (row) => (
        <span className="ig-num ig-num--muted">{formatLocaleNumber(row.allowed)}</span>
      ),
    },
    {
      key: 'rejected',
      header: t('inputGuard.stats.rejected'),
      render: (row) => (
        <span className={`ig-num${row.rejected > 0 ? ' ig-num--rejected' : ' ig-num--muted'}`}>
          {formatLocaleNumber(row.rejected)}
        </span>
      ),
    },
    {
      key: 'errors',
      header: t('inputGuard.stats.errors'),
      render: (row) => (
        <span className={`ig-num${row.errors > 0 ? ' ig-num--errors' : ' ig-num--muted'}`}>
          {formatLocaleNumber(row.errors)}
        </span>
      ),
    },
    {
      key: 'reasons',
      header: t('inputGuard.stats.topReasons'),
      render: (row) =>
        row.topReasons.length === 0 ? (
          <span className="ig-num--muted">-</span>
        ) : (
          <div className="ig-reasons">
            {row.topReasons.slice(0, 3).map((r) => (
              <span key={r.reason} className="ig-reasons__item">
                <code>{r.reason}</code>
                <span className="ig-reasons__count">×{r.count}</span>
              </span>
            ))}
          </div>
        ),
    },
  ]

  return (
    <div>
      <div className="ig-toolbar">
        <label htmlFor="stats-hours" className="ig-toolbar__label">
          {t('inputGuard.stats.period')}
        </label>
        <select
          id="stats-hours"
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
        >
          <option value={1}>{t('inputGuard.stats.last1h')}</option>
          <option value={24}>{t('inputGuard.stats.last24h')}</option>
          <option value={168}>{t('inputGuard.stats.last7d')}</option>
        </select>
        <div className="ig-toolbar__spacer" />
        {stats && (
          <span className="ig-toolbar__meta">
            {t('inputGuard.stats.totalCount', { count: stats.totalRequests })}
          </span>
        )}
      </div>

      {errorMsg && <div className="alert alert-error">{errorMsg}</div>}
      {statsQuery.isLoading && (
        <>
          <div className="stat-grid">
            <SkeletonCard height={80} />
            <SkeletonCard height={80} />
            <SkeletonCard height={80} />
            <SkeletonCard height={80} />
          </div>
          <div className="detail-panel detail-panel--compact" style={{ marginTop: 'var(--space-4)' }}>
            <SkeletonTable rows={5} columns={4} />
          </div>
        </>
      )}

      {!statsQuery.isLoading && stats && stats.totalRequests === 0 && !errorMsg && (
        <EmptyState
          message={t('inputGuard.stats.emptyTitle')}
          description={t('inputGuard.stats.emptyDesc')}
        />
      )}

      {!statsQuery.isLoading && stats && stats.totalRequests > 0 && (
        <>
          <div className="stat-grid">
            <StatCard
              label={t('inputGuard.stats.totalRequests')}
              value={formatLocaleNumber(stats.totalRequests)}
            />
            <StatCard
              label={t('inputGuard.stats.allowed')}
              value={formatLocaleNumber(stats.totalAllowed)}
            />
            <StatCard
              label={t('inputGuard.stats.rejected')}
              value={formatLocaleNumber(stats.totalRejected)}
            />
            <StatCard
              label={t('inputGuard.stats.blockRate')}
              value={blockRateLabel}
            />
          </div>

          {stats.totalErrors > 0 && (
            <div className="alert alert-warning ig-stats-note">
              {t('inputGuard.stats.errorsNotice', { count: stats.totalErrors })}
            </div>
          )}

          <div className="detail-panel detail-panel--compact ig-stage-table-wrap ig-stage-table">
            <h2 className="section-title">{t('inputGuard.stats.byStage')}</h2>
            <DataTable<StageStats>
              data={stats.byStage}
              columns={columns}
              keyFn={(row) => row.stage}
            />
          </div>
        </>
      )}
    </div>
  )
}

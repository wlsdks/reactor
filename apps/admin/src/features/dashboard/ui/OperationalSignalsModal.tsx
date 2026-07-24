import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  ChartTooltip,
  CollapsibleSection,
  DetailModal,
  formatNumber,
  LoadingSpinner,
  StatusBadge,
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  paletteColor,
} from '../../../shared/ui'
import { formatRelativeTimeKo } from '../../../shared/lib/formatRelativeTimeKo'
import {
  dashboardExecutionTimestamp,
  describeTrustEventDetail,
  describeTrustEventType,
  humanizeMetricName,
} from '../presenters'
import { buildTrustEventInspectorHref } from '../../chat-inspector/prefill'
import type {
  OpsMetricSnapshot,
  DashboardRecentSchedulerExecution,
  DashboardRecentTrustEvent,
  DashboardResponseTrustSummary,
} from '../types'

// -- Helpers ------------------------------------------------------------------

type SignalColor = 'green' | 'yellow' | 'red' | 'neutral'

function signalColorVar(color: SignalColor): string {
  switch (color) {
    case 'green': return 'var(--green)'
    case 'yellow': return 'var(--yellow)'
    case 'red': return 'var(--red)'
    case 'neutral': return 'var(--text-secondary)'
  }
}

function signalColorClass(color: SignalColor): string {
  switch (color) {
    case 'green': return 'signal-card--green'
    case 'yellow': return 'signal-card--yellow'
    case 'red': return 'signal-card--red'
    case 'neutral': return 'signal-card--neutral'
  }
}

function deriveOverallStatus(
  schedulerBacklog: number,
  pendingApprovals: number,
  responseTrust: DashboardResponseTrustSummary,
  t: TFunction,
): { label: string; color: SignalColor } {
  if (responseTrust.outputGuardRejected > 0) {
    return { label: t('dashboard.signalStatus.attention'), color: 'red' }
  }
  if (schedulerBacklog > 0 || pendingApprovals > 0 || responseTrust.outputGuardModified > 0) {
    return { label: t('dashboard.signalStatus.minorAttention'), color: 'yellow' }
  }
  return { label: t('dashboard.signalStatus.allClear'), color: 'green' }
}

const MAX_RECENT_EVENTS = 5

// -- Component ----------------------------------------------------------------

interface OperationalSignalsModalProps {
  open: boolean
  onClose: () => void
  metrics: OpsMetricSnapshot[]
  metricFilterRaw: string
  metricNames: string[]
  onMetricFilterChange: (value: string) => void
  onApplyMetrics: () => void
  onResetMetrics: () => void
  refreshing: boolean
  responseTrust: DashboardResponseTrustSummary
  schedulerBacklog: number
  pendingApprovals: number
  unverifiedResponses: number
  recentExecutions: DashboardRecentSchedulerExecution[]
  recentTrustEvents: DashboardRecentTrustEvent[]
}

export function OperationalSignalsModal({
  open,
  onClose,
  metrics,
  metricFilterRaw,
  metricNames,
  onMetricFilterChange,
  onApplyMetrics,
  onResetMetrics,
  refreshing,
  responseTrust,
  schedulerBacklog,
  pendingApprovals,
  unverifiedResponses,
  recentExecutions,
  recentTrustEvents,
}: OperationalSignalsModalProps) {
  const { t } = useTranslation()

  const overall = deriveOverallStatus(schedulerBacklog, pendingApprovals, responseTrust, t)

  // Chart data with human-readable labels
  const chartData = metrics
    .slice()
    .sort((a, b) => b.meterCount - a.meterCount)
    .filter(m => m.meterCount > 0)
    .slice(0, 8)
    .map(m => ({
      name: humanizeMetricName(m.name, t),
      count: m.meterCount,
    }))

  // Split events into scheduler and trust, limited to 5 each
  const schedulerEvents = recentExecutions
    .slice()
    .sort((a, b) => dashboardExecutionTimestamp(b) - dashboardExecutionTimestamp(a))
    .slice(0, MAX_RECENT_EVENTS)

  const trustEvents = recentTrustEvents
    .slice()
    .sort((a, b) => b.occurredAt - a.occurredAt)
    .slice(0, MAX_RECENT_EVENTS)

  // Signal cards configuration
  const signalCards: Array<{
    label: string
    value: number
    color: SignalColor
  }> = [
    {
      label: t('dashboard.schedulerBacklog'),
      value: schedulerBacklog,
      color: schedulerBacklog > 0 ? 'yellow' : 'green',
    },
    {
      label: t('dashboard.pendingApprovals'),
      value: pendingApprovals,
      color: pendingApprovals > 0 ? 'yellow' : 'green',
    },
    {
      label: t('dashboard.outputGuardRejected'),
      value: responseTrust.outputGuardRejected,
      color: responseTrust.outputGuardRejected > 0 ? 'red' : 'green',
    },
    {
      label: t('dashboard.outputGuardModified'),
      value: responseTrust.outputGuardModified,
      color: responseTrust.outputGuardModified > 0 ? 'yellow' : 'green',
    },
    {
      label: t('dashboard.unverifiedResponses'),
      value: unverifiedResponses,
      color: 'neutral',
    },
  ]

  return (
    <DetailModal
      open={open}
      title={`${t('dashboard.operationalSignalsModal.title')} — ${overall.label}`}
      onClose={onClose}
    >
      {/* Section 1: Status Summary — signal cards grid */}
      <div className="signal-cards-grid" role="list" aria-label={t('dashboard.signalStatus.summary')}>
        {signalCards.map(card => (
          <div
            key={card.label}
            className={`signal-card ${signalColorClass(card.color)}`}
            role="listitem"
          >
            <div className="signal-card-value" style={{ color: signalColorVar(card.color) }}>
              {card.value}
            </div>
            <div className="signal-card-label">{card.label}</div>
          </div>
        ))}
      </div>

      {/* Section 2: Recent Events — split into scheduler + trust */}
      <div className="detail-panel detail-panel--compact">
        {/* 2a: Recent Scheduler Executions */}
        <div className="section">
          <h2 className="section-title">{t('dashboard.recentSchedulerTitle')}</h2>
          {schedulerEvents.length === 0 ? (
            <div className="section-muted-message">
              {t('dashboard.noRecentScheduler')}
            </div>
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col" style={{ width: '80px' }}>{t('common.time')}</th>
                    <th scope="col" style={{ width: '90px' }}>{t('common.status')}</th>
                    <th scope="col">{t('common.name')}</th>
                    <th scope="col">{t('common.detail')}</th>
                  </tr>
                </thead>
                <tbody>
                  {schedulerEvents.map((exec, i) => (
                    <tr key={`sched-${exec.id}-${i}`}>
                      <td style={{ whiteSpace: 'nowrap', color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>{formatRelativeTimeKo(dashboardExecutionTimestamp(exec))}</td>
                      <td><StatusBadge status={exec.status} /></td>
                      <td style={{ fontWeight: 'var(--font-weight-emphasis)' }}>{exec.jobName}</td>
                      <td style={{ color: 'var(--text-muted)' }}>{exec.failureReason ?? exec.resultPreview ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* 2b: Recent Trust Events */}
        <div className="section" style={{ marginTop: 'var(--space-4)' }}>
          <h2 className="section-title">{t('dashboard.recentTrustTitle')}</h2>
          {trustEvents.length === 0 ? (
            <div className="section-muted-message">
              {t('dashboard.noRecentTrust')}
            </div>
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col" style={{ width: '80px' }}>{t('common.time')}</th>
                    <th scope="col" style={{ width: '90px' }}>{t('common.severity')}</th>
                    <th scope="col">{t('common.type')}</th>
                    <th scope="col">{t('common.detail')}</th>
                    <th scope="col" style={{ width: '100px' }}>{t('common.action')}</th>
                  </tr>
                </thead>
                <tbody>
                  {trustEvents.map((event, i) => (
                    <tr key={`trust-${event.occurredAt}-${i}`}>
                      <td style={{ whiteSpace: 'nowrap', color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>{formatRelativeTimeKo(event.occurredAt)}</td>
                      <td><StatusBadge status={event.severity} /></td>
                      <td style={{ fontWeight: 'var(--font-weight-emphasis)' }}>{t(`dashboard.trust.${describeTrustEventType(event)}`)}</td>
                      <td style={{ color: 'var(--text-muted)' }}>{describeTrustEventDetail(event)}</td>
                      <td>
                        {buildTrustEventInspectorHref(event) && (
                          <button className="btn btn-secondary btn-sm" onClick={() => { window.location.href = buildTrustEventInspectorHref(event)! }}>
                            {t('dashboard.inspectInChatInspector')}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Section 3: Signal Chart — collapsed by default */}
      <CollapsibleSection title={t('dashboard.topSignals')} defaultOpen={false}>
        {chartData.length > 0 ? (
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData} layout="vertical" margin={{ top: 8, right: 16, left: 120, bottom: 0 }}>
                <CartesianGrid {...CHART_GRID_STYLE} horizontal={false} />
                <XAxis type="number" tick={{ ...CHART_AXIS_STYLE.tick, fontSize: 10, fontFamily: 'var(--font-mono)' }} tickFormatter={formatNumber} />
                <YAxis type="category" dataKey="name" tick={{ ...CHART_AXIS_STYLE.tick, fontFamily: 'var(--font-mono)' }} width={110} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" fill={paletteColor(2)} radius={[0, 2, 2, 0]} animationDuration={600} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="section-muted-message">{t('dashboard.noSignalChart')}</div>
        )}
      </CollapsibleSection>

      {/* Section 4: Advanced Metric Filter — collapsed */}
      <CollapsibleSection title={t('dashboard.advancedFilter')} defaultOpen={false}>
        <div className="section-toolbar" style={{ marginTop: 'var(--space-3)' }}>
          <div className="detail-note">{t('dashboard.advancedFilterDescription')}</div>
          <div className="header-filters">
            <button className="btn btn-secondary" onClick={onApplyMetrics} disabled={refreshing}>
              {refreshing ? <LoadingSpinner size="sm" /> : t('common.apply')}
            </button>
            <button className="btn btn-secondary" onClick={onResetMetrics} disabled={refreshing}>
              {t('common.reset')}
            </button>
          </div>
        </div>
        <div className="form-group">
          <label htmlFor="metric-filter-input">{t('dashboard.metricFilterLabel')}</label>
          <input
            id="metric-filter-input"
            value={metricFilterRaw}
            onChange={e => onMetricFilterChange(e.target.value)}
            placeholder={t('dashboard.metricFilterPlaceholder')}
          />
        </div>
        {metricNames.length > 0 && (
          <div className="tag-list">
            {metricNames.slice(0, 20).map(name => (
              <button
                key={name}
                type="button"
                className="tag"
                onClick={() => {
                  const current = metricFilterRaw
                    .split(',')
                    .map(n => n.trim())
                    .filter(Boolean)
                  if (current.includes(name)) return
                  onMetricFilterChange([...current, name].join(', '))
                }}
              >
                {name}
              </button>
            ))}
          </div>
        )}
      </CollapsibleSection>

      {/* Section 5: Raw Metrics Table — collapsed, developer detail */}
      {metrics.length > 0 && (
        <CollapsibleSection title={t('dashboard.metrics')} defaultOpen={false}>
          <div className="table-wrapper">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">{t('dashboard.metricSignal')}</th>
                  <th scope="col">{t('dashboard.metricSources')}</th>
                  <th scope="col">{t('dashboard.metricValues')}</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map(m => (
                  <tr key={m.name}>
                    <td><code>{m.name}</code></td>
                    <td>{m.meterCount}</td>
                    <td>
                      {m.meterCount === 0 ? (
                        <span className="metric-empty">&mdash;</span>
                      ) : (
                        Object.entries(m.measurements).map(([k, v]) => (
                          <span key={k} className="metric-measurement">
                            <span className="metric-key">{k}:</span>{' '}
                            <strong>{v % 1 === 0 ? v : v.toFixed(3)}</strong>
                          </span>
                        ))
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CollapsibleSection>
      )}
    </DetailModal>
  )
}

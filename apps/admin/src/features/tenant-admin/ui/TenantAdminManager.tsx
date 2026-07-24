import './TenantAdminManager.css'
import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  ChartTooltip,
  DataTable,
  EmptyState,
  formatNumber,
  HelpHint,
  LoadingSpinner,
  PageHeader,
  paletteColor,
  Tooltip as InfoTooltip,
} from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import { humanizeToolName } from '../../../shared/lib/humanizeToolName'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import { useTenantAdminData } from '../useTenantAdminData'
import type {
  TenantAlertResponse,
  TenantCostResponse,
  TenantQualityResponse,
  TenantQuotaResponse,
  TenantSloResponse,
  TenantToolsResponse,
  TenantUsageResponse,
} from '../types'

const percent = (value: number): string => `${(value * 100).toFixed(value * 100 < 10 ? 1 : 0)}%`
const money = (value: string | number): string => `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function localizedTenantValue(t: TFunction, value: string, keys: Record<string, string>, unknownKey: string): string {
  return t(keys[value.trim().toLowerCase()] ?? unknownKey)
}

function channelLabel(t: TFunction, value: string): string {
  return localizedTenantValue(t, value, {
    web: 'tenantAdminPage.channelLabels.web',
    api: 'tenantAdminPage.channelLabels.api',
    slack: 'tenantAdminPage.channelLabels.slack',
    a2a: 'tenantAdminPage.channelLabels.a2a',
    faq: 'tenantAdminPage.channelLabels.faq',
  }, 'tenantAdminPage.channelLabels.unknown')
}

function errorLabel(t: TFunction, value: string): string {
  return localizedTenantValue(t, value, {
    timeout: 'tenantAdminPage.errorLabels.timeout',
    request_timeout: 'tenantAdminPage.errorLabels.timeout',
    model_timeout: 'tenantAdminPage.errorLabels.modelTimeout',
    model_error: 'tenantAdminPage.errorLabels.modelError',
    tool_error: 'tenantAdminPage.errorLabels.toolError',
    guard_blocked: 'tenantAdminPage.errorLabels.guardBlocked',
    input_guard_blocked: 'tenantAdminPage.errorLabels.guardBlocked',
    output_guard_blocked: 'tenantAdminPage.errorLabels.guardBlocked',
  }, 'tenantAdminPage.errorLabels.unknown')
}

function alertSeverityLabel(t: TFunction, value: string): string {
  return localizedTenantValue(t, value, {
    critical: 'tenantAdminPage.alertSeverity.critical',
    error: 'tenantAdminPage.alertSeverity.critical',
    warning: 'tenantAdminPage.alertSeverity.warning',
    warn: 'tenantAdminPage.alertSeverity.warning',
    info: 'tenantAdminPage.alertSeverity.info',
  }, 'tenantAdminPage.alertSeverity.unknown')
}

function alertSeverityTone(value: string): 'critical' | 'info' | null {
  const normalized = value.trim().toLowerCase()
  if (normalized === 'critical' || normalized === 'error') return 'critical'
  if (normalized === 'info') return 'info'
  return null
}

function alertStatusLabel(t: TFunction, value: string): string {
  return localizedTenantValue(t, value, {
    open: 'tenantAdminPage.alertStatus.needsAttention',
    active: 'tenantAdminPage.alertStatus.needsAttention',
    acknowledged: 'tenantAdminPage.alertStatus.reviewing',
    resolved: 'tenantAdminPage.alertStatus.resolved',
    closed: 'tenantAdminPage.alertStatus.resolved',
  }, 'tenantAdminPage.alertStatus.unknown')
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="tenant-metric">
      <dt>{label}</dt>
      <dd>{value}</dd>
      {detail ? <span>{detail}</span> : null}
    </div>
  )
}

function SectionHeading({ id, title, description }: { id: string; title: string; description: string }) {
  return (
    <header className="tenant-operations__section-heading">
      <h3 id={id}>{title}</h3>
      <p>{description}</p>
    </header>
  )
}

function UsageSection({ data }: { data: TenantUsageResponse }) {
  const { t } = useTranslation()
  const channels = Object.entries(data.channelDistribution)
  return (
    <section className="tenant-operations__section" aria-labelledby="tenant-usage-title">
      <SectionHeading id="tenant-usage-title" title={t('tenantAdminPage.usage')} description={t('tenantAdminPage.sectionDescriptions.usage')} />
      <dl className="tenant-metrics tenant-metrics--compact">
        <Metric label={t('tenantAdminPage.avgTurns')} value={data.avgTurnsPerSession.toFixed(1)} />
        <Metric label={t('tenantAdminPage.resolveRate')} value={percent(data.sessionResolveRate)} />
        <Metric label={t('tenantAdminPage.abandonRate')} value={percent(data.sessionAbandonRate)} />
      </dl>
      {channels.length > 0 ? (
        <dl className="tenant-breakdown" aria-label={t('tenantAdminPage.channelDistribution')}>
          {channels.map(([channel, count]) => <div key={channel}><dt>{channelLabel(t, channel)}</dt><dd>{formatLocaleNumber(count)}</dd></div>)}
        </dl>
      ) : null}
      {data.topUsers.length > 0 ? (
        <div className="tenant-table-wrap">
          <table className="data-table">
            <thead><tr><th>{t('tenantAdminPage.user')}</th><th>{t('tenantAdminPage.totalRequests')}</th><th>{t('tenantAdminPage.totalTokens')}</th><th>{t('tenantAdminPage.totalCost')}</th><th>{t('tenantAdminPage.lastActivity')}</th></tr></thead>
            <tbody>{data.topUsers.map((row) => <tr key={row.userLabel}><td>{row.userLabel}</td><td>{formatLocaleNumber(row.requests)}</td><td>{formatLocaleNumber(row.tokens)}</td><td>{money(row.costUsd)}</td><td>{row.lastActivity ? formatDateTime(row.lastActivity) : '—'}</td></tr>)}</tbody>
          </table>
        </div>
      ) : <EmptyState message={t('tenantAdminPage.noUsage')} description={t('tenantAdminPage.analytics.emptyHint')} />}
    </section>
  )
}

function QualitySection({ data }: { data: TenantQualityResponse }) {
  const { t } = useTranslation()
  const errors = Object.entries(data.errorDistribution)
  return (
    <section className="tenant-operations__section" aria-labelledby="tenant-quality-title">
      <SectionHeading id="tenant-quality-title" title={t('tenantAdminPage.quality')} description={t('tenantAdminPage.sectionDescriptions.quality')} />
      <dl className="tenant-metrics tenant-metrics--compact">
        <Metric label={t('tenantAdminPage.typicalResponseTime')} value={`${formatLocaleNumber(data.latencyP50)} ms`} />
        <Metric label={t('tenantAdminPage.slowResponseTime')} value={`${formatLocaleNumber(data.latencyP95)} ms`} />
        <Metric label={t('tenantAdminPage.slowestResponseTime')} value={`${formatLocaleNumber(data.latencyP99)} ms`} />
      </dl>
      {errors.length > 0 ? <dl className="tenant-breakdown">{errors.map(([name, count]) => <div key={name}><dt>{errorLabel(t, name)}</dt><dd>{formatLocaleNumber(count)}</dd></div>)}</dl> : <p className="tenant-operations__healthy">{t('tenantAdminPage.noErrors')}</p>}
    </section>
  )
}

function ToolsSection({ data }: { data: TenantToolsResponse }) {
  const { t } = useTranslation()
  return (
    <section className="tenant-operations__section" aria-labelledby="tenant-tools-title">
      <SectionHeading id="tenant-tools-title" title={t('tenantAdminPage.tools')} description={t('tenantAdminPage.sectionDescriptions.tools')} />
      {data.toolRanking.length > 0 ? (
        <div className="tenant-table-wrap"><table className="data-table"><thead><tr><th>{t('tenantAdminPage.toolName')}</th><th>{t('tenantAdminPage.callCount')}</th><th>{t('tenantAdminPage.successRate')}</th><th>{t('tenantAdminPage.avgDuration')}</th><th>{t('tenantAdminPage.slowResponseTime')}</th></tr></thead><tbody>{data.toolRanking.map((row) => <tr key={`${row.mcpServerName ?? 'native'}:${row.toolName}`}><td><strong>{humanizeToolName(row.toolName)}</strong><small>{row.mcpServerName ? t('tenantAdminPage.externalTool') : t('tenantAdminPage.builtInTool')}</small></td><td>{formatLocaleNumber(row.calls)}</td><td>{percent(row.successRate)}</td><td>{formatLocaleNumber(row.avgDurationMs)} ms</td><td>{formatLocaleNumber(row.p95DurationMs)} ms</td></tr>)}</tbody></table></div>
      ) : <EmptyState message={t('tenantAdminPage.noTools')} />}
    </section>
  )
}

function CostSection({ data }: { data: TenantCostResponse }) {
  const { t } = useTranslation()
  const models = Object.entries(data.costByModel).map(([model, cost]) => ({ model, cost: Number(cost) }))
  return (
    <section className="tenant-operations__section" aria-labelledby="tenant-cost-title">
      <SectionHeading id="tenant-cost-title" title={t('tenantAdminPage.cost')} description={t('tenantAdminPage.sectionDescriptions.cost')} />
      <dl className="tenant-metrics tenant-metrics--compact">
        <Metric label={t('tenantAdminPage.totalCost')} value={money(data.monthlyCost)} />
        <Metric label={t('tenantAdminPage.costPerResolution')} value={money(data.costPerResolution)} />
        <Metric label={t('tenantAdminPage.cachedTokenRatio')} value={percent(data.cachedTokenRatio)} />
        <Metric label={t('tenantAdminPage.budgetUsage')} value={`${data.budgetUsagePercent.toFixed(1)}%`} />
      </dl>
      {models.length > 0 ? <div className="tenant-cost-layout"><div className="tenant-cost-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={models} margin={{ top: 8, right: 8, left: 4, bottom: 8 }}><CartesianGrid {...CHART_GRID_STYLE} vertical={false} /><XAxis dataKey="model" tick={{ ...CHART_AXIS_STYLE.tick, fontSize: 11 }} /><YAxis tick={CHART_AXIS_STYLE.tick} tickFormatter={formatNumber} /><Tooltip content={<ChartTooltip formatValue={(value) => money(value)} />} /><Bar dataKey="cost" fill={paletteColor(2)} radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div><dl className="tenant-breakdown">{models.map((row) => <div key={row.model}><dt>{row.model}</dt><dd>{money(row.cost)}</dd></div>)}</dl></div> : <EmptyState message={t('tenantAdminPage.noCost')} />}
    </section>
  )
}

function SloAndQuotaSection({ slo, quota }: { slo: TenantSloResponse; quota: TenantQuotaResponse }) {
  const { t } = useTranslation()
  return (
    <section className="tenant-operations__section" aria-labelledby="tenant-slo-title">
      <SectionHeading id="tenant-slo-title" title={t('tenantAdminPage.sloAndQuota')} description={t('tenantAdminPage.sectionDescriptions.slo')} />
      <div className="tenant-slo-grid">
        <dl className="tenant-comparison">
          <div><dt>{t('tenantAdminPage.availability')}</dt><dd><span>{t('tenantAdminPage.target')} {percent(slo.sloAvailability)}</span><strong>{t('tenantAdminPage.actual')} {percent(slo.currentAvailability)}</strong></dd></div>
          <div><dt>P99 {t('tenantAdminPage.latency')}</dt><dd><span>{t('tenantAdminPage.target')} {formatLocaleNumber(slo.sloLatencyP99Ms)} ms</span><strong>{t('tenantAdminPage.actual')} {formatLocaleNumber(slo.latencyP99Ms)} ms</strong></dd></div>
          <div><dt>{t('tenantAdminPage.errorBudget')}</dt><dd><strong>{percent(slo.errorBudgetRemaining)}</strong></dd></div>
        </dl>
        <div className="tenant-quota">
          <div><span>{t('tenantAdminPage.requestUsage')}</span><strong>{formatLocaleNumber(quota.usage.requests)} / {formatLocaleNumber(quota.quota.maxRequestsPerMonth)}</strong><progress max={100} value={Math.min(100, quota.requestUsagePercent)} /></div>
          <div><span>{t('tenantAdminPage.tokenUsage')}</span><strong>{formatLocaleNumber(quota.usage.tokens)} / {formatLocaleNumber(quota.quota.maxTokensPerMonth)}</strong><progress max={100} value={Math.min(100, quota.tokenUsagePercent)} /></div>
        </div>
      </div>
    </section>
  )
}

export interface TenantAdminManagerProps { tenantId?: string; embedded?: boolean }

export function TenantAdminManager({ tenantId: initialTenantId, embedded = false }: TenantAdminManagerProps = {}) {
  const { t } = useTranslation()
  const data = useTenantAdminData(initialTenantId)
  const alertColumns = [
    { key: 'severity', header: t('tenantAdminPage.severity'), responsivePriority: 1, render: (row: TenantAlertResponse) => <span className={alertSeverityTone(row.severity) ? `tenant-alert-severity is-${alertSeverityTone(row.severity)}` : 'tenant-alert-severity'}>{alertSeverityLabel(t, row.severity)}</span> },
    { key: 'message', header: t('tenantAdminPage.message'), responsivePriority: 1, render: (row: TenantAlertResponse) => <InfoTooltip content={row.message}><span className="text-truncate">{row.message}</span></InfoTooltip> },
    { key: 'status', header: t('common.status'), responsivePriority: 1, render: (row: TenantAlertResponse) => alertStatusLabel(t, row.status) },
    { key: 'firedAt', header: t('tenantAdminPage.fired'), responsivePriority: 2, render: (row: TenantAlertResponse) => formatDateTime(row.firedAt) },
  ]

  return (
    <div className={embedded ? 'tenant-admin-workspace' : 'page tenant-admin-workspace'}>
      {embedded ? (
        <header className="tenant-operations__header">
          <div><h2>{t('tenantsPage.operationsTitle')}</h2><p>{t('tenantAdminPage.loadDashboardsHint')}</p></div>
          {!data.isManagerMode && data.overview && !data.error ? <div className="tenant-operations__header-actions"><button className="btn btn-secondary" onClick={() => void data.handleExportExecutions()} disabled={data.exporting}>{t('tenantAdminPage.exportExecutions')}</button><button className="btn btn-secondary" onClick={() => void data.handleExportTools()} disabled={data.exporting}>{t('tenantAdminPage.exportToolCalls')}</button></div> : null}
        </header>
      ) : <PageHeader title={t('nav.tenantAdmin')} description={<span className="text-with-hint"><span>{t('tenantAdminPage.loadDashboardsHint')}</span><HelpHint label={t('tenantAdminPage.help.analytics')} placement="bottom" /></span>} actions={!data.isManagerMode && data.overview && !data.error ? <><button className="btn btn-secondary" onClick={() => void data.handleExportExecutions()} disabled={data.exporting}>{t('tenantAdminPage.exportExecutions')}</button><button className="btn btn-secondary" onClick={() => void data.handleExportTools()} disabled={data.exporting}>{t('tenantAdminPage.exportToolCalls')}</button></> : undefined} />}

      <section className="tenant-scope" aria-labelledby="tenant-scope-title">
        <div><h3 id="tenant-scope-title">{t('tenantAdminPage.tenantScope')}</h3><p>{t('tenantAdminPage.scopeDescription')}</p></div>
        <div className="tenant-scope__fields">
          <label><span className="text-with-hint"><span>{t('tenantAdminPage.tenantId')}</span><HelpHint label={t('tenantAdminPage.help.tenantId')} placement="bottom" /></span><input id="tenant-operations-id" aria-label={t('tenantAdminPage.tenantId')} value={data.tenantId} onChange={(event) => data.setTenantId(event.target.value)} /></label>
          <label><span>{t('tenantAdminPage.from')}</span><input id="tenant-operations-from" type="datetime-local" value={data.fromLocal} onChange={(event) => data.setFromLocal(event.target.value)} /></label>
          <label><span>{t('tenantAdminPage.to')}</span><input id="tenant-operations-to" type="datetime-local" value={data.toLocal} onChange={(event) => data.setToLocal(event.target.value)} /></label>
          <button className="btn btn-primary" onClick={data.loadAll} disabled={data.loading}>{data.loading ? <LoadingSpinner size="sm" /> : t('tenantAdminPage.loadDashboards')}</button>
        </div>
      </section>

      {data.error ? <section className="tenant-operations__load-error" role="alert"><div><strong>{t('tenantAdminPage.loadErrorTitle')}</strong><p>{t('tenantAdminPage.loadErrorDescription')}</p></div><button className="btn btn-sm btn-secondary" onClick={data.loadAll}>{t('common.retry')}</button><details><summary>{t('common.technicalDetails')}</summary><code>{data.error}</code></details></section> : null}

      {!data.hasRequested ? <EmptyState message={t('tenantAdminPage.selectScope')} description={t('tenantAdminPage.selectScopeDescription')} /> : data.loading && !data.overview ? <div className="tenant-operations__loading"><LoadingSpinner /><span>{t('common.loading')}</span></div> : (
        <div className="tenant-operations">
          {data.overview ? <section className="tenant-operations__summary" aria-labelledby="tenant-summary-title"><SectionHeading id="tenant-summary-title" title={t('tenantAdminPage.overview')} description={t('tenantAdminPage.sectionDescriptions.overview')} /><dl className="tenant-metrics"><Metric label={t('tenantAdminPage.totalRequests')} value={formatLocaleNumber(data.overview.totalRequests)} /><Metric label={t('tenantAdminPage.successRate')} value={percent(data.overview.successRate)} /><Metric label={t('tenantAdminPage.avgResponseTime')} value={`${formatLocaleNumber(data.overview.avgResponseTimeMs)} ms`} /><Metric label={t('tenantAdminPage.responseExperience')} value={data.overview.apdexScore.toFixed(2)} /><Metric label={t('tenantAdminPage.totalCost')} value={money(data.overview.monthlyCost)} /><Metric label={t('tenantAdminPage.alerts')} value={formatLocaleNumber(data.overview.activeAlerts)} /></dl></section> : null}
          {data.usage ? <UsageSection data={data.usage} /> : null}
          {data.quality ? <QualitySection data={data.quality} /> : null}
          {data.tools ? <ToolsSection data={data.tools} /> : null}
          {data.cost ? <CostSection data={data.cost} /> : null}
          {data.slo && data.quota ? <SloAndQuotaSection slo={data.slo} quota={data.quota} /> : null}
          {data.alerts ? <section className="tenant-operations__section" aria-labelledby="tenant-alerts-title"><SectionHeading id="tenant-alerts-title" title={t('tenantAdminPage.alerts')} description={t('tenantAdminPage.sectionDescriptions.alerts')} />{data.alerts.length === 0 ? <p className="tenant-operations__healthy">{t('tenantAdminPage.noActiveAlerts')}</p> : <DataTable columns={alertColumns} data={data.alerts} keyFn={(row) => row.id} tableId="tenant-analytics-alerts" urlStateKey="tenant-analytics" exportable={{ filename: 'tenant-analytics-alerts' }} />}</section> : null}
        </div>
      )}
    </div>
  )
}

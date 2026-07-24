import './dashboard.css'
import { lazy, Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PageHeader, SectionErrorBoundary, SkeletonCard, SkeletonChart, WorkspaceUnavailable } from '../../../shared/ui'
import { usePageHelp } from '../../../shared/lib/usePageHelp'
import { useIssueCenterSnapshot } from '../../issues'
import { useRoleVisibility } from '../../workspace/RoleVisibilityProvider'
import { useFeatureAvailability } from '../../capabilities'
import { DoctorBanner } from '../../doctor'
import { ReleaseOperationsSummary } from '../../release-operations'
import { useDashboardData } from '../useDashboardData'
import { DashboardHealthBar } from './DashboardHealthBar'
import { DashboardStatCards, DashboardStatCardsSkeleton } from './DashboardStatCards'
import { DashboardActionCards } from './DashboardActionCards'
import { DashboardInfraPanel } from './DashboardInfraPanel'
import { DashboardCostAlertPanel } from './DashboardCostAlertPanel'
import { EmployeeValueModal } from './EmployeeValueModal'

const OperationalSignalsModal = lazy(() =>
  import('./OperationalSignalsModal').then((module) => ({ default: module.OperationalSignalsModal })),
)

function parseMetricNames(raw: string): string[] {
  return [...new Set(raw.split(',').map((name) => name.trim()).filter(Boolean))]
}

export function DashboardView() {
  const { t } = useTranslation()
  void t('dashboardPage.help', { returnObjects: true })
  usePageHelp({ helpKey: 'dashboardPage.help' })
  const { effectiveRole } = useRoleVisibility()
  const { isDurable } = useFeatureAvailability()
  const { data: issueSnapshot } = useIssueCenterSnapshot()
  const isDeveloperMode = effectiveRole !== 'ADMIN_MANAGER'
  const [metricFilterOverride, setMetricFilterOverride] = useState<string | null>(null)
  const [customMetricNames, setCustomMetricNames] = useState<string[] | undefined>()
  const [employeeValueOpen, setEmployeeValueOpen] = useState(false)
  const [operationalSignalsOpen, setOperationalSignalsOpen] = useState(false)

  const {
    data,
    metricNames,
    platformReadiness,
    reactorConnection,
    projectConnections,
    extraMcpServers,
    isLoading,
    isFetching,
    error,
    errorHint,
    refetch,
    dataUpdatedAt,
  } = useDashboardData(customMetricNames, operationalSignalsOpen)

  const metricFilterRaw = metricFilterOverride ?? (metricNames.length > 0 ? metricNames.slice(0, 8).join(', ') : '')
  const connectedCount = data?.mcp.statusCounts.CONNECTED ?? 0

  function handleApplyMetrics() {
    const selectedNames = parseMetricNames(metricFilterRaw)
    setCustomMetricNames(selectedNames.length > 0 ? selectedNames : undefined)
  }

  function handleResetMetrics() {
    setMetricFilterOverride(null)
    setCustomMetricNames(undefined)
  }

  return (
    <div className="page">
      {!error && <DoctorBanner />}
      <PageHeader
        title={t('dashboard.todayTitle')}
        description={t('dashboard.todayDescription')}
        actions={isDeveloperMode && data ? (
          <>
            <button className="btn btn-secondary btn-sm" onClick={() => setEmployeeValueOpen(true)}>{t('dashboard.actions.employeeValue')}</button>
            <button className="btn btn-secondary btn-sm" onClick={() => setOperationalSignalsOpen(true)}>{t('dashboard.actions.operationalSignals')}</button>
          </>
        ) : undefined}
      />
      {isDurable === false && (
        <div className="alert alert-info" role="status">
          <span className="alert-message">{t('dashboard.localModeNotice')}</span>
        </div>
      )}

      {isLoading ? (
        <>
          <SkeletonCard height={56} />
          <div style={{ marginTop: 'var(--space-4)' }}><SkeletonCard height={160} /></div>
          <div style={{ marginTop: 'var(--space-4)' }}><DashboardStatCardsSkeleton /></div>
          <div style={{ marginTop: 'var(--space-4)' }}><SkeletonChart height={240} /></div>
        </>
      ) : error && !data ? (
        <WorkspaceUnavailable
          title={t('dashboard.unavailable.title')}
          description={errorHint ?? t('dashboard.unavailable.description')}
          retryLabel={t('dashboard.unavailable.retry')}
          retryingLabel={t('dashboard.unavailable.retrying')}
          onRetry={refetch}
          isRetrying={isFetching}
          secondaryAction={{ label: t('dashboard.unavailable.openHealth'), to: '/health' }}
          guide={{ title: t('dashboard.unavailable.technical'), technicalDetail: error }}
        />
      ) : data && (
        <>
          <DashboardHealthBar readiness={platformReadiness} issueSnapshot={issueSnapshot} mcpConnected={connectedCount} mcpTotal={data.mcp.total} groundedPercent={data.employeeValue?.groundedRatePercent ?? 0} updatedAt={dataUpdatedAt} />
          {((issueSnapshot?.criticalCount ?? 0) > 0 || (issueSnapshot?.warningCount ?? 0) > 0 || data.approvals.pendingCount > 0 || data.responseTrust.outputGuardRejected > 0 || data.responseTrust.outputGuardModified > 0) && (
            <DashboardActionCards issueSnapshot={issueSnapshot} pendingApprovals={data.approvals.pendingCount} guardRejected={data.responseTrust.outputGuardRejected} guardModified={data.responseTrust.outputGuardModified} />
          )}
          <ReleaseOperationsSummary readiness={data.releaseReadiness} />
          <DashboardStatCards data={data} issueSnapshot={issueSnapshot} connectedCount={connectedCount} />
          <SectionErrorBoundary name="dashboard-cost-alert"><DashboardCostAlertPanel /></SectionErrorBoundary>
          <DashboardInfraPanel statusCounts={data.mcp.statusCounts} reactorConnection={reactorConnection} projectConnections={projectConnections} extraMcpServers={extraMcpServers} metrics={data.metrics} trustEvents={data.recentTrustEvents} generatedAt={data.generatedAt} />
        </>
      )}

      <EmployeeValueModal open={employeeValueOpen} onClose={() => setEmployeeValueOpen(false)} employeeValue={data?.employeeValue} />
      {operationalSignalsOpen && (
        <Suspense fallback={null}>
          <OperationalSignalsModal
            open={operationalSignalsOpen}
            onClose={() => setOperationalSignalsOpen(false)}
            metrics={data?.metrics ?? []}
            metricFilterRaw={metricFilterRaw}
            metricNames={metricNames}
            onMetricFilterChange={setMetricFilterOverride}
            onApplyMetrics={handleApplyMetrics}
            onResetMetrics={handleResetMetrics}
            refreshing={isFetching}
            responseTrust={data?.responseTrust ?? { unverifiedResponses: 0, outputGuardRejected: 0, outputGuardModified: 0, boundaryFailures: 0 }}
            schedulerBacklog={data?.scheduler.attentionBacklog ?? 0}
            pendingApprovals={data?.approvals.pendingCount ?? 0}
            unverifiedResponses={data?.responseTrust.unverifiedResponses ?? 0}
            recentExecutions={data?.recentSchedulerExecutions ?? []}
            recentTrustEvents={data?.recentTrustEvents ?? []}
          />
        </Suspense>
      )}
    </div>
  )
}

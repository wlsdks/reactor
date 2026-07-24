import '../../dashboard/ui/dashboard.css'
import './issues.css'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SkeletonChart, SkeletonTable, PageHeader, RefreshButton } from '../../../shared/ui'
import { WorkspaceUnavailable } from '../../../shared/ui/WorkspaceUnavailable'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useIssueCenterSnapshot, useTopologyData, type TopologyData } from '../query'
import type { IssueSeverity } from '../types'
import { SummaryChips } from './SummaryChips'
import { IssueList } from './IssueList'

// Lazy-load SystemTopology to keep @xyflow/react out of the initial IssuesPage chunk.
// @xyflow/react + @xyflow/system together account for the bulk of the page weight,
// so deferring them shrinks IssuesPage and isolates them in a dedicated vendor-flow chunk.
const SystemTopology = lazy(() => import('./SystemTopology'))

// 동적 MCP 서버 이름까지 수용 (예: `clipping-mcp-server`) — SystemTopology 와 타입 일치.
type SourceFilterValue = string | null

const EMPTY_TOPOLOGY: TopologyData = {
  reactor: { status: 'PASS', apiBase: '', missingPaths: [] },
  projects: [],
}

// Issue summaries construct these keys from typed diagnostic IDs in
// `issueCenter.ts`. Keep the complete source-controlled family visible to the
// i18n verifier so an operator-facing detail can never regress to a raw key.
const ISSUE_DYNAMIC_I18N_KEYS = [
  'mcpServers.configReadinessDetails.transportUrlReady',
  'mcpServers.configReadinessDetails.transportCommandReady',
  'mcpServers.configReadinessDetails.transportMissingUrl',
  'mcpServers.configReadinessDetails.transportMissingCommand',
  'mcpServers.configReadinessDetails.adminUrlReady',
  'mcpServers.configReadinessDetails.adminUrlDerived',
  'mcpServers.configReadinessDetails.adminUrlMissing',
  'mcpServers.configReadinessDetails.adminUrlOptional',
  'mcpServers.configReadinessDetails.adminTokenReady',
  'mcpServers.configReadinessDetails.adminTokenMissing',
  'mcpServers.configReadinessDetails.adminTokenPlaceholder',
  'mcpServers.configReadinessDetails.adminTokenOptional',
  'mcpServers.configReadinessDetails.adminHmacReady',
  'mcpServers.configReadinessDetails.adminHmacMissing',
  'mcpServers.configReadinessDetails.adminHmacPlaceholder',
  'mcpServers.configReadinessDetails.adminHmacDisabled',
  'mcpServers.configReadinessDetails.timeoutsReady',
  'mcpServers.configReadinessDetails.timeoutsDefault',
  'mcpServers.configReadinessDetails.timeoutsNeedReview',
  'mcpServers.configReadinessDetails.autoConnectEnabled',
  'mcpServers.configReadinessDetails.autoConnectDisabled',
  'mcpServers.policySignalDetails.dynamicModeEnabled',
  'mcpServers.policySignalDetails.dynamicModeDisabled',
  'mcpServers.policySignalDetails.dynamicModeUnknown',
  'mcpServers.policySignalDetails.coverageScoped',
  'mcpServers.policySignalDetails.coveragePartiallyScoped',
  'mcpServers.policySignalDetails.coverageOpenAll',
  'mcpServers.policySignalDetails.previewReadsBlocked',
  'mcpServers.policySignalDetails.previewReadsAllowed',
  'mcpServers.policySignalDetails.previewWritesBlocked',
  'mcpServers.policySignalDetails.previewWritesAllowed',
  'mcpServers.policySignalDetails.directUrlLoadsBlocked',
  'mcpServers.policySignalDetails.directUrlLoadsAllowed',
  'mcpServers.policySignalDetails.publishedOnlyEnforced',
  'mcpServers.policySignalDetails.publishedScopeOpen',
  'mcpServers.policySignalDetails.dynamicPolicyInSync',
  'mcpServers.policySignalDetails.dynamicPolicyDrifted',
  'mcpServers.policySignalDetails.dynamicSnapshotMissing',
  'mcpServers.policySignalDetails.dynamicSnapshotNotUsed',
] as const

export function IssueCenterManager() {
  const { t } = useTranslation()
  void ISSUE_DYNAMIC_I18N_KEYS
  // Issue titles/messages are selected from typed diagnostics at runtime.
  // Keep their static keys visible to the i18n completeness sensor.
  void t('issuesPage.titles.accessPolicy')
  void t('issuesPage.titles.approvalRequest')
  void t('issuesPage.titles.configReadiness')
  void t('issuesPage.titles.preflight')
  void t('issuesPage.titles.schedulerJob')
  void t('issuesPage.titles.serverDetail')
  void t('issuesPage.titles.serverDisconnected')
  void t('issuesPage.messages.detailUnavailable')
  void t('issuesPage.messages.policyUnavailable')
  void t('issuesPage.messages.preflightUnavailable')
  const scrollTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null)

  const [severityFilter, setSeverityFilter] = useState<IssueSeverity | null>(null)
  const [sourceFilter, setSourceFilter] = useState<SourceFilterValue>(null)
  const [topologyOpen, setTopologyOpen] = useState(false)
  const snapshotQuery = useIssueCenterSnapshot()
  const topologyQuery = useTopologyData(topologyOpen)

  const { data, isLoading, error, refetch, isFetching } = snapshotQuery
  useEffect(() => {
    return () => {
      if (scrollTimerRef.current !== null) {
        window.clearTimeout(scrollTimerRef.current)
      }
    }
  }, [])

  function handleNodeClick(source: string | null) {
    setSourceFilter(source)
    if (source) {
      if (scrollTimerRef.current !== null) {
        window.clearTimeout(scrollTimerRef.current)
      }
      scrollTimerRef.current = window.setTimeout(() => {
        scrollTimerRef.current = null
        document.querySelector('.issue-group')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 50)
    }
  }

  function handleCenterClick() {
    setSourceFilter(null)
    setSeverityFilter(null)
  }

  return (
    <div className="page">
      <PageHeader
        title={t('issuesPage.pageTitle')}
        description={t('issuesPage.pageSubtitle')}
        actions={!error ? <RefreshButton onRefresh={() => { void refetch() }} isFetching={isFetching} /> : undefined}
      />

      {isLoading && !data ? (
        <SkeletonTable rows={8} columns={3} />
      ) : error ? (
        <WorkspaceUnavailable
          title={t('issuesPage.unavailableTitle')}
          description={t('issuesPage.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refetch}
          isRetrying={isFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('issuesPage.recoveryGuideTitle'),
            steps: [
              t('issuesPage.recoveryCheckAccount'),
              t('issuesPage.recoveryCheckConnection'),
              t('issuesPage.recoveryRetry'),
            ],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: getErrorMessage(error),
          }}
        />
      ) : data ? (
        <div className="issues-workspace">
          <SummaryChips
            snapshot={data}
            sourceFilter={sourceFilter}
            activeSeverity={severityFilter}
            onSeverityChange={setSeverityFilter}
          />
          <IssueList
            items={data.items}
            sourceFilter={sourceFilter}
            severityFilter={severityFilter}
          />
          <details
            className="issues-topology-disclosure"
            open={topologyOpen}
            onToggle={(event) => setTopologyOpen(event.currentTarget.open)}
          >
            <summary>
              <span>{t('issuesPage.topologyDisclosure.title')}</span>
              <span>{t('issuesPage.topologyDisclosure.description')}</span>
            </summary>
            {topologyOpen && (
              <Suspense fallback={<SkeletonChart height={220} />}>
                <SystemTopology
                  snapshot={data}
                  topology={topologyQuery.data ?? EMPTY_TOPOLOGY}
                  activeSource={sourceFilter}
                  onNodeClick={handleNodeClick}
                  onCenterClick={handleCenterClick}
                />
              </Suspense>
            )}
          </details>
        </div>
      ) : null}
    </div>
  )
}

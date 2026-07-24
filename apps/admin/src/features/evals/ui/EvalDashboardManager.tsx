import './EvalDashboardManager.css'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CloudUpload, Database, RefreshCw } from 'lucide-react'
import {
  CopyButton,
  HelpHint,
  OperationButton,
  ProductCapabilityBoundaryFlowList,
  ReleaseReportLink,
  ReleaseReportList,
  WorkspaceUnavailable,
} from '../../../shared/ui'
import { SkeletonTable } from '../../../shared/ui/Skeleton'
import { EmptyState } from '../../../shared/ui/EmptyState'
import { SectionErrorBoundary } from '../../../shared/ui/SectionErrorBoundary'
import { DataTable } from '../../../shared/ui/DataTable'
import { PageHeader } from '../../../shared/ui/PageHeader'
import { formatDateTime } from '../../../shared/lib/formatters'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { usePageHelp } from '../../../shared/lib/usePageHelp'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { isForbiddenError } from '../../../shared/lib/isForbiddenError'
import { useToastStore } from '../../../shared/store/toast.store'
import {
  hasEvidenceEntries,
  hasLangsmithSyncEvidence,
} from '../../../shared/lib/releaseReadinessEvidence'
import { resolveReleaseNextActionCommand } from '../../../shared/lib/releaseNextActionCommand'
import type { Column } from '../../../shared/ui/DataTable'
import type { EvalRun, LangSmithPersistedEvalSyncResult } from '../types'
import type {
  DashboardReleaseNextAction,
  DashboardReleaseReadinessSummary,
} from '../../dashboard/types'
import {
  getEvalRuns,
  getEvalPassRate,
  getPersistedEvalCases,
  syncPersistedEvalCases,
} from '../api'
import { getDashboard } from '../../dashboard/api'
import { EvalScoreTrendChart } from './EvalScoreTrendChart'
import {
  RELEASE_A2A_PROTOCOL_PATH,
  RELEASE_EVAL_REGRESSION_ANCHOR_ID,
  RELEASE_LANGSMITH_SYNC_ANCHOR_ID,
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_SLACK_GATEWAY_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
  releaseReportBelongsToGate,
} from '../../../shared/releaseWorkflow'

function listSummary(values: string[] | null | undefined): string {
  return values?.filter(Boolean).join(', ') ?? ''
}

function isNonEmptyString(value: string | null | undefined): value is string {
  return Boolean(value)
}

function recordSummary(values: Record<string, number> | null | undefined): string {
  return Object.entries(values ?? {})
    .map(([key, count]) => `${key}: ${count}`)
    .join(', ')
}

function formatEvidenceValue(value: boolean | number | string | string[] | null): string {
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return String(value)
  return value ?? ''
}

function evidenceMapSummary(
  values: Record<string, boolean | number | string | string[] | null> | null | undefined,
): string {
  return Object.entries(values ?? {})
    .map(([key, value]) => `${key}: ${formatEvidenceValue(value)}`)
    .filter((value) => !value.endsWith(': '))
    .join(', ')
}

function renderLinkedReports(values: string[] | null | undefined, includeStep = false) {
  return <ReleaseReportList reports={values} includeStep={includeStep} />
}

function formatEnvAnyOf(groups: string[][] | null | undefined): string {
  return groups
    ?.filter((group) => group.length > 0)
    .map((group) => group.join(' or '))
    .join('; ') ?? ''
}

function formatEvidence(value: Record<string, unknown> | null | undefined): string {
  if (!value || Object.keys(value).length === 0) return ''
  return JSON.stringify(value, null, 2)
}

function coverageSummary(sourceCaseIds: string[] | null | undefined, targetCaseIds: string[] | null | undefined): string {
  const source = sourceCaseIds?.filter(Boolean) ?? []
  if (source.length === 0) return ''
  const target = new Set(targetCaseIds?.filter(Boolean) ?? [])
  const covered = source.filter((caseId) => target.has(caseId))
  return `${covered.length}/${source.length}`
}

function splitCoverage(sourceCaseIds: string[] | null | undefined, targetCaseIds: string[] | null | undefined) {
  const source = sourceCaseIds?.filter(Boolean) ?? []
  const target = new Set(targetCaseIds?.filter(Boolean) ?? [])

  return {
    covered: source.filter((caseId) => target.has(caseId)),
    missing: source.filter((caseId) => !target.has(caseId)),
  }
}

function smokeGateStatus(blockingReports: string[], gate: 'slack' | 'a2a' | 'provider') {
  return blockingReports.some((report) => releaseReportBelongsToGate(report, gate)) ? 'WARN' : 'DISABLED'
}

function actionStateClassName(state: string): string {
  const normalized = state.trim().toLowerCase()
  if (normalized === 'ready' || normalized === 'passed') return 'eval-langsmith-panel__action-state--ready'
  if (normalized === 'blocked' || normalized === 'failed') return 'eval-langsmith-panel__action-state--blocked'
  return 'eval-langsmith-panel__action-state--pending'
}

function InlineStatus({ status, label }: { status: string; label: string }) {
  return (
    <span className="eval-inline-status" data-status={status.toLowerCase()} title={label}>
      <span aria-hidden="true" />
      {label}
    </span>
  )
}

function isPermissionFailure(error: unknown): boolean {
  if (isForbiddenError(error)) return true

  const message = getErrorMessage(error).toLowerCase()
  return [
    '403',
    'forbidden',
    'permission',
    'access required',
    '권한',
  ].some((indicator) => message.includes(indicator))
}

function resolveLangsmithActionHandoffs(
  readiness: DashboardReleaseReadinessSummary | null | undefined,
) {
  const actionStates = readiness?.nextActionStates ?? {}
  const readyActionIds = new Set(readiness?.readyNextActionIds ?? [])
  const handoffs = new Map<string, {
    action: DashboardReleaseNextAction
    command: string | null
    itemName: string | null
    state: string | null
  }>()

  for (const item of readiness?.items ?? []) {
    const itemName = item.name ?? null
    const itemBelongsToLangsmith = itemName ? releaseReportBelongsToGate(itemName, 'langsmith') : false
    for (const action of item.nextActions ?? []) {
      const command = resolveReleaseNextActionCommand(action)
      const id = action.id?.trim() ?? ''
      const actionText = [
        id,
        action.label,
        command,
      ].filter(Boolean).join(' ').toLowerCase()
      const actionBelongsToLangsmith =
        itemBelongsToLangsmith
        || actionText.includes('langsmith')
        || actionText.includes('eval')
        || actionText.includes('dataset')
      if (!actionBelongsToLangsmith) continue

      const key = id || `${itemName ?? 'release'}:${action.label ?? ''}:${command ?? ''}`
      if (!key || handoffs.has(key)) continue
      handoffs.set(key, {
        action,
        command,
        itemName,
        state: id ? actionStates[id] ?? (readyActionIds.has(id) ? 'ready' : null) : null,
      })
    }
  }

  return Array.from(handoffs.values())
}

function resolveLangsmithReadinessItem(
  readiness: DashboardReleaseReadinessSummary | null | undefined,
) {
  return readiness?.items?.find((item) =>
    item.name ? releaseReportBelongsToGate(item.name, 'langsmith') : false,
  ) ?? null
}

export function EvalDashboardManager() {
  const { t } = useTranslation()
  const [datasetName, setDatasetName] = useState('reactor-admin-persisted-eval-cases')
  const [liveSyncResult, setLiveSyncResult] = useState<LangSmithPersistedEvalSyncResult | null>(null)
  void t('evalsPage.help', { returnObjects: true })
  usePageHelp({ helpKey: 'evalsPage.help' })

  const {
    data: runs,
    isLoading: runsLoading,
    isFetching: runsFetching,
    isError: runsError,
    error: runsErrorValue,
    refetch: refetchRuns,
  } = useQuery({
    queryKey: queryKeys.evals.list(),
    queryFn: () => getEvalRuns(30),
  })

  const {
    data: passRateData,
    isFetching: passRateFetching,
    refetch: refetchPassRate,
  } = useQuery({
    queryKey: queryKeys.evals.summary(),
    queryFn: () => getEvalPassRate(30),
  })

  const {
    data: persistedCases = [],
    isLoading: persistedCasesLoading,
    isFetching: persistedCasesFetching,
    error: persistedCasesErrorValue,
    refetch: refetchPersistedCases,
  } = useQuery({
    queryKey: queryKeys.evals.cases(),
    queryFn: getPersistedEvalCases,
  })

  const {
    data: dashboard,
    isLoading: dashboardLoading,
    isFetching: dashboardFetching,
    error: dashboardErrorValue,
    refetch: refetchDashboard,
  } = useQuery({
    queryKey: queryKeys.dashboard.main(['reactor.release.readiness']),
    queryFn: () => getDashboard(['reactor.release.readiness']),
  })

  const syncMutation = useMutation({
    mutationFn: () => syncPersistedEvalCases(datasetName.trim()),
    onSuccess: async (result) => {
      setLiveSyncResult(result)
      await refetchDashboard()
      useToastStore.getState().addToast({
        type: 'success',
        message: t('evalsPage.langsmith.liveSyncSuccess', { count: result.examples }),
      })
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({ type: 'error', message: getErrorMessage(error) })
    },
  })

  const primaryDataError = runsErrorValue ?? persistedCasesErrorValue ?? dashboardErrorValue
  const primaryDataLoading = runsLoading || persistedCasesLoading || dashboardLoading
  const primaryDataRefreshing = runsFetching || persistedCasesFetching || passRateFetching || dashboardFetching
  const primaryDataIsForbidden = isPermissionFailure(primaryDataError)
  const refetchPrimaryData = async () => {
    await Promise.all([
      refetchRuns(),
      refetchPassRate(),
      refetchPersistedCases(),
      refetchDashboard(),
    ])
  }

  if (primaryDataLoading) {
    return (
      <div className="page">
        <PageHeader
          title={t('evalsPage.title')}
          description={t('evalsPage.description')}
        />
        <SkeletonTable rows={4} columns={3} />
      </div>
    )
  }

  if (primaryDataError) {
    return (
      <div className="page">
        <PageHeader
          title={t('evalsPage.title')}
          description={t('evalsPage.description')}
        />
        <WorkspaceUnavailable
          title={t(primaryDataIsForbidden ? 'evalsPage.permissionUnavailableTitle' : 'evalsPage.unavailableTitle')}
          description={t(primaryDataIsForbidden ? 'evalsPage.permissionUnavailableDescription' : 'evalsPage.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refetchPrimaryData}
          isRetrying={primaryDataRefreshing}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('evalsPage.recoveryTitle'),
            steps: primaryDataIsForbidden
              ? [t('evalsPage.recoveryPermission'), t('evalsPage.recoveryRetry')]
              : [t('evalsPage.recoveryConnection'), t('evalsPage.recoveryRetry')],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: getErrorMessage(primaryDataError),
          }}
        />
      </div>
    )
  }

  // Compute summary from runs
  const totalRuns = runs?.length ?? 0
  const runDisplayNames = new Map(
    (runs ?? []).map((run, index) => [
      run.evalRunId,
      t('evalsPage.runLabel', { number: index + 1 }),
    ]),
  )
  const releaseReadiness = dashboard?.releaseReadiness ?? null
  const langsmithSync = releaseReadiness?.langsmithSync ?? null
  const readinessCaseIds = new Set(langsmithSync?.caseIds?.filter(Boolean) ?? [])
  const readinessMetadataCaseIds = new Set(langsmithSync?.metadataCaseIds?.filter(Boolean) ?? [])
  const liveSyncAggregated = Boolean(
    liveSyncResult
    && liveSyncResult.caseIds.length > 0
    && liveSyncResult.caseIds.every((caseId) => readinessCaseIds.has(caseId))
    && liveSyncResult.metadataCaseIds.every((caseId) => readinessMetadataCaseIds.has(caseId)),
  )
  const feedbackReviewQueue = releaseReadiness?.feedbackReviewQueue ?? null
  const productCapabilityBoundary = releaseReadiness?.productCapabilityBoundary ?? null
  const tagRecommendation = releaseReadiness?.tagRecommendation ?? null
  const releaseReadinessCommand = tagRecommendation?.releaseReadinessCommand ?? null
  const langsmithReadinessItem = resolveLangsmithReadinessItem(releaseReadiness)
  const splitSummary = Object.entries(langsmithSync?.splitCounts ?? {})
    .map(([split, count]) => `${split}: ${count}`)
    .join(', ')
  const exampleIdsSummary = listSummary(langsmithSync?.exampleIds)
  const caseIdsSummary = listSummary(langsmithSync?.caseIds)
  const metadataCaseIdsSummary = listSummary(langsmithSync?.metadataCaseIds)
  const feedbackPromotedCaseIdsSummary = listSummary(feedbackReviewQueue?.caseIds)
  const feedbackReviewTagsSummary = listSummary(feedbackReviewQueue?.reviewTags)
  const feedbackExpectedCitationCountsSummary = recordSummary(feedbackReviewQueue?.expectedCitationCounts)
  const feedbackPromotionProvenance = feedbackReviewQueue?.promotionProvenance
    ?.filter((item) => item && Object.values(item).some(Boolean)) ?? []
  const feedbackSyncRemediationCommand = feedbackPromotionProvenance
    .map((item) => item.remediationCommand)
    .find(isNonEmptyString) ?? null
  const sdkContractFieldsSummary = formatEvidence(langsmithSync?.sdkContractFields)
  const exampleContractSummary = formatEvidence(langsmithSync?.exampleContract)
  const feedbackLangsmithCoverage = coverageSummary(feedbackReviewQueue?.caseIds, langsmithSync?.caseIds)
  const feedbackMetadataCoverage = coverageSummary(feedbackReviewQueue?.caseIds, langsmithSync?.metadataCaseIds)
  const feedbackDiagnosticsCoverage = coverageSummary(
    feedbackPromotionProvenance.map((item) => item.caseId).filter(isNonEmptyString),
    feedbackPromotionProvenance
      .filter((item) => item.diagnosticsApi)
      .map((item) => item.caseId)
      .filter(isNonEmptyString),
  )
  const { covered: feedbackSyncedCases, missing: feedbackUnsyncedCases } = splitCoverage(
    feedbackReviewQueue?.caseIds,
    langsmithSync?.caseIds,
  )
  const { missing: feedbackMetadataMissingCases } = splitCoverage(
    feedbackReviewQueue?.caseIds,
    langsmithSync?.metadataCaseIds,
  )
  const hasFeedbackCoverage =
    (feedbackReviewQueue?.caseIds?.filter(Boolean).length ?? 0) > 0
  const hasFeedbackSyncRemediation =
    feedbackUnsyncedCases.length > 0 || feedbackMetadataMissingCases.length > 0
  const langsmithContractChecks = [
    {
      ok: Boolean(langsmithSync?.datasetName),
      label: t('evalsPage.langsmith.dataset'),
    },
    {
      ok: (langsmithSync?.exampleCount ?? 0) > 0 && hasEvidenceEntries(langsmithSync?.exampleIds),
      label: t('evalsPage.langsmith.examples'),
    },
    {
      ok: (langsmithSync?.caseCount ?? 0) > 0 && hasEvidenceEntries(langsmithSync?.caseIds),
      label: t('evalsPage.langsmith.caseIds'),
    },
    {
      ok: hasEvidenceEntries(langsmithSync?.metadataCaseIds),
      label: t('evalsPage.langsmith.metadataCaseIds'),
    },
    {
      ok: Object.keys(langsmithSync?.splitCounts ?? {}).length > 0,
      label: t('evalsPage.langsmith.splits'),
    },
    {
      ok: Boolean(langsmithSync?.sdkContract),
      label: t('evalsPage.langsmith.sdkContract'),
    },
    {
      ok: Boolean(sdkContractFieldsSummary),
      label: t('evalsPage.langsmith.sdkContractFields'),
    },
    {
      ok: langsmithSync?.secretFree === true,
      label: t('evalsPage.langsmith.secretScan'),
    },
    {
      ok: Boolean(exampleContractSummary),
      label: t('evalsPage.langsmith.exampleContract'),
    },
  ]
  const missingLangsmithContracts = langsmithContractChecks
    .filter((item) => !item.ok)
    .map((item) => item.label)
  const langsmithSyncReady = hasLangsmithSyncEvidence(langsmithSync)
  const requiredReports = releaseReadiness?.requiredReports ?? []
  const missingReports = releaseReadiness?.missingReports ?? []
  const blockingReports = releaseReadiness?.blockingReports ?? []
  const requiredReportLinks = renderLinkedReports(requiredReports)
  const missingReportLinks = renderLinkedReports(missingReports)
  const blockingReportLinks = renderLinkedReports(blockingReports)
  const unblockBlockingReportLinks = renderLinkedReports(blockingReports, true)
  const requiredEnvAnyOf = formatEnvAnyOf(releaseReadiness?.requiredEnvAnyOf)
  const missingEnvAnyOf = listSummary(releaseReadiness?.missingEnvAnyOf)
  const recommendedEnv = listSummary(releaseReadiness?.recommendedEnv)
  const langsmithActionHandoffs = resolveLangsmithActionHandoffs(releaseReadiness)
  const hasLangsmithUnblockHandoff =
    Boolean(
      requiredEnvAnyOf
      || missingEnvAnyOf
      || blockingReports.length > 0
      || releaseReadinessCommand
      || langsmithActionHandoffs.length > 0
    )
  const evalWorkflowSteps = [
    {
      id: 'regression-suite',
      displayNumber: 1,
      href: `#${RELEASE_EVAL_REGRESSION_ANCHOR_ID}`,
      label: t('evalsPage.langsmith.workflowRegression'),
      description: t('evalsPage.langsmith.workflowRegressionDesc', {
        count: runs?.[0]?.totalCases ?? 0,
      }),
      status: totalRuns > 0 ? 'PASS' : 'FAIL',
    },
    {
      id: 'langsmith-sync',
      displayNumber: 2,
      href: `#${RELEASE_LANGSMITH_SYNC_ANCHOR_ID}`,
      label: t('evalsPage.langsmith.workflowSync'),
      description: t('evalsPage.langsmith.workflowSyncDesc', {
        examples: langsmithSync?.exampleCount ?? 0,
        cases: langsmithSync?.caseCount ?? 0,
      }),
      status: langsmithSyncReady ? 'PASS' : langsmithSync ? 'WARN' : 'DISABLED',
    },
    {
      id: 'readiness-aggregate',
      displayNumber: 3,
      href: RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
      label: t('evalsPage.langsmith.workflowReadiness'),
      description: t('evalsPage.langsmith.workflowReadinessDesc', {
        reports: requiredReports.length,
      }),
      status: missingReports.length === 0 && blockingReports.length === 0 ? 'PASS' : 'WARN',
    },
  ] as const
  const releaseReadinessBadgeStatus = releaseReadiness?.status === 'blocked'
    ? 'FAIL'
    : langsmithSyncReady
      ? 'PASS'
      : langsmithSync
        ? 'WARN'
        : 'DISABLED'
  const liveSmokeChainSteps = [
    {
      id: 'langsmith-sync',
      href: RELEASE_LANGSMITH_SYNC_PATH,
      label: t('evalsPage.langsmith.liveSmokeLangsmith'),
      description: t('evalsPage.langsmith.liveSmokeLangsmithDesc'),
      status: langsmithSyncReady ? 'PASS' : langsmithSync ? 'WARN' : 'DISABLED',
    },
    {
      id: 'slack-workspace',
      href: RELEASE_SLACK_GATEWAY_PATH,
      label: t('evalsPage.langsmith.liveSmokeSlack'),
      description: t('evalsPage.langsmith.liveSmokeSlackDesc'),
      status: smokeGateStatus(blockingReports, 'slack'),
    },
    {
      id: 'a2a-peer',
      href: RELEASE_A2A_PROTOCOL_PATH,
      label: t('evalsPage.langsmith.liveSmokeA2a'),
      description: t('evalsPage.langsmith.liveSmokeA2aDesc'),
      status: smokeGateStatus(blockingReports, 'a2a'),
    },
    {
      id: 'provider-runtime',
      href: RELEASE_WORKFLOW_PATHS_BY_ID.provider,
      label: t('evalsPage.langsmith.liveSmokeProvider'),
      description: t('evalsPage.langsmith.liveSmokeProviderDesc'),
      status: smokeGateStatus(blockingReports, 'provider'),
    },
    {
      id: 'readiness-aggregate',
      href: RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
      label: t('evalsPage.langsmith.liveSmokeReadiness'),
      description: t('evalsPage.langsmith.liveSmokeReadinessDesc'),
      status: missingReports.length === 0 && blockingReports.length === 0 ? 'PASS' : 'WARN',
    },
  ] as const
  const columns: Column<EvalRun>[] = [
    {
      key: 'evalRunId',
      header: t('evalsPage.run'),
      width: '180px',
      responsivePriority: 1,
      render: (row) => (
        <span className="eval-run-id">
          <span>
            {runDisplayNames.get(row.evalRunId)
              ?? t('evalsPage.runLabel', { number: 1 })}
          </span>
          <HelpHint
            title={t('evalsPage.technicalRunId')}
            label={t('evalsPage.technicalRunIdDescription', {
              id: row.evalRunId,
            })}
          />
        </span>
      ),
    },
    {
      key: 'result',
      header: t('evalsPage.result'),
      width: '140px',
      responsivePriority: 1,
      render: (row) => (
        <span className={`eval-run-result ${row.passCount === row.totalCases ? 'is-pass' : 'is-attention'}`}>
          <span className="eval-run-result__dot" aria-hidden="true" />
          {t('evalsPage.passSummary', { passed: row.passCount, total: row.totalCases })}
        </span>
      ),
    },
    {
      key: 'avgScore',
      header: t('evalsPage.avgScore'),
      width: '100px',
      responsivePriority: 2,
      render: (row) => <span className="data-mono">{row.avgScore.toFixed(2)}</span>,
    },
    {
      key: 'totalCost',
      header: t('evalsPage.cost'),
      width: '100px',
      responsivePriority: 3,
      render: (row) => <span className="data-mono">${row.totalCost.toFixed(4)}</span>,
    },
    {
      key: 'startedAt',
      header: t('evalsPage.startedAt'),
      width: '170px',
      responsivePriority: 3,
      render: (row) => <span className="data-mono">{formatDateTime(new Date(row.startedAt).getTime())}</span>,
    },
  ]

  return (
    <div className="page">
      <PageHeader
        title={t('evalsPage.title')}
        description={t('evalsPage.description')}
      />

      <div role="region" aria-label={t('evalsPage.summaryStats')}>
        <dl className="eval-dashboard-stats">
          <div>
            <dt>{t('evalsPage.latestPassRate')}</dt>
            <dd>{runs?.[0] ? `${runs[0].passCount} / ${runs[0].totalCases}` : '-'}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.savedCases')}</dt>
            <dd>{persistedCasesLoading ? '-' : persistedCases.length}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.recentRuns')}</dt>
            <dd>{totalRuns}</dd>
          </div>
        </dl>
      </div>

      {/* Pass rate trend chart */}
      <SectionErrorBoundary name="eval-trend-chart">
        {passRateData && passRateData.length > 1 && (
          <div className="eval-trend-section">
            <EvalScoreTrendChart data={passRateData} />
          </div>
        )}
      </SectionErrorBoundary>

      <section
        id={RELEASE_EVAL_REGRESSION_ANCHOR_ID}
        className="eval-langsmith-panel"
        aria-label={t('evalsPage.langsmith.title')}
      >
        <div className="eval-langsmith-panel__header">
          <div>
            <div className="eval-langsmith-panel__title-row">
              <h2 className="eval-langsmith-panel__title">{t('evalsPage.langsmith.title')}</h2>
              <HelpHint
                title={t('evalsPage.langsmith.help.title')}
                label={t('evalsPage.langsmith.help.description')}
                placement="right"
              />
            </div>
            <p className="eval-langsmith-panel__description">{t('evalsPage.langsmith.description')}</p>
          </div>
          <div className="inline-actions">
            <InlineStatus
              status={releaseReadinessBadgeStatus}
              label={releaseReadiness
                ? t(`common.statuses.${releaseReadinessBadgeStatus}`, { defaultValue: releaseReadinessBadgeStatus })
                : t('evalsPage.langsmith.missing')}
            />
          </div>
        </div>
        <ol
          className="eval-langsmith-panel__workflow"
          aria-label={t('evalsPage.langsmith.workflowLabel')}
        >
          {evalWorkflowSteps.map((step) => {
            const content = (
              <>
                <span className="eval-langsmith-panel__workflow-index" aria-hidden="true">
                  {step.displayNumber}
                </span>
                <span className="eval-langsmith-panel__workflow-copy">
                  <span className="eval-langsmith-panel__workflow-label">{step.label}</span>
                  <span className="eval-langsmith-panel__workflow-description">{step.description}</span>
                </span>
                <span className={`eval-langsmith-panel__workflow-status eval-langsmith-panel__workflow-status--${step.status.toLowerCase()}`}>
                  <span aria-hidden="true" />
                  {t(`common.statuses.${step.status}`, { defaultValue: step.status })}
                </span>
              </>
            )
            return (
              <li key={step.id} className="eval-langsmith-panel__workflow-step">
                {step.href.startsWith('#') ? (
                  <a href={step.href} className="eval-langsmith-panel__workflow-link">
                    {content}
                  </a>
                ) : (
                  <Link to={step.href} className="eval-langsmith-panel__workflow-link">
                    {content}
                  </Link>
                )}
              </li>
            )
          })}
        </ol>
        {productCapabilityBoundary && (
          <details className="eval-langsmith-panel__disclosure">
            <summary>{t('evalsPage.langsmith.productBoundaryFlow')}</summary>
            <ProductCapabilityBoundaryFlowList
              evidence={productCapabilityBoundary.evidence}
              missingEvidence={productCapabilityBoundary.missingEvidence}
              className="eval-langsmith-panel__boundary-flow"
              ariaLabel={t('evalsPage.langsmith.productBoundaryFlow')}
              itemClassName={(item) => `eval-langsmith-panel__boundary-flow-item eval-langsmith-panel__boundary-flow-item--${item.status}`}
              linkClassName="eval-langsmith-panel__boundary-flow-link"
              stepClassName="eval-langsmith-panel__boundary-flow-step"
              copyClassName="eval-langsmith-panel__boundary-flow-copy"
              labelClassName="eval-langsmith-panel__boundary-flow-label"
              evidenceClassName="eval-langsmith-panel__boundary-flow-evidence"
              statusPosition="after-copy"
            />
          </details>
        )}
        <details
          className="eval-langsmith-panel__live-smoke"
          aria-label={t('evalsPage.langsmith.liveSmokeChain')}
        >
          <summary className="eval-langsmith-panel__live-smoke-head">
            <span>{t('evalsPage.langsmith.liveSmokeChain')}</span>
            <span>{t('evalsPage.langsmith.liveSmokeChainDesc')}</span>
          </summary>
          <ol
            className="eval-langsmith-panel__live-smoke-list"
            aria-label={t('evalsPage.langsmith.liveSmokeChain')}
          >
            {liveSmokeChainSteps.map((step) => (
              <li key={step.id} className="eval-langsmith-panel__live-smoke-step">
                <Link to={step.href} className="eval-langsmith-panel__live-smoke-link">
                  <span className="eval-langsmith-panel__live-smoke-copy">
                    <span className="eval-langsmith-panel__live-smoke-label">{step.label}</span>
                    <span className="eval-langsmith-panel__live-smoke-description">
                      {step.description}
                    </span>
                  </span>
                  <InlineStatus
                    status={step.status}
                    label={t(`common.statuses.${step.status}`, { defaultValue: step.status })}
                  />
                </Link>
              </li>
            ))}
          </ol>
        </details>
        <section
          className="eval-langsmith-panel__operations"
          role="region"
          aria-label={t('evalsPage.langsmith.operationsTitle')}
        >
          <div className="eval-langsmith-panel__operations-head">
            <div>
              <h3>{t('evalsPage.langsmith.operationsTitle')}</h3>
              <p>{t('evalsPage.langsmith.operationsDescription')}</p>
            </div>
            <InlineStatus
              status={liveSyncResult ? (liveSyncAggregated ? 'PASS' : 'WARN') : 'DISABLED'}
              label={liveSyncResult
                ? liveSyncAggregated
                  ? t('evalsPage.langsmith.readinessAggregationCurrent')
                  : t('evalsPage.langsmith.readinessAggregationPending')
                : t('evalsPage.langsmith.notRun')}
            />
          </div>
          <div className="eval-langsmith-panel__operations-form">
            <div className="eval-langsmith-panel__dataset-control">
              <div className="eval-langsmith-panel__dataset-label">
                <label htmlFor="eval-langsmith-dataset-name">{t('evalsPage.langsmith.datasetName')}</label>
                <HelpHint
                  title={t('evalsPage.langsmith.help.datasetTitle')}
                  label={t('evalsPage.langsmith.help.datasetDescription')}
                />
              </div>
              <div className="eval-langsmith-panel__dataset-field">
                <Database size={17} aria-hidden="true" />
                <input
                  id="eval-langsmith-dataset-name"
                  type="text"
                  value={datasetName}
                  maxLength={255}
                  onChange={(event) => setDatasetName(event.target.value)}
                />
              </div>
            </div>
            <div className="eval-langsmith-panel__operations-count">
              <span>{t('evalsPage.langsmith.enabledPersistedCases')}</span>
              <strong>{persistedCasesLoading ? '-' : persistedCases.length}</strong>
            </div>
            <div className="eval-langsmith-panel__operations-actions">
              <OperationButton
                variant="primary"
                isOperating={syncMutation.isPending}
                disabled={!datasetName.trim() || persistedCases.length === 0}
                disabledReason={persistedCases.length === 0
                  ? t('evalsPage.langsmith.noEnabledCases')
                  : t('evalsPage.langsmith.datasetRequired')}
                onClick={() => syncMutation.mutate()}
              >
                <CloudUpload size={16} aria-hidden="true" />
                {t('evalsPage.langsmith.syncAllEnabled')}
              </OperationButton>
              <OperationButton
                variant="secondary"
                isOperating={dashboardFetching}
                onClick={() => { void refetchDashboard() }}
              >
                <RefreshCw size={16} aria-hidden="true" />
                {t('evalsPage.langsmith.refreshReadinessEvidence')}
              </OperationButton>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => { void refetchPersistedCases() }}
              >
                <RefreshCw size={16} aria-hidden="true" />
                {t('evalsPage.langsmith.refreshCases')}
              </button>
            </div>
          </div>
          {liveSyncResult && (
            <details className="eval-langsmith-panel__live-result" aria-live="polite">
              <summary className="eval-langsmith-panel__live-result-head">
                <strong>{t('evalsPage.langsmith.liveSyncPassed')}</strong>
                <InlineStatus
                  status={liveSyncResult.secretFree ? 'PASS' : 'FAIL'}
                  label={liveSyncResult.secretFree
                    ? t('evalsPage.langsmith.liveSyncVerified')
                    : t('common.statuses.FAIL')}
                />
              </summary>
              <dl>
                <div>
                  <dt>{t('evalsPage.langsmith.dataset')}</dt>
                  <dd>{liveSyncResult.datasetName}</dd>
                </div>
                <div>
                  <dt>{t('evalsPage.langsmith.examples')}</dt>
                  <dd>{liveSyncResult.examples}</dd>
                </div>
                <div>
                  <dt>{t('evalsPage.langsmith.caseIds')}</dt>
                  <dd>{liveSyncResult.caseIds.join(', ')}</dd>
                </div>
                <div>
                  <dt>{t('evalsPage.langsmith.metadataCaseIds')}</dt>
                  <dd>{liveSyncResult.metadataCaseIds.join(', ')}</dd>
                </div>
                <div className="eval-langsmith-panel__live-result-wide">
                  <dt>{t('evalsPage.langsmith.exampleIds')}</dt>
                  <dd>{liveSyncResult.exampleIds.join(', ')}</dd>
                </div>
              </dl>
              {!liveSyncAggregated && (
                <p className="eval-langsmith-panel__aggregation-note">
                  {t('evalsPage.langsmith.readinessAggregationPendingDesc')}{' '}
                  <Link to={RELEASE_WORKFLOW_PATHS_BY_ID.cockpit}>
                    <span>{RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit}</span>
                    {t('evalsPage.langsmith.openReleaseCockpit')}
                  </Link>
                </p>
              )}
            </details>
          )}
        </section>
        <details id={RELEASE_LANGSMITH_SYNC_ANCHOR_ID} className="eval-langsmith-panel__evidence-disclosure">
          <summary>
            <span className="eval-langsmith-panel__disclosure-copy">
              <span>{t('evalsPage.langsmith.syncEvidenceDetails')}</span>
              <span>{t('evalsPage.langsmith.syncEvidenceDetailsDescription')}</span>
            </span>
          </summary>
          <dl className="eval-langsmith-panel__grid">
          <div>
            <dt>{t('evalsPage.langsmith.dataset')}</dt>
            <dd>{langsmithSync?.datasetName || t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.gateStatus')}</dt>
            <dd>{langsmithReadinessItem?.status || t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.gateMode')}</dt>
            <dd>{langsmithReadinessItem?.mode || t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.gateScope')}</dt>
            <dd>{langsmithReadinessItem?.scope || t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.gateArtifact')}</dt>
            <dd>{langsmithReadinessItem?.artifact || t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.examples')}</dt>
            <dd>{langsmithSync?.exampleCount ?? 0}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.cases')}</dt>
            <dd>{langsmithSync?.caseCount ?? 0}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.splits')}</dt>
            <dd>{splitSummary || t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.sdkContract')}</dt>
            <dd>{langsmithSync?.sdkContract || t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div className="eval-langsmith-panel__wide">
            <dt>{t('evalsPage.langsmith.sdkContractFields')}</dt>
            <dd>
              {sdkContractFieldsSummary
                ? <code className="eval-langsmith-panel__evidence">{sdkContractFieldsSummary}</code>
                : t('evalsPage.langsmith.missing')}
            </dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.secretScan')}</dt>
            <dd>{langsmithSync?.secretFree === false ? t('common.no') : langsmithSync ? t('common.yes') : t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div className="eval-langsmith-panel__wide">
            <dt>{t('evalsPage.langsmith.exampleContract')}</dt>
            <dd>
              {exampleContractSummary
                ? <code className="eval-langsmith-panel__evidence">{exampleContractSummary}</code>
                : t('evalsPage.langsmith.missing')}
            </dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.exampleIds')}</dt>
            <dd>{exampleIdsSummary || t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.caseIds')}</dt>
            <dd>{caseIdsSummary || t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.metadataCaseIds')}</dt>
            <dd>{metadataCaseIdsSummary || t('evalsPage.langsmith.missing')}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.syncContract')}</dt>
            <dd>
              {missingLangsmithContracts.length === 0
                ? t('evalsPage.langsmith.contractReady')
                : t('evalsPage.langsmith.contractMissing', {
                    fields: missingLangsmithContracts.join(', '),
                  })}
            </dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.requiredReports')}</dt>
            <dd>{requiredReportLinks ?? '-'}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.missingReports')}</dt>
            <dd>{missingReportLinks ?? t('evalsPage.langsmith.noneMissing')}</dd>
          </div>
          <div>
            <dt>{t('evalsPage.langsmith.blockingReports')}</dt>
            <dd>{blockingReportLinks ?? t('evalsPage.langsmith.noneBlocking')}</dd>
          </div>
          {requiredEnvAnyOf && (
            <div>
              <dt>{t('evalsPage.langsmith.requiredEnvAnyOf')}</dt>
              <dd>{requiredEnvAnyOf}</dd>
            </div>
          )}
          {missingEnvAnyOf && (
            <div>
              <dt>{t('evalsPage.langsmith.missingEnvAnyOf')}</dt>
              <dd>{missingEnvAnyOf}</dd>
            </div>
          )}
          {recommendedEnv && (
            <div>
              <dt>{t('evalsPage.langsmith.recommendedEnv')}</dt>
              <dd>{recommendedEnv}</dd>
            </div>
          )}
          </dl>
        </details>
        {hasLangsmithUnblockHandoff && (
          <details
            className="eval-langsmith-panel__handoff"
            aria-label={t('evalsPage.langsmith.unblockHandoff')}
          >
            <summary className="eval-langsmith-panel__handoff-head">
              <span>{t('evalsPage.langsmith.unblockHandoff')}</span>
              <InlineStatus
                status={blockingReports.includes('langsmith_eval_sync') ? 'WARN' : 'PASS'}
                label={blockingReports.includes('langsmith_eval_sync')
                  ? t('evalsPage.langsmith.syncNeedsAttention')
                  : t('evalsPage.langsmith.noneBlocking')}
              />
            </summary>
            <dl className="eval-langsmith-panel__handoff-grid">
              {requiredEnvAnyOf && (
                <div>
                  <dt>{t('evalsPage.langsmith.unblockCredentialGroup')}</dt>
                  <dd>{requiredEnvAnyOf}</dd>
                </div>
              )}
              {missingEnvAnyOf && (
                <div>
                  <dt>{t('evalsPage.langsmith.unblockMissingEnv')}</dt>
                  <dd>{missingEnvAnyOf}</dd>
                </div>
              )}
              {blockingReports.length > 0 && (
                <div>
                  <dt>{t('evalsPage.langsmith.unblockBlockingReports')}</dt>
                  <dd>{unblockBlockingReportLinks}</dd>
                </div>
              )}
              {releaseReadinessCommand && (
                <div className="eval-langsmith-panel__handoff-wide">
                  <dt>{t('evalsPage.langsmith.unblockCommand')}</dt>
                  <dd>
                    <span className="eval-langsmith-panel__command">
                      <code>{releaseReadinessCommand}</code>
                      <CopyButton
                        value={releaseReadinessCommand}
                        label={t('evalsPage.langsmith.copyReadinessCommand')}
                      />
                    </span>
                  </dd>
                </div>
              )}
              {feedbackSyncRemediationCommand && (
                <div className="eval-langsmith-panel__handoff-wide">
                  <dt>{t('evalsPage.langsmith.feedbackRemediationCommand')}</dt>
                  <dd>
                    <span className="eval-langsmith-panel__command">
                      <code>{feedbackSyncRemediationCommand}</code>
                      <CopyButton
                        value={feedbackSyncRemediationCommand}
                        label={t('evalsPage.langsmith.feedbackRemediationCommand')}
                      />
                    </span>
                  </dd>
                </div>
              )}
              {langsmithActionHandoffs.length > 0 && (
                <div className="eval-langsmith-panel__handoff-wide">
                  <dt>{t('evalsPage.langsmith.nextActionStates')}</dt>
                  <dd>
                    <div className="eval-langsmith-panel__actions" role="list">
                      {langsmithActionHandoffs.map(({ action, command, itemName, state }) => (
                        <div
                          key={action.id || `${itemName ?? 'release'}:${action.label ?? ''}:${command ?? ''}`}
                          className="eval-langsmith-panel__action"
                          role="listitem"
                        >
                          <div className="eval-langsmith-panel__action-head">
                            <span className="eval-langsmith-panel__action-id">
                              {action.id || action.label || t('evalsPage.langsmith.nextAction')}
                            </span>
                            {state && (
                              <span className={`eval-langsmith-panel__action-state ${actionStateClassName(state)}`}>
                                {t('evalsPage.langsmith.actionState')}: {state}
                              </span>
                            )}
                            {itemName && <ReleaseReportLink report={itemName} />}
                          </div>
                          {action.label && <p>{action.label}</p>}
                          {command && (
                            <span className="eval-langsmith-panel__command">
                              <code>{command}</code>
                              <CopyButton
                                value={command}
                                label={t('evalsPage.langsmith.nextActionCommand')}
                              />
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </dd>
                </div>
              )}
            </dl>
          </details>
        )}
        {hasFeedbackCoverage && (
          <details
            className="eval-langsmith-panel__handoff"
            role="region"
            aria-label={t('evalsPage.langsmith.feedbackPromotionCoverage')}
          >
            <summary className="eval-langsmith-panel__handoff-head">
              <span>{t('evalsPage.langsmith.feedbackPromotionCoverage')}</span>
              <Link className="eval-langsmith-panel__command-link" to={RELEASE_WORKFLOW_PATHS_BY_ID.feedback}>
                <span className="eval-langsmith-panel__command-step">
                  {RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback}
                </span>
                {t('evalsPage.langsmith.openFeedbackPromotion')}
              </Link>
            </summary>
            <dl className="eval-langsmith-panel__handoff-grid">
              <div>
                <dt>{t('evalsPage.langsmith.feedbackPromotedCases')}</dt>
                <dd>{feedbackPromotedCaseIdsSummary}</dd>
              </div>
              {feedbackReviewQueue?.reviewStatus && (
                <div>
                  <dt>{t('evalsPage.langsmith.feedbackReviewStatus')}</dt>
                  <dd>{feedbackReviewQueue.reviewStatus}</dd>
                </div>
              )}
              {feedbackReviewQueue?.reviewNote && (
                <div>
                  <dt>{t('evalsPage.langsmith.feedbackReviewNote')}</dt>
                  <dd>{feedbackReviewQueue.reviewNote}</dd>
                </div>
              )}
              {feedbackReviewTagsSummary && (
                <div>
                  <dt>{t('evalsPage.langsmith.feedbackReviewTags')}</dt>
                  <dd>{feedbackReviewTagsSummary}</dd>
                </div>
              )}
              {feedbackExpectedCitationCountsSummary && (
                <div>
                  <dt>{t('evalsPage.langsmith.feedbackExpectedCitations')}</dt>
                  <dd>{feedbackExpectedCitationCountsSummary}</dd>
                </div>
              )}
              <div>
                <dt>{t('evalsPage.langsmith.feedbackCoverage')}</dt>
                <dd>{feedbackLangsmithCoverage || '-'}</dd>
              </div>
              <div>
                <dt>{t('evalsPage.langsmith.feedbackSyncedCases')}</dt>
                <dd>{feedbackSyncedCases.length > 0 ? feedbackSyncedCases.join(', ') : '-'}</dd>
              </div>
              <div>
                <dt>{t('evalsPage.langsmith.feedbackUnsyncedCases')}</dt>
                <dd>{feedbackUnsyncedCases.length > 0 ? feedbackUnsyncedCases.join(', ') : '-'}</dd>
              </div>
              <div>
                <dt>{t('evalsPage.langsmith.feedbackMetadataCoverage')}</dt>
                <dd>{feedbackMetadataCoverage || '-'}</dd>
              </div>
              <div>
                <dt>{t('evalsPage.langsmith.feedbackMetadataMissingCases')}</dt>
                <dd>{feedbackMetadataMissingCases.length > 0 ? feedbackMetadataMissingCases.join(', ') : '-'}</dd>
              </div>
              {feedbackPromotionProvenance.length > 0 && (
                <div>
                  <dt>{t('evalsPage.langsmith.feedbackDiagnosticsCoverage')}</dt>
                  <dd>{feedbackDiagnosticsCoverage || '-'}</dd>
                </div>
              )}
              {feedbackPromotionProvenance.length > 0 && (
                <div className="eval-langsmith-panel__handoff-wide">
                  <dt>{t('evalsPage.langsmith.feedbackPromotionProvenance')}</dt>
                  <dd>
                    {feedbackPromotionProvenance.map((item, index) => {
                      const promotionCoverage = evidenceMapSummary(item.promotionCoverage)
                      const citationMarkerContract = evidenceMapSummary(item.citationMarkerContract)
                      return (
                        <dl
                          key={`${item.caseId ?? item.sourceRunId ?? 'promotion-provenance'}-${index}`}
                          className="eval-langsmith-panel__provenance"
                        >
                          {item.caseId && (
                            <div>
                              <dt>{t('evalsPage.langsmith.caseIds')}</dt>
                              <dd>{item.caseId}</dd>
                            </div>
                          )}
                          {item.sourceRunId && (
                            <div>
                              <dt>{t('evalsPage.langsmith.feedbackSourceRun')}</dt>
                              <dd>{item.sourceRunId}</dd>
                            </div>
                          )}
                          {item.runFile && (
                            <div>
                              <dt>{t('evalsPage.langsmith.feedbackRunFile')}</dt>
                              <dd>{item.runFile}</dd>
                            </div>
                          )}
                          {item.caseFile && (
                            <div>
                              <dt>{t('evalsPage.langsmith.feedbackCaseFile')}</dt>
                              <dd>{item.caseFile}</dd>
                            </div>
                          )}
                          {item.diagnosticsApi && (
                            <div>
                              <dt>{t('evalsPage.langsmith.feedbackDiagnosticsApi')}</dt>
                              <dd>{item.diagnosticsApi}</dd>
                            </div>
                          )}
                          {item.remediationCommand && (
                            <div>
                              <dt>{t('evalsPage.langsmith.feedbackRemediationCommand')}</dt>
                              <dd>{item.remediationCommand}</dd>
                            </div>
                          )}
                          {promotionCoverage && (
                            <div>
                              <dt>{t('evalsPage.langsmith.feedbackPromotionCoverageContract')}</dt>
                              <dd>{promotionCoverage}</dd>
                            </div>
                          )}
                          {citationMarkerContract && (
                            <div>
                              <dt>{t('evalsPage.langsmith.feedbackCitationMarkerContract')}</dt>
                              <dd>{citationMarkerContract}</dd>
                            </div>
                          )}
                        </dl>
                      )
                    })}
                  </dd>
                </div>
              )}
            </dl>
            {hasFeedbackSyncRemediation && (
              <div
                className="eval-langsmith-panel__remediation"
                role="region"
                aria-label={t('evalsPage.langsmith.feedbackSyncRemediation')}
              >
                <div className="eval-langsmith-panel__remediation-head">
                  <span>{t('evalsPage.langsmith.feedbackSyncRemediation')}</span>
                  <InlineStatus
                    status="WARN"
                    label={t('evalsPage.langsmith.syncNeedsAttention')}
                  />
                </div>
                <p>{t('evalsPage.langsmith.feedbackSyncRemediationDesc')}</p>
                <dl>
                  {feedbackUnsyncedCases.length > 0 && (
                    <div>
                      <dt>{t('evalsPage.langsmith.feedbackUnsyncedCases')}</dt>
                      <dd>{feedbackUnsyncedCases.join(', ')}</dd>
                    </div>
                  )}
                  {feedbackMetadataMissingCases.length > 0 && (
                    <div>
                      <dt>{t('evalsPage.langsmith.feedbackMetadataMissingCases')}</dt>
                      <dd>{feedbackMetadataMissingCases.join(', ')}</dd>
                    </div>
                  )}
                </dl>
                <div className="eval-langsmith-panel__remediation-actions">
                  <Link className="eval-langsmith-panel__command-link" to={RELEASE_WORKFLOW_PATHS_BY_ID.feedback}>
                    <span className="eval-langsmith-panel__command-step">
                      {RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback}
                    </span>
                    {t('evalsPage.langsmith.openFeedbackPromotion')}
                  </Link>
                  <Link className="eval-langsmith-panel__command-link" to={RELEASE_WORKFLOW_PATHS_BY_ID.cockpit}>
                    <span className="eval-langsmith-panel__command-step">
                      {RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit}
                    </span>
                    {t('evalsPage.langsmith.openReleaseCockpit')}
                  </Link>
                </div>
              </div>
            )}
          </details>
        )}
        {releaseReadinessCommand && (
          <details className="eval-langsmith-panel__command-disclosure">
            <summary>
              <span className="eval-langsmith-panel__disclosure-copy">
                <span>{t('evalsPage.langsmith.copyReadinessCommand')}</span>
                <span>{t('evalsPage.langsmith.copyReadinessCommandDescription')}</span>
              </span>
            </summary>
            <div className="eval-langsmith-panel__command">
              <CopyButton
                value={releaseReadinessCommand}
                label={t('evalsPage.langsmith.copyReadinessCommand')}
              />
              <Link className="eval-langsmith-panel__command-link" to={RELEASE_WORKFLOW_PATHS_BY_ID.cockpit}>
                <span className="eval-langsmith-panel__command-step">
                  {RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit}
                </span>
                {t('evalsPage.langsmith.openReleaseCockpit')}
              </Link>
              <code>{releaseReadinessCommand}</code>
            </div>
          </details>
        )}
      </section>
      <section className="eval-run-history" aria-labelledby="eval-run-history-title">
        <header className="eval-run-history__header">
          <div>
            <h3 id="eval-run-history-title">{t('evalsPage.runHistory')}</h3>
            <p>{t('evalsPage.runHistoryDescription')}</p>
          </div>
          {!runsLoading && !runsError && (
            <span className="eval-run-history__count">
              {t('evalsPage.runCount', { count: runs?.length ?? 0 })}
            </span>
          )}
        </header>
        {runsLoading ? (
          <SkeletonTable rows={4} columns={5} />
        ) : runs && runs.length > 0 ? (
          <DataTable
            columns={columns}
            data={runs}
            keyFn={(row) => row.evalRunId}
            tableId="eval-run-history"
          />
        ) : (
          <EmptyState
            message={t('evalsPage.noExperiments')}
            description={t('evalsPage.noExperimentsDescription')}
          />
        )}
      </section>
    </div>
  )
}

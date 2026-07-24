import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ChevronDown } from 'lucide-react'
import {
  CopyButton,
  ProductCapabilityBoundaryFlowList,
  ReleaseReportLink,
  ReleaseReportList,
  StatusBadge,
  TimestampWithZone,
} from '../../../shared/ui'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import { hasLangsmithSyncEvidence } from '../../../shared/lib/releaseReadinessEvidence'
import {
  hasA2aSmokeEvidence,
  hasSlackSmokeEvidence,
} from '../../../shared/lib/liveSmokeEvidence'
import {
  hasProviderSmokeEvidence,
  listProviderSmokeMissingCheckIds,
  type ProviderSmokeCheckId,
} from '../../../shared/lib/providerSmokeEvidence'
import { resolveReleaseNextActionCommand } from '../../../shared/lib/releaseNextActionCommand'
import {
  RELEASE_COCKPIT_ANCHOR_ID,
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_RAG_ANSWER_CONTRACT_PATH,
  RELEASE_WORKFLOW_GATE_ORDER,
  RELEASE_WORKFLOW_GATE_PATHS,
  RELEASE_WORKFLOW_GATE_STEP_NUMBERS,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
  releaseBlockingReportRoute,
  releaseBoundaryEvidencePath,
  releaseReportBelongsToGate,
  releaseReportPath,
  type ReleaseWorkflowGateId,
} from '../../../shared/releaseWorkflow'
import type {
  DashboardReleaseGateSummary,
  DashboardReleaseNextAction,
  DashboardReleaseReadinessSummary,
} from '../types'

const gateOrder = RELEASE_WORKFLOW_GATE_ORDER

const statusToBadge: Record<DashboardReleaseReadinessSummary['status'], string> = {
  passed: 'PASS',
  eligible_with_warnings: 'WARN',
  blocked: 'FAIL',
  missing: 'DISABLED',
}

const gateStatusToBadge: Record<DashboardReleaseGateSummary['status'], string> = {
  passed: 'PASS',
  warning: 'WARN',
  blocked: 'FAIL',
  missing: 'DISABLED',
}

const gatePaths = RELEASE_WORKFLOW_GATE_PATHS
const gateStepNumbers = RELEASE_WORKFLOW_GATE_STEP_NUMBERS

interface BlockerQueueItem {
  key: string
  report: string
  gateId: ReleaseWorkflowGateId | null
  path: string | null
  stepNumber: number | null
  gateLabel: string
  remediation: string
}

interface ProductBoundaryOpsQueueItem {
  id: string
  stepNumber: number
  title: string
  description: string
  href: string
  status: string
  statusLabel: string
  evidence: string[]
  missing: string[]
}

type ReleaseWarning = NonNullable<DashboardReleaseReadinessSummary['warnings']>[number]
type DependencyWarnings = NonNullable<DashboardReleaseReadinessSummary['dependencyWarnings']>

type SmokeBlockerGateId = Extract<ReleaseWorkflowGateId, 'slack' | 'a2a' | 'provider'>

const smokeGateEnvRequirements: Record<SmokeBlockerGateId, string[]> = {
  slack: ['REACTOR_SLACK_BOT_TOKEN', 'REACTOR_SLACK_SIGNING_SECRET'],
  a2a: ['REACTOR_A2A_BASE_URL', 'REACTOR_A2A_API_KEY'],
  provider: ['OPENAI_API_KEY'],
}

const localGateCommands = [
  'git status --short --branch',
  'git tag --points-at HEAD',
  'pnpm test -- --reporter=dot',
  'pnpm lint --quiet',
  'pnpm build',
  'pnpm verify:admin-api',
]

function resolveGate(
  readiness: DashboardReleaseReadinessSummary | null | undefined,
  id: ReleaseWorkflowGateId,
): DashboardReleaseGateSummary {
  return readiness?.gates?.find((gate) => gate.id === id) ?? { id, status: 'missing' }
}

function listSummary(values: string[] | null | undefined): string {
  return values?.filter(Boolean).join(', ') ?? ''
}

function renderLinkedReports(values: string[] | null | undefined) {
  return <ReleaseReportList reports={values} />
}

function countSummary(values: Record<string, number> | null | undefined): string {
  return Object.entries(values ?? {})
    .map(([key, count]) => `${key}: ${formatLocaleNumber(count)}`)
    .join(', ')
}

function formatBoolean(value: boolean | null | undefined, yes: string, no: string, missing: string): string {
  if (value === true) return yes
  if (value === false) return no
  return missing
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

function mappingSummary(value: Record<string, string> | null | undefined): string {
  return Object.entries(value ?? {})
    .map(([key, item]) => `${key}: ${item}`)
    .join(', ')
}

function releaseAggregateSummary(
  summary: DashboardReleaseReadinessSummary['summary'] | null | undefined,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  if (!summary) return ''
  return [
    `${t('dashboard.release.aggregateDiagnostics.blocked')}: ${formatLocaleNumber(summary.blocked ?? 0)}`,
    `${t('dashboard.release.aggregateDiagnostics.failed')}: ${formatLocaleNumber(summary.failed ?? 0)}`,
    `${t('dashboard.release.aggregateDiagnostics.passed')}: ${formatLocaleNumber(summary.passed ?? 0)}`,
    `${t('dashboard.release.aggregateDiagnostics.skipped')}: ${formatLocaleNumber(summary.skipped ?? 0)}`,
    `${t('dashboard.release.aggregateDiagnostics.total')}: ${formatLocaleNumber(summary.total ?? 0)}`,
  ].join(', ')
}

function releaseDecisionActionLabel(
  action: string,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  if (/[가-힣ㄱ-ㅎㅏ-ㅣ]/u.test(action)) return action

  const normalized = action.toLowerCase()
  if (['review release readiness warnings', 'verify clean worktree']
    .some((phrase) => normalized.includes(phrase))) {
    return t('dashboard.release.decisionBrief.reviewWarningsThenVerify')
  }
  if (normalized.includes('monitor upstream') && normalized.includes('compatibility')) {
    return t('dashboard.release.decisionBrief.monitorDependencyCompatibility')
  }
  return t('dashboard.release.decisionBrief.reviewReportedAction')
}

function releaseVersionBumpLabel(
  value: string,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  const normalized = value.trim().toLowerCase()
  if (normalized === 'major') return t('dashboard.release.versionBumpValue.major')
  if (normalized === 'minor') return t('dashboard.release.versionBumpValue.minor')
  if (normalized === 'patch') return t('dashboard.release.versionBumpValue.patch')
  if (normalized === 'none') return t('dashboard.release.versionBumpValue.none')
  return value
}

function readinessItemStatusBadge(
  item: NonNullable<DashboardReleaseReadinessSummary['items']>[number],
): string {
  if (item.ok === true || item.status === 'passed') return 'PASS'
  if (item.ok === false || item.status === 'blocked' || item.status === 'failed') return 'FAIL'
  if (item.status === 'skipped' || item.status === 'missing') return 'DISABLED'
  return 'WARN'
}

function releaseNextActionHandoffs(
  items: NonNullable<DashboardReleaseReadinessSummary['items']>,
  actionStates: Record<string, string>,
) {
  const handoffs = new Map<string, {
    action: DashboardReleaseNextAction
    command: string
    itemName: string | null
    itemPath: string | null
    state: string | null
  }>()

  items.forEach((item) => {
    item.nextActions?.filter(Boolean).forEach((action) => {
      const command = resolveReleaseNextActionCommand(action) ?? ''
      const key = action.id || `${item.name ?? 'item'}:${action.label ?? ''}:${command}`
      if (!key || handoffs.has(key)) return
      handoffs.set(key, {
        action,
        command,
        itemName: item.name ?? null,
        itemPath: item.name ? releaseReportPath(item.name) : null,
        state: action.id ? actionStates[action.id] ?? null : null,
      })
    })
  })

  return Array.from(handoffs.values())
}

function providerSmokeCheckLabel(t: ReturnType<typeof useTranslation>['t'], checkId: ProviderSmokeCheckId): string {
  const labels: Record<ProviderSmokeCheckId, string> = {
    provider: t('dashboard.release.provider.provider'),
    model: t('dashboard.release.provider.model'),
    usage_present: t('dashboard.release.provider.usage'),
    usage_source: t('dashboard.release.provider.source'),
    usage_tokens: t('dashboard.release.provider.tokenCounts'),
    usage_breakdown: t('dashboard.release.provider.breakdown'),
    required_usage_metadata: t('dashboard.release.provider.requiredChecks'),
  }
  return labels[checkId]
}

function uniqueList(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value))))
}

function compactStrings(values: Array<string | null | undefined>): string[] {
  return values.filter((value): value is string => Boolean(value))
}

function warningFindingsSummary(
  findings: NonNullable<NonNullable<DashboardReleaseReadinessSummary['warnings']>[number]['findings']> | null | undefined,
): string {
  return (findings ?? [])
    .map((finding) => [
      finding.package,
      finding.module,
      finding.deprecatedImport && finding.replacement
        ? `${finding.deprecatedImport} -> ${finding.replacement}`
        : finding.deprecatedImport,
      finding.severity,
    ].filter(Boolean).join(' / '))
    .filter(Boolean)
    .join(', ')
}

function warningFingerprint(warning: ReleaseWarning): string {
  return [
    warning.name,
    warning.status,
    warning.source,
    warning.remediation,
    ...(warning.findings ?? []).flatMap((finding) => [
      finding.package,
      finding.module,
      finding.deprecatedImport,
      finding.replacement,
    ]),
  ].filter(Boolean).join(' ').toLowerCase()
}

function isDependencyCompatibilityWarning(warning: ReleaseWarning): boolean {
  return /dependency|langmem|trustcall|langgraph/.test(warningFingerprint(warning))
}

function releaseWarningOperatorTitle(
  warning: ReleaseWarning,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  return isDependencyCompatibilityWarning(warning)
    ? t('dashboard.release.warningList.dependencyTitle')
    : t('dashboard.release.warningList.generalTitle')
}

function releaseWarningOperatorSummary(
  warning: ReleaseWarning,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  return isDependencyCompatibilityWarning(warning)
    ? t('dashboard.release.warningList.dependencySummary')
    : t('dashboard.release.warningList.generalSummary')
}

function releaseWarningOperatorAction(
  warning: ReleaseWarning,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  return isDependencyCompatibilityWarning(warning)
    ? t('dashboard.release.warningList.dependencyAction')
    : t('dashboard.release.warningList.generalAction')
}

function dependencyWarningOperatorSummary(
  warning: DependencyWarnings,
  t: ReturnType<typeof useTranslation>['t'],
): string {
  const count = warning.findingCount ?? warning.findings?.length ?? 0
  return count > 0
    ? t('dashboard.release.warningEvidence.operatorSummaryWithCount', { count })
    : t('dashboard.release.warningEvidence.dependencySummary')
}

function resolveReportGateIds(report: string): ReleaseWorkflowGateId[] {
  return gateOrder.filter((gateId) => releaseReportBelongsToGate(report, gateId))
}

function listSmokeBlockerBreakdown(missingEnv: string[] | null | undefined) {
  const missing = new Set(missingEnv?.filter(Boolean) ?? [])
  return (Object.entries(smokeGateEnvRequirements) as Array<[SmokeBlockerGateId, string[]]>)
    .map(([gateId, env]) => ({
      gateId,
      env: env.filter((key) => missing.has(key)),
    }))
    .filter((item) => item.env.length > 0)
}

function smokeBlockerDescription(t: ReturnType<typeof useTranslation>['t'], gateId: SmokeBlockerGateId): string {
  if (gateId === 'slack') return t('dashboard.release.smokeHandoff.slackDesc')
  if (gateId === 'a2a') return t('dashboard.release.smokeHandoff.a2aDesc')
  return t('dashboard.release.smokeHandoff.providerDesc')
}

function readinessProvenanceReason(
  t: ReturnType<typeof useTranslation>['t'],
  reason: string | null | undefined,
): string {
  switch (reason) {
    case 'stale_readiness_evidence':
      return t('dashboard.release.decisionBrief.provenanceStale')
    case 'current_head_mismatch':
    case 'report_commit_mismatch':
      return t('dashboard.release.decisionBrief.provenanceHeadMismatch')
    case 'missing_provenance':
    case 'missing_provenance_fields':
      return t('dashboard.release.decisionBrief.provenanceMissing')
    default:
      return t('dashboard.release.decisionBrief.provenanceNotVerified')
  }
}

export type ReleaseCockpitView = 'all' | 'decision' | 'boundary' | 'evidence'

export function ReleaseCockpit({
  readiness,
  view = 'all',
}: {
  readiness?: DashboardReleaseReadinessSummary | null
  view?: ReleaseCockpitView
}) {
  const { t } = useTranslation()
  const status = readiness?.status ?? 'missing'
  const hasReleaseReadiness = readiness !== null && readiness !== undefined
  const tagRecommendation = readiness?.tagRecommendation ?? null
  const provenance = readiness?.provenance ?? null
  const provenanceVerified = provenance?.status === 'verified' && provenance.verifiedCurrentHead === true
  const evidenceCurrent = Boolean(readiness?.syncedAt) && provenanceVerified
  const blockers = readiness?.blockingReports ?? []
  const warnings = readiness?.warningReports ?? tagRecommendation?.warningReports ?? []
  const warningReviewPending = tagRecommendation?.warningReviewRequired === true
  const missingEvidenceTimestamp = Boolean(readiness) && !readiness?.syncedAt
  const decisionStatus = (hasReleaseReadiness && !evidenceCurrent) || blockers.length > 0 || tagRecommendation?.eligible === false
    ? 'blocked'
    : warningReviewPending
      ? 'eligible_with_warnings'
      : status
  const requiredReports = readiness?.requiredReports ?? []
  const missingReports = readiness?.missingReports ?? []
  const aggregateSummary = releaseAggregateSummary(readiness?.summary, t)
  const aggregateItems = readiness?.items?.filter(Boolean) ?? []
  const readyNextActionIds = readiness?.readyNextActionIds?.filter(Boolean) ?? []
  const nextActionStateMap = readiness?.nextActionStates ?? {}
  const aggregateActionHandoffs = releaseNextActionHandoffs(aggregateItems, nextActionStateMap)
  const nextActionStates = Object.entries(nextActionStateMap)
    .map(([id, state]) => `${id}: ${state}`)
    .join(', ')
  const showAggregateDiagnostics = Boolean(
    aggregateSummary
    || readiness?.failureSummary
    || readyNextActionIds.length > 0
    || nextActionStates
    || aggregateActionHandoffs.length > 0
    || aggregateItems.length > 0,
  )
  const requiredReportLinks = renderLinkedReports(requiredReports)
  const missingReportLinks = renderLinkedReports(missingReports)
  const requiredEnvAnyOf = formatEnvAnyOf(readiness?.requiredEnvAnyOf)
  const missingEnvAnyOf = listSummary(readiness?.missingEnvAnyOf)
  const recommendedEnv = listSummary(readiness?.recommendedEnv)
  const smokeMissingEnv = listSummary(tagRecommendation?.missingEnv)
  const smokeMissingEnvAnyOf = listSummary(tagRecommendation?.missingEnvAnyOf)
  const smokeBlockerBreakdown = listSmokeBlockerBreakdown(tagRecommendation?.missingEnv)
  const preflightEnvFileCommand = tagRecommendation?.preflightEnvFileCommand ?? null
  const releaseSmokeEnvFileCommand = tagRecommendation?.releaseSmokeEnvFileCommand ?? null
  const smokeHandoffVisible = Boolean(
    smokeMissingEnv
    || smokeMissingEnvAnyOf
    || smokeBlockerBreakdown.length > 0
    || preflightEnvFileCommand
    || releaseSmokeEnvFileCommand,
  )
  const currentEvidenceRequired = t('dashboard.release.currentEvidenceRequired')
  const recommendedTag = evidenceCurrent
    ? readiness?.recommendedTag ?? tagRecommendation?.recommendedTag ?? t('dashboard.release.noTag')
    : currentEvidenceRequired
  const versionBump = readiness?.recommendedVersionBump ?? tagRecommendation?.recommendedVersionBump ?? t('dashboard.release.noBump')
  const versionBumpLabel = evidenceCurrent
    ? releaseVersionBumpLabel(versionBump, t)
    : currentEvidenceRequired
  const minorEligible = evidenceCurrent && (readiness?.minorEligible ?? tagRecommendation?.minorEligible) === true
  const releaseReadinessCommand = tagRecommendation?.releaseReadinessCommand ?? null
  const latestVerifiedTag = tagRecommendation?.latestTag ?? null
  const localEvidenceReady = evidenceCurrent && Boolean(latestVerifiedTag && releaseReadinessCommand)
  const productCapabilityBoundary = readiness?.productCapabilityBoundary ?? null
  const productBoundaryEvidence = productCapabilityBoundary?.evidence?.filter(Boolean) ?? []
  const productBoundaryMissingEvidence = productCapabilityBoundary?.missingEvidence?.filter(Boolean) ?? []
  const productBoundaryChecklist = gateOrder.map((gateId) => {
    const gate = resolveGate(readiness, gateId)
    return {
      gateId,
      gate,
      gateLabel: gate.label ?? t(`dashboard.release.gates.${gateId}`),
      path: gatePaths[gateId],
      stepNumber: gateStepNumbers[gateId],
    }
  })
  const langsmithSync = readiness?.langsmithSync ?? null
  const langsmithSyncReady = hasLangsmithSyncEvidence(langsmithSync)
  const splitCounts = langsmithSync?.splitCounts ?? {}
  const splitSummary = Object.entries(splitCounts)
    .map(([split, count]) => `${split}: ${formatLocaleNumber(count)}`)
    .join(', ')
  const exampleIdsSummary = listSummary(langsmithSync?.exampleIds)
  const caseIdsSummary = listSummary(langsmithSync?.caseIds)
  const metadataCaseIdsSummary = listSummary(langsmithSync?.metadataCaseIds)
  const sdkContractFieldsSummary = formatEvidence(langsmithSync?.sdkContractFields)
  const exampleContractSummary = formatEvidence(langsmithSync?.exampleContract)
  const ragIngestionLifecycle = readiness?.ragIngestionLifecycle ?? null
  const ragAnswerContract = ragIngestionLifecycle?.researchAnswerContract ?? null
  const ragVerificationSensors = ragIngestionLifecycle?.verificationSensors ?? null
  const ragDiagnosticsSurface = ragIngestionLifecycle?.diagnosticsSurface ?? null
  const ragRuntimeSummary = [
    ragIngestionLifecycle?.framework,
    ragIngestionLifecycle?.vectorStore,
  ].filter(Boolean).join(' / ')
  const ragReleaseContracts = listSummary(ragVerificationSensors?.releaseReadinessContracts)
  const ragDiagnosticsApi = listSummary(ragDiagnosticsSurface?.apiPaths)
  const ragPoisoningEvalCases = listSummary(ragIngestionLifecycle?.poisoningEvalCaseIds)
  const feedbackReviewQueue = readiness?.feedbackReviewQueue ?? null
  const feedbackCaseIds = listSummary(feedbackReviewQueue?.caseIds)
  const feedbackReviewTags = listSummary(feedbackReviewQueue?.reviewTags)
  const feedbackRatingCounts = countSummary(feedbackReviewQueue?.feedbackRatingCounts)
  const feedbackSourceCounts = countSummary(feedbackReviewQueue?.feedbackSourceCounts)
  const feedbackWorkflowCounts = countSummary(feedbackReviewQueue?.workflowTagCounts)
  const feedbackExpectedCitationCounts = countSummary(feedbackReviewQueue?.expectedCitationCounts)
  const boundaryOpsQueue: ProductBoundaryOpsQueueItem[] = [
    {
      id: 'ingest',
      stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.ingest,
      title: t('dashboard.release.productBoundaryOps.ingestTitle'),
      description: t('dashboard.release.productBoundaryOps.ingestDesc'),
      href: RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
      status: gateStatusToBadge[resolveGate(readiness, 'rag').status],
      statusLabel: t(`dashboard.release.gateStatus.${resolveGate(readiness, 'rag').status}`),
      evidence: compactStrings([
        ragRuntimeSummary,
        ragReleaseContracts,
        ragDiagnosticsApi,
      ]),
      missing: [
        !ragIngestionLifecycle && t('dashboard.release.productBoundaryOps.missingRagLifecycle'),
        !ragReleaseContracts && t('dashboard.release.productBoundaryOps.missingReadinessContracts'),
      ].filter((item): item is string => Boolean(item)),
    },
    {
      id: 'cited-answer',
      stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.rag,
      title: t('dashboard.release.productBoundaryOps.citedAnswerTitle'),
      description: t('dashboard.release.productBoundaryOps.citedAnswerDesc'),
      href: RELEASE_RAG_ANSWER_CONTRACT_PATH,
      status: gateStatusToBadge[resolveGate(readiness, 'rag').status],
      statusLabel: t(`dashboard.release.gateStatus.${resolveGate(readiness, 'rag').status}`),
      evidence: compactStrings([
        ragAnswerContract?.citationStyle,
        ragAnswerContract?.requiresSourceLabels === true ? t('dashboard.release.rag.sourceLabels') : '',
        ragAnswerContract?.uncitedClaimsAllowed === false ? t('dashboard.release.rag.uncitedClaims') : '',
      ]),
      missing: [
        !ragAnswerContract && t('dashboard.release.productBoundaryOps.missingAnswerContract'),
        ragAnswerContract?.requiresCitationIds !== true && t('dashboard.release.productBoundaryOps.missingCitationIds'),
      ].filter((item): item is string => Boolean(item)),
    },
    {
      id: 'feedback',
      stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback,
      title: t('dashboard.release.productBoundaryOps.feedbackTitle'),
      description: t('dashboard.release.productBoundaryOps.feedbackDesc'),
      href: RELEASE_WORKFLOW_PATHS_BY_ID.feedback,
      status: gateStatusToBadge[resolveGate(readiness, 'feedback').status],
      statusLabel: t(`dashboard.release.gateStatus.${resolveGate(readiness, 'feedback').status}`),
      evidence: compactStrings([
        feedbackReviewQueue?.candidateTag,
        feedbackCaseIds,
        feedbackExpectedCitationCounts,
      ]),
      missing: [
        !feedbackReviewQueue && t('dashboard.release.productBoundaryOps.missingFeedbackQueue'),
        !feedbackCaseIds && t('dashboard.release.productBoundaryOps.missingFeedbackCases'),
      ].filter((item): item is string => Boolean(item)),
    },
    {
      id: 'langsmith',
      stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
      title: t('dashboard.release.productBoundaryOps.langsmithTitle'),
      description: t('dashboard.release.productBoundaryOps.langsmithDesc'),
      href: RELEASE_LANGSMITH_SYNC_PATH,
      status: langsmithSyncReady ? 'PASS' : gateStatusToBadge[resolveGate(readiness, 'langsmith').status],
      statusLabel: langsmithSyncReady
        ? t('dashboard.release.langsmith.secretScanPass')
        : t(`dashboard.release.gateStatus.${resolveGate(readiness, 'langsmith').status}`),
      evidence: compactStrings([
        langsmithSync?.datasetName,
        caseIdsSummary,
        metadataCaseIdsSummary,
        splitSummary,
      ]),
      missing: [
        !langsmithSyncReady && t('dashboard.release.productBoundaryOps.missingLangsmithSync'),
        !metadataCaseIdsSummary && t('dashboard.release.productBoundaryOps.missingMetadataCases'),
      ].filter((item): item is string => Boolean(item)),
    },
  ]
  const backendProviderIntegration = readiness?.backendProviderIntegration ?? null
  const providerUsage = backendProviderIntegration?.usageMetadata ?? null
  const providerUsageSummary = providerUsage
    ? [
        `${t('dashboard.release.provider.inputTokens')}: ${formatLocaleNumber(providerUsage.inputTokens ?? 0)}`,
        `${t('dashboard.release.provider.outputTokens')}: ${formatLocaleNumber(providerUsage.outputTokens ?? 0)}`,
        `${t('dashboard.release.provider.totalTokens')}: ${formatLocaleNumber(providerUsage.totalTokens ?? 0)}`,
      ].join(', ')
    : ''
  const providerChecksSummary = listSummary(backendProviderIntegration?.requiredChecks)
  const localProviderNoKey = backendProviderIntegration?.provider === 'ollama'
  const missingProviderSmokeChecks = listProviderSmokeMissingCheckIds(backendProviderIntegration)
    .map((checkId) => providerSmokeCheckLabel(t, checkId))
  const providerSmokeReady = hasProviderSmokeEvidence(backendProviderIntegration)
  const showProviderHandoff = hasReleaseReadiness
  const showProviderRemediation = showProviderHandoff && missingProviderSmokeChecks.length > 0
  const slackGatewaySmoke = readiness?.slackGatewaySmoke ?? null
  const slackRequiredChecks = listSummary(slackGatewaySmoke?.requiredChecks)
  const showSmokeHandoff = hasReleaseReadiness
  const showLangsmithSync = hasReleaseReadiness
  const showFeedbackReviewQueue = hasReleaseReadiness
  const a2aProtocol = readiness?.a2aProtocol ?? null
  const a2aAgentCard = a2aProtocol?.agentCard ?? null
  const a2aDiagnostics = a2aProtocol?.diagnostics ?? null
  const a2aNegotiation = a2aProtocol?.protocolNegotiation ?? null
  const a2aTaskApi = a2aProtocol?.taskApi ?? null
  const a2aOperational = a2aProtocol?.operationalEvidence ?? null
  const a2aBindings = listSummary(a2aAgentCard?.interfaceProtocolBindings)
  const a2aVersions = listSummary(a2aAgentCard?.interfaceProtocolVersions)
  const slackSmokeReady = hasSlackSmokeEvidence(slackGatewaySmoke)
  const a2aSmokeReady = hasA2aSmokeEvidence(a2aProtocol)
  const smokeVerified = slackSmokeReady && a2aSmokeReady && providerSmokeReady
  const smokeChecklistVisible = Boolean(
    slackGatewaySmoke
    || a2aProtocol
    || showProviderHandoff
    || releaseReadinessCommand,
  )
  const passedReports = tagRecommendation?.passedReports ?? []
  const minorBoundaryReports = tagRecommendation?.minorBoundaryReports ?? []
  const releaseWarnings = readiness?.warnings?.filter(Boolean) ?? []
  const warningReviewReports = uniqueList([
    ...warnings,
    ...releaseWarnings.map((warning) => warning.name),
  ])
  const warningReviewCommands = uniqueList([
    ...releaseWarnings.map((warning) => warning.reviewCommand),
    readiness?.dependencyWarnings?.reviewCommand,
  ])
  const warningRemediationCommands = uniqueList([
    ...releaseWarnings.map((warning) => warning.remediationCommand),
    readiness?.dependencyWarnings?.remediationCommand,
  ])
  const hasWarningReviewHandoff =
    Boolean(tagRecommendation?.warningReviewRequired)
    || warningReviewReports.length > 0
    || warningReviewCommands.length > 0
    || warningRemediationCommands.length > 0
  const blockerQueue = blockers.flatMap<BlockerQueueItem>((report) => {
    const exactRoute = releaseBlockingReportRoute(report)
    if (exactRoute && exactRoute.reportId !== 'smoke_run' && exactRoute.reportId !== 'preflight') {
      return [{
        key: report,
        report,
        gateId: null,
        path: exactRoute.path,
        stepNumber: exactRoute.stepNumber,
        gateLabel: t(exactRoute.titleKey),
        remediation: t('dashboard.release.blockerQueue.openOwningSurface'),
      }]
    }
    const gateIds = resolveReportGateIds(report)
    if (gateIds.length === 0) {
      return [{
        key: report,
        report,
        gateId: null,
        path: releaseReportPath(report),
        stepNumber: null,
        gateLabel: t('dashboard.release.blockerQueue.unknownGate'),
        remediation: t('dashboard.release.blockerQueue.unknownRemediation'),
      }]
    }
    return gateIds.map((gateId) => ({
      key: `${report}:${gateId}`,
      report,
      gateId,
      path: gatePaths[gateId],
      stepNumber: gateStepNumbers[gateId],
      gateLabel: t(`dashboard.release.gates.${gateId}`),
      remediation: t(`dashboard.release.gateRemediation.${gateId}`),
    }))
  })
  const primaryActionHandoff = aggregateActionHandoffs.find((handoff) => handoff.state === 'ready')
    ?? aggregateActionHandoffs[0]
    ?? null
  const primaryBlocker = blockerQueue[0] ?? null
  const decisionAction = primaryActionHandoff?.action.label
    || primaryActionHandoff?.action.id
    || primaryBlocker?.remediation
    || tagRecommendation?.nextAction
    || t('dashboard.release.decisionBrief.noAction')
  const decisionActionLabel = missingEvidenceTimestamp
    ? t('dashboard.release.decisionBrief.evidenceNotCurrent')
    : releaseDecisionActionLabel(decisionAction, t)
  const decisionPath = primaryActionHandoff?.itemPath ?? primaryBlocker?.path ?? null
  const decisionCommand = primaryActionHandoff?.command || releaseReadinessCommand
  const dependencyWarnings = readiness?.dependencyWarnings ?? null
  const dependencyWarningReviewRequired = dependencyWarnings?.warningReviewRequired === true
    || dependencyWarnings?.status === 'review_required'
  const dependencyWarningReports = listSummary(dependencyWarnings?.warningReports)
  const dependencyPackages = listSummary(dependencyWarnings?.checkedPackages)
  const dependencyVersions = mappingSummary(dependencyWarnings?.installedVersions)
  const dependencyPins = mappingSummary(dependencyWarnings?.directPins)
  const dependencyFindings = dependencyWarnings?.findings
    ?.map((finding) => [
      finding.package,
      finding.module,
      finding.deprecatedImport && finding.replacement
        ? `${finding.deprecatedImport} -> ${finding.replacement}`
        : finding.deprecatedImport,
      finding.severity,
    ].filter(Boolean).join(' / '))
    .filter(Boolean)
    .join(', ') ?? ''

  return (
    <section
      id={RELEASE_COCKPIT_ANCHOR_ID}
      className={`release-cockpit release-cockpit--${view}`}
      aria-labelledby={view === 'all' || view === 'decision' ? 'release-cockpit-title' : undefined}
      aria-label={view === 'boundary'
        ? t('releaseOperations.views.boundary')
        : view === 'evidence'
          ? t('releaseOperations.views.evidence')
          : undefined}
    >
      {(view === 'all' || view === 'decision') && (
        <>
          <div className="release-cockpit__header">
            <div>
              <h2 id="release-cockpit-title" className="release-cockpit__title">
                {t('dashboard.release.title')}
              </h2>
              <p className="release-cockpit__subtitle">
                {t('dashboard.release.subtitle')}
              </p>
            </div>
            <span className={`release-cockpit__status release-cockpit__status--${decisionStatus}`} role="status">
              <span aria-hidden="true" />
              {t(`dashboard.release.status.${decisionStatus}`)}
            </span>
          </div>

          <dl className="release-cockpit__summary" aria-label={t('dashboard.release.summaryLabel')}>
            <div className="release-cockpit__metric">
              <dt className="release-cockpit__metric-label">{t('dashboard.release.recommendedTag')}</dt>
              <dd className="release-cockpit__metric-value">{recommendedTag}</dd>
            </div>
            <div className="release-cockpit__metric">
              <dt className="release-cockpit__metric-label">{t('dashboard.release.versionBump')}</dt>
              <dd className="release-cockpit__metric-value">{versionBumpLabel}</dd>
            </div>
            <div className="release-cockpit__metric">
              <dt className="release-cockpit__metric-label">{t('dashboard.release.minorBoundary')}</dt>
              <dd className="release-cockpit__metric-value">
                {minorEligible ? t('common.yes') : t('common.no')}
              </dd>
            </div>
          </dl>
        </>
      )}

      <div
        className="release-cockpit__decision-brief"
        data-release-section="decision"
        aria-label={t('dashboard.release.decisionBrief.title')}
      >
        <div className="release-cockpit__decision-brief-head">
          <span className="release-cockpit__decision-brief-title">
            {t('dashboard.release.decisionBrief.title')}
          </span>
        </div>
        <dl className="release-cockpit__decision-brief-grid">
          <div className="release-cockpit__decision-brief-action">
            <dt>{t('dashboard.release.decisionBrief.nextAction')}</dt>
            <dd>{decisionActionLabel}</dd>
          </div>
          <div>
            <dt>{t('dashboard.release.decisionBrief.owningSurface')}</dt>
            <dd>
              {decisionPath
                ? <Link to={decisionPath}>{t('dashboard.release.decisionBrief.openSurface')}</Link>
                : t('dashboard.release.decisionBrief.noOwningSurface')}
            </dd>
          </div>
          <div>
            <dt>{t('dashboard.release.decisionBrief.latestVerifiedTag')}</dt>
            <dd>{latestVerifiedTag || t('dashboard.release.noTag')}</dd>
          </div>
          <div>
            <dt>{t('dashboard.release.decisionBrief.evidenceSyncedAt')}</dt>
            <dd>
              {readiness?.syncedAt
                ? <TimestampWithZone value={readiness.syncedAt} />
                : t('dashboard.release.decisionBrief.notReported')}
            </dd>
          </div>
          <div>
            <dt>{t('dashboard.release.decisionBrief.provenance')}</dt>
            <dd>
              {provenanceVerified
                ? t('dashboard.release.decisionBrief.provenanceVerified')
                : readinessProvenanceReason(t, provenance?.reason)}
            </dd>
          </div>
        </dl>
        {provenance && (
          <details className="release-cockpit__decision-technical">
            <summary>{t('dashboard.release.decisionBrief.showProvenance')}</summary>
            <dl className="release-cockpit__decision-brief-grid release-cockpit__decision-provenance-grid">
              <div>
                <dt>{t('dashboard.release.decisionBrief.currentCommit')}</dt>
                <dd><code>{provenance.commitSha || t('dashboard.release.decisionBrief.notReported')}</code></dd>
              </div>
              <div>
                <dt>{t('dashboard.release.decisionBrief.expectedCommit')}</dt>
                <dd><code>{provenance.expectedCommitSha || t('dashboard.release.decisionBrief.notReported')}</code></dd>
              </div>
              <div>
                <dt>{t('dashboard.release.decisionBrief.inputHash')}</dt>
                <dd><code>{provenance.inputHash || t('dashboard.release.decisionBrief.notReported')}</code></dd>
              </div>
            </dl>
          </details>
        )}
        {decisionCommand && (
          <details className="release-cockpit__decision-technical">
            <summary>{t('dashboard.release.decisionBrief.showCommand')}</summary>
            <div className="release-cockpit__decision-command">
              <code>{decisionCommand}</code>
              <CopyButton
                value={decisionCommand}
                label={t('dashboard.release.decisionBrief.copyCommand')}
              />
            </div>
          </details>
        )}
      </div>

      {showAggregateDiagnostics && (
        <details
          className="release-cockpit__warning"
          data-release-section="decision"
          aria-label={t('dashboard.release.aggregateDiagnostics.title')}
          open={status === 'blocked'}
        >
          <summary className="release-cockpit__warning-head">
            <span className="release-cockpit__warning-title">
              {t('dashboard.release.aggregateDiagnostics.title')}
            </span>
            <StatusBadge
              status={statusToBadge[status]}
              label={t(`dashboard.release.status.${status}`)}
            />
            <ChevronDown className="release-cockpit__disclosure-icon" size={16} aria-hidden="true" />
          </summary>
          <dl className="release-cockpit__warning-grid">
            {aggregateSummary && (
              <div>
                <dt>{t('dashboard.release.aggregateDiagnostics.summary')}</dt>
                <dd>{t('dashboard.release.aggregateDiagnostics.summaryValue', { summary: aggregateSummary })}</dd>
              </div>
            )}
            {readiness?.failureSummary && (
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.aggregateDiagnostics.failureSummary')}</dt>
                <dd>
                  <code>{readiness.failureSummary}</code>
                </dd>
              </div>
            )}
            {(readyNextActionIds.length > 0 || nextActionStates) && (
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.aggregateDiagnostics.readyActions')}</dt>
                <dd>
                  {[readyNextActionIds.join(', '), nextActionStates].filter(Boolean).join(' / ')}
                </dd>
              </div>
            )}
            {aggregateActionHandoffs.length > 0 && (
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.aggregateDiagnostics.actionHandoff')}</dt>
                <dd>
                  <ul
                    className="release-cockpit__command-list"
                    aria-label={t('dashboard.release.aggregateDiagnostics.actionHandoff')}
                  >
                    {aggregateActionHandoffs.map(({ action, command, itemName, itemPath, state }, index) => (
                      <li key={`${action.id ?? 'action'}-${index}`}>
                        <span>
                          {action.id || action.label || t('dashboard.release.aggregateDiagnostics.nextActions')}
                          {state ? `: ${state}` : ''}
                        </span>
                        {itemName ? (
                          <span>
                            {t('dashboard.release.aggregateDiagnostics.itemName')}: {' '}
                            {itemPath ? <Link to={itemPath}>{itemName}</Link> : itemName}
                          </span>
                        ) : null}
                        {action.label ? <span>{action.label}</span> : null}
                        {action.missingEnv?.length ? (
                          <span>{action.missingEnv.join(', ')}</span>
                        ) : null}
                        {command && (
                          <span className="release-cockpit__warning-command">
                            <CopyButton
                              value={command}
                              label={t('dashboard.release.aggregateDiagnostics.copyCommand')}
                            />
                            <span>{command}</span>
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            )}
            {aggregateItems.length > 0 && (
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.aggregateDiagnostics.items')}</dt>
                <dd>
                  <ul className="release-cockpit__command-list">
                    {aggregateItems.map((item, index) => {
                      const nextActions = item.nextActions?.filter(Boolean) ?? []
                      const itemPath = item.name ? releaseReportPath(item.name) : null
                      return (
                        <li key={`${item.name ?? 'item'}-${index}`}>
                          <dl className="release-cockpit__warning-grid">
                            <div>
                              <dt>{t('dashboard.release.aggregateDiagnostics.itemName')}</dt>
                              <dd>
                                {item.name
                                  ? itemPath
                                    ? <Link to={itemPath}>{item.name}</Link>
                                    : item.name
                                  : t('dashboard.release.warningEvidence.missing')}
                              </dd>
                            </div>
                            <div>
                              <dt>{t('dashboard.release.aggregateDiagnostics.itemStatus')}</dt>
                              <dd>
                                <StatusBadge
                                  status={readinessItemStatusBadge(item)}
                                  label={item.status || t('dashboard.release.warningEvidence.missing')}
                                />
                              </dd>
                            </div>
                            {item.artifact && (
                              <div>
                                <dt>{t('dashboard.release.aggregateDiagnostics.artifact')}</dt>
                                <dd>{item.artifact}</dd>
                              </div>
                            )}
                            {item.failure && (
                              <div className="release-cockpit__warning-wide">
                                <dt>{t('dashboard.release.aggregateDiagnostics.failure')}</dt>
                                <dd>{item.failure}</dd>
                              </div>
                            )}
                            {item.preflightMissingEnv?.length ? (
                              <div className="release-cockpit__warning-wide">
                                <dt>{t('dashboard.release.aggregateDiagnostics.missingEnv')}</dt>
                                <dd>{item.preflightMissingEnv.join(', ')}</dd>
                              </div>
                            ) : null}
                            {nextActions.length > 0 && (
                              <div className="release-cockpit__warning-wide">
                                <dt>{t('dashboard.release.aggregateDiagnostics.nextActions')}</dt>
                                <dd>
                                  <ul className="release-cockpit__command-list">
                                    {nextActions.map((action, actionIndex) => {
                                      const command = resolveReleaseNextActionCommand(action) ?? ''
                                      return (
                                        <li key={`${action.id ?? 'action'}-${actionIndex}`}>
                                          <span>{action.label || action.id || t('dashboard.release.aggregateDiagnostics.nextActions')}</span>
                                          {action.missingEnv?.length ? (
                                            <span>{action.missingEnv.join(', ')}</span>
                                          ) : null}
                                          {command && (
                                            <span className="release-cockpit__warning-command">
                                              <CopyButton
                                                value={command}
                                                label={t('dashboard.release.aggregateDiagnostics.copyCommand')}
                                              />
                                              <span>{command}</span>
                                            </span>
                                          )}
                                        </li>
                                      )
                                    })}
                                  </ul>
                                </dd>
                              </div>
                            )}
                          </dl>
                        </li>
                      )
                    })}
                  </ul>
                </dd>
              </div>
            )}
          </dl>
        </details>
      )}

      {tagRecommendation && evidenceCurrent && (
        <details
          className="release-cockpit__recommendation"
          data-release-section="decision"
          aria-label={t('dashboard.release.recommendation.title')}
        >
          <summary className="release-cockpit__recommendation-head">
            <span className="release-cockpit__recommendation-title">
              {t('dashboard.release.recommendation.title')}
            </span>
            <StatusBadge
              status={tagRecommendation.eligible === false ? 'FAIL' : 'PASS'}
              label={tagRecommendation.eligible === false
                ? t('dashboard.release.recommendation.ineligible')
                : t('dashboard.release.recommendation.eligible')}
            />
            <ChevronDown className="release-cockpit__disclosure-icon" size={16} aria-hidden="true" />
          </summary>
          <dl className="release-cockpit__recommendation-grid release-cockpit__disclosure-body">
            <div>
              <dt>{t('dashboard.release.recommendation.latestTag')}</dt>
              <dd>{tagRecommendation.latestTag || t('dashboard.release.noTag')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.recommendation.passedReports')}</dt>
              <dd>{renderLinkedReports(passedReports) ?? '-'}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.recommendation.minorBoundaryReports')}</dt>
              <dd>{renderLinkedReports(minorBoundaryReports) ?? '-'}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.recommendation.warningReview')}</dt>
              <dd>
                {tagRecommendation.warningReviewRequired
                  ? t('dashboard.release.warningReviewHandoff.reviewRequired')
                  : t('dashboard.release.warningReviewHandoff.reviewed')}
              </dd>
            </div>
          </dl>
          {tagRecommendation.nextAction && (
            <div className="release-cockpit__recommendation-action">
              <p>{releaseDecisionActionLabel(tagRecommendation.nextAction, t)}</p>
              <CopyButton
                value={releaseDecisionActionLabel(tagRecommendation.nextAction, t)}
                label={t('dashboard.release.recommendation.copyNextAction')}
              />
            </div>
          )}
        </details>
      )}

      {hasWarningReviewHandoff && evidenceCurrent && (
        <details
          className="release-cockpit__warning-review"
          data-release-section="decision"
          aria-label={t('dashboard.release.warningReviewHandoff.title')}
        >
          <summary className="release-cockpit__warning-review-head">
            <span className="release-cockpit__warning-review-title">
              {t('dashboard.release.warningReviewHandoff.title')}
            </span>
            <StatusBadge
              status={tagRecommendation?.warningReviewRequired ? 'WARN' : 'PASS'}
              label={tagRecommendation?.warningReviewRequired
                ? t('dashboard.release.warningReviewHandoff.reviewRequired')
                : t('dashboard.release.warningReviewHandoff.reviewed')}
            />
            <ChevronDown className="release-cockpit__disclosure-icon" size={16} aria-hidden="true" />
          </summary>
          <dl className="release-cockpit__warning-review-grid release-cockpit__disclosure-body">
            <div>
              <dt>{t('dashboard.release.warningReviewHandoff.status')}</dt>
              <dd>
                {tagRecommendation?.warningReviewRequired
                  ? t('dashboard.release.warningReviewHandoff.reviewRequired')
                  : t('dashboard.release.warningReviewHandoff.reviewed')}
              </dd>
            </div>
            <div>
              <dt>{t('dashboard.release.warningReviewHandoff.scope')}</dt>
              <dd>{t('dashboard.release.warningReviewHandoff.operatorScope')}</dd>
            </div>
            <div className="release-cockpit__warning-review-wide">
              <dt>{t('dashboard.release.warningReviewHandoff.nextAction')}</dt>
              <dd>{tagRecommendation?.nextAction
                ? releaseDecisionActionLabel(tagRecommendation.nextAction, t)
                : t('dashboard.release.warningReviewHandoff.operatorAction')}</dd>
            </div>
          </dl>
          <details className="release-cockpit__warning-technical">
            <summary>
              <span>{t('common.technicalDetails')}</span>
              <ChevronDown className="release-cockpit__disclosure-icon" size={16} aria-hidden="true" />
            </summary>
            <dl className="release-cockpit__warning-review-grid release-cockpit__disclosure-body">
              <div className="release-cockpit__warning-review-wide">
                <dt>{t('dashboard.release.warningReviewHandoff.reports')}</dt>
                <dd>{warningReviewReports.length > 0 ? warningReviewReports.join(', ') : t('dashboard.release.warningEvidence.missing')}</dd>
              </div>
              {warningReviewCommands.length > 0 && (
                <div className="release-cockpit__warning-review-wide">
                  <dt>{t('dashboard.release.warningReviewHandoff.reviewCommands')}</dt>
                  <dd>
                    <ul className="release-cockpit__command-list">
                      {warningReviewCommands.map((command) => (
                        <li key={command}>
                          <span className="release-cockpit__warning-command">
                            <CopyButton
                              value={command}
                              label={t('dashboard.release.warningReviewHandoff.copyReviewCommand')}
                            />
                            <span>{command}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </dd>
                </div>
              )}
              {warningRemediationCommands.length > 0 && (
                <div className="release-cockpit__warning-review-wide">
                  <dt>{t('dashboard.release.warningReviewHandoff.remediationCommands')}</dt>
                  <dd>
                    <ul className="release-cockpit__command-list">
                      {warningRemediationCommands.map((command) => (
                        <li key={command}>
                          <span className="release-cockpit__warning-command">
                            <CopyButton
                              value={command}
                              label={t('dashboard.release.warningReviewHandoff.copyRemediationCommand')}
                            />
                            <span>{command}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </dd>
                </div>
              )}
            </dl>
          </details>
        </details>
      )}

      <details
        className="release-cockpit__local-gates"
        data-release-section="decision"
        aria-label={t('dashboard.release.localGates.title')}
      >
        <summary className="release-cockpit__local-gates-head">
          <span className="release-cockpit__local-gates-title">
            {t('dashboard.release.localGates.title')}
          </span>
          <StatusBadge
            status={localEvidenceReady ? 'PASS' : 'WARN'}
            label={localEvidenceReady
              ? t('dashboard.release.localGates.evidenceReady')
              : t('dashboard.release.localGates.evidenceIncomplete')}
          />
          <ChevronDown className="release-cockpit__disclosure-icon" size={16} aria-hidden="true" />
        </summary>
        <ul className="release-cockpit__local-gates-list release-cockpit__disclosure-body">
          <li>{t('dashboard.release.localGates.ciDisabled')}</li>
          <li>{t('dashboard.release.localGates.localEvidence')}</li>
          <li>{t('dashboard.release.localGates.cleanMainUnverified')}</li>
          <li>
            {t('dashboard.release.localGates.latestVerifiedTag')}: {' '}
            <code>{latestVerifiedTag || t('dashboard.release.noTag')}</code>
          </li>
          <li>{t('dashboard.release.localGates.noProgressTags')}</li>
        </ul>
        <div className="release-cockpit__local-gates-commands">
          {localGateCommands.map((command) => (
            <code key={command}>{command}</code>
          ))}
        </div>
      </details>

      {productCapabilityBoundary && (
        <div
          className="release-cockpit__product-boundary"
          data-release-section="boundary"
          aria-label={t('dashboard.release.productBoundary.title')}
        >
          <div className="release-cockpit__product-boundary-head">
            <span className="release-cockpit__product-boundary-title">
              {t('dashboard.release.productBoundary.title')}
            </span>
            <StatusBadge
              status={productCapabilityBoundary.minorEligible ? 'PASS' : 'WARN'}
              label={productCapabilityBoundary.minorEligible
                ? t('dashboard.release.productBoundary.minorEligible')
                : t('dashboard.release.productBoundary.minorBlocked')}
            />
          </div>
          <dl className="release-cockpit__product-boundary-summary">
            <div>
              <dt>{t('dashboard.release.productBoundary.capability')}</dt>
              <dd>{t('dashboard.release.productBoundary.capabilitySummary')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.productBoundary.sourceReport')}</dt>
              <dd>
                {productCapabilityBoundary.sourceReport
                  ? <ReleaseReportLink report={productCapabilityBoundary.sourceReport} />
                  : t('dashboard.release.productBoundary.missing')}
              </dd>
            </div>
            <div>
              <dt>{t('dashboard.release.productBoundary.status')}</dt>
              <dd>
                {productCapabilityBoundary.status === 'passed'
                  ? t('dashboard.release.gateStatus.passed')
                  : productCapabilityBoundary.status === 'blocked'
                    ? t('dashboard.release.gateStatus.blocked')
                    : t('dashboard.release.productBoundary.missing')}
              </dd>
            </div>
            <div>
              <dt>{t('dashboard.release.productBoundary.missingEvidence')}</dt>
              <dd>{t('dashboard.release.productBoundary.missingCount', { count: productBoundaryMissingEvidence.length })}</dd>
            </div>
          </dl>

          <ol
            className="release-cockpit__product-boundary-gates"
            aria-label={t('dashboard.release.productBoundary.checklistTitle')}
          >
            {productBoundaryChecklist.map((item) => (
              <li key={item.gateId}>
                <Link to={item.path}>
                  <span className="release-cockpit__boundary-step">{item.stepNumber}</span>
                  <span className="release-cockpit__product-boundary-gate-copy">
                    <span>{item.gateLabel}</span>
                    <span>{t(`dashboard.release.gateRemediation.${item.gateId}`)}</span>
                  </span>
                  <span className={`release-cockpit__status release-cockpit__status--${item.gate.status}`}>
                    <span aria-hidden="true" />
                    {t(`dashboard.release.gateStatus.${item.gate.status}`)}
                  </span>
                </Link>
              </li>
            ))}
          </ol>

          <details className="release-cockpit__product-boundary-technical">
            <summary>{t('dashboard.release.productBoundary.technicalEvidence')}</summary>
            <dl className="release-cockpit__recommendation-grid">
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.productBoundary.capability')}</dt>
                <dd>{productCapabilityBoundary.capability || t('dashboard.release.productBoundary.missing')}</dd>
              </div>
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.productBoundary.evidence')}</dt>
                <dd>
                  {productBoundaryEvidence.length > 0 ? (
                    <ul className="release-cockpit__inline-list" aria-label={t('dashboard.release.productBoundary.evidenceLinks')}>
                      {productBoundaryEvidence.map((evidence) => {
                        const path = releaseBoundaryEvidencePath(evidence)
                        return (
                          <li key={evidence}>
                            {path ? <Link to={path}>{evidence}</Link> : <span>{evidence}</span>}
                          </li>
                        )
                      })}
                    </ul>
                  ) : t('dashboard.release.productBoundary.missing')}
                </dd>
              </div>
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.productBoundary.missingEvidence')}</dt>
                <dd>
                  {productBoundaryMissingEvidence.length > 0 ? (
                    <ul className="release-cockpit__inline-list" aria-label={t('dashboard.release.productBoundary.missingEvidenceLinks')}>
                      {productBoundaryMissingEvidence.map((evidence) => {
                        const path = releaseBoundaryEvidencePath(evidence)
                        return (
                          <li key={evidence}>
                            {path ? <Link to={path}>{evidence}</Link> : <span>{evidence}</span>}
                          </li>
                        )
                      })}
                    </ul>
                  ) : t('dashboard.release.productBoundary.noneMissing')}
                </dd>
              </div>
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.productBoundaryFlow.title')}</dt>
                <dd>
                  <ProductCapabilityBoundaryFlowList
                    as="ul"
                    evidence={productBoundaryEvidence}
                    missingEvidence={productBoundaryMissingEvidence}
                    className="release-cockpit__inline-list"
                    ariaLabel={t('dashboard.release.productBoundaryFlow.title')}
                    stepClassName="release-cockpit__boundary-step"
                    fallbackEvidenceLabel={t('dashboard.release.productBoundary.missing')}
                    statusIconOnly
                  />
                </dd>
              </div>
            </dl>
          </details>
        </div>
      )}

      {hasReleaseReadiness && (
        <div
          className="release-cockpit__boundary-ops"
          data-release-section="boundary"
          aria-label={t('dashboard.release.productBoundaryOps.title')}
        >
          <div className="release-cockpit__boundary-ops-head">
            <span className="release-cockpit__boundary-ops-title">
              {t('dashboard.release.productBoundaryOps.title')}
            </span>
            <span className="release-cockpit__boundary-ops-desc">
              {t('dashboard.release.productBoundaryOps.description')}
            </span>
          </div>
          <ol className="release-cockpit__boundary-ops-list">
            {boundaryOpsQueue.map((item) => (
              <li key={item.id} className="release-cockpit__boundary-ops-item">
                <div className="release-cockpit__boundary-ops-item-head">
                  <Link to={item.href} className="release-cockpit__boundary-ops-link">
                    <span className="release-cockpit__boundary-step">{item.stepNumber}</span>
                    <span>{item.title}</span>
                  </Link>
                  <StatusBadge status={item.status} label={item.statusLabel} />
                </div>
                <p>{item.description}</p>
                {item.missing.length > 0 && (
                  <p className="release-cockpit__boundary-ops-missing">
                    {t('dashboard.release.productBoundaryOps.missingCount', { count: item.missing.length })}: {' '}
                    {item.missing.join(', ')}
                  </p>
                )}
                <details className="release-cockpit__boundary-ops-evidence">
                  <summary>
                    {t('dashboard.release.productBoundaryOps.evidenceCount', { count: item.evidence.length })}
                  </summary>
                  <p>{item.evidence.length > 0 ? item.evidence.join(', ') : t('dashboard.release.productBoundaryOps.none')}</p>
                </details>
              </li>
            ))}
          </ol>
        </div>
      )}

      {releaseWarnings.length > 0 && (
        <details
          className="release-cockpit__warning"
          data-release-section="evidence"
          aria-label={t('dashboard.release.warningList.title')}
        >
          <summary className="release-cockpit__warning-head">
            <span className="release-cockpit__warning-title">
              {t('dashboard.release.warningList.title')}
            </span>
            <StatusBadge
              status="WARN"
              label={t('dashboard.release.warningList.count', { count: releaseWarnings.length })}
            />
            <ChevronDown className="release-cockpit__disclosure-icon" size={16} aria-hidden="true" />
          </summary>
          <div className="release-cockpit__warning-list">
            {releaseWarnings.map((warning, index) => {
              const findings = warningFindingsSummary(warning.findings)
              return (
                <div
                  key={`${warning.name ?? 'warning'}-${index}`}
                  className="release-cockpit__warning-item"
                >
                  <dl className="release-cockpit__warning-grid release-cockpit__warning-operator-grid">
                    <div>
                      <dt>{t('dashboard.release.warningList.operatorTitle')}</dt>
                      <dd>{releaseWarningOperatorTitle(warning, t)}</dd>
                    </div>
                    <div>
                      <dt>{t('dashboard.release.warningList.status')}</dt>
                      <dd>{t('dashboard.release.warningList.reviewRequired')}</dd>
                    </div>
                    <div className="release-cockpit__warning-wide">
                      <dt>{t('dashboard.release.warningList.operatorSummary')}</dt>
                      <dd>{releaseWarningOperatorSummary(warning, t)}</dd>
                    </div>
                    <div className="release-cockpit__warning-wide">
                      <dt>{t('dashboard.release.warningList.operatorAction')}</dt>
                      <dd>{releaseWarningOperatorAction(warning, t)}</dd>
                    </div>
                  </dl>
                  <details className="release-cockpit__warning-technical">
                    <summary>
                      <span>{t('common.technicalDetails')}</span>
                      <ChevronDown className="release-cockpit__disclosure-icon" size={16} aria-hidden="true" />
                    </summary>
                    <dl className="release-cockpit__warning-grid release-cockpit__disclosure-body">
                      <div className="release-cockpit__warning-wide">
                        <dt>{t('dashboard.release.warningList.name')}</dt>
                        <dd>{warning.name || t('dashboard.release.warningEvidence.missing')}</dd>
                      </div>
                      <div>
                        <dt>{t('dashboard.release.warningList.status')}</dt>
                        <dd>{warning.status || t('dashboard.release.warningEvidence.missing')}</dd>
                      </div>
                      <div>
                        <dt>{t('dashboard.release.warningList.source')}</dt>
                        <dd>{warning.source || t('dashboard.release.warningEvidence.missing')}</dd>
                      </div>
                      <div className="release-cockpit__warning-wide">
                        <dt>{t('dashboard.release.warningList.remediation')}</dt>
                        <dd>{warning.remediation || t('dashboard.release.warningEvidence.missing')}</dd>
                      </div>
                      <div className="release-cockpit__warning-wide">
                        <dt>{t('dashboard.release.warningList.findings')}</dt>
                        <dd>{findings || t('dashboard.release.warningEvidence.missing')}</dd>
                      </div>
                      {warning.reviewCommand && (
                        <div className="release-cockpit__warning-wide">
                          <dt>{t('dashboard.release.warningList.reviewCommand')}</dt>
                          <dd>
                            <span className="release-cockpit__warning-command">
                              <CopyButton
                                value={warning.reviewCommand}
                                label={t('dashboard.release.warningList.copyReviewCommand')}
                              />
                              <span>{warning.reviewCommand}</span>
                            </span>
                          </dd>
                        </div>
                      )}
                      {warning.remediationCommand && (
                        <div className="release-cockpit__warning-wide">
                          <dt>{t('dashboard.release.warningList.remediationCommand')}</dt>
                          <dd>
                          <span className="release-cockpit__warning-command">
                            <CopyButton
                              value={warning.remediationCommand}
                              label={t('dashboard.release.warningList.copyRemediationCommand')}
                            />
                            <span>{warning.remediationCommand}</span>
                          </span>
                          </dd>
                        </div>
                      )}
                    </dl>
                  </details>
                </div>
              )
            })}
          </div>
        </details>
      )}

      {dependencyWarnings && (
        <details
          className="release-cockpit__warning"
          data-release-section="evidence"
          aria-label={t('dashboard.release.warningEvidence.title')}
        >
          <summary className="release-cockpit__warning-head">
            <span className="release-cockpit__warning-title">
              {t('dashboard.release.warningEvidence.title')}
            </span>
            <StatusBadge
              status={dependencyWarningReviewRequired ? 'WARN' : 'PASS'}
              label={dependencyWarningReviewRequired
                ? t('dashboard.release.warningEvidence.reviewRequired')
                : t('dashboard.release.warningEvidence.reviewed')}
            />
            <ChevronDown className="release-cockpit__disclosure-icon" size={16} aria-hidden="true" />
          </summary>
          <dl className="release-cockpit__warning-grid release-cockpit__warning-operator-grid">
            <div>
              <dt>{t('dashboard.release.warningEvidence.status')}</dt>
              <dd>{dependencyWarningReviewRequired
                ? t('dashboard.release.warningEvidence.reviewRequired')
                : t('dashboard.release.warningEvidence.reviewed')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.warningEvidence.operatorTitle')}</dt>
              <dd>{t('dashboard.release.warningEvidence.dependencyTitle')}</dd>
            </div>
            <div className="release-cockpit__warning-wide">
              <dt>{t('dashboard.release.warningEvidence.operatorSummary')}</dt>
              <dd>{dependencyWarningOperatorSummary(dependencyWarnings, t)}</dd>
            </div>
          </dl>
          <details className="release-cockpit__warning-technical">
            <summary>
              <span>{t('common.technicalDetails')}</span>
              <ChevronDown className="release-cockpit__disclosure-icon" size={16} aria-hidden="true" />
            </summary>
            <dl className="release-cockpit__warning-grid release-cockpit__disclosure-body">
              <div>
                <dt>{t('dashboard.release.warningEvidence.status')}</dt>
                <dd>{dependencyWarnings.status || t('dashboard.release.warningEvidence.missing')}</dd>
              </div>
              <div>
                <dt>{t('dashboard.release.warningEvidence.source')}</dt>
                <dd>{dependencyWarnings.source || t('dashboard.release.warningEvidence.missing')}</dd>
              </div>
              <div>
                <dt>{t('dashboard.release.warningEvidence.reports')}</dt>
                <dd>{dependencyWarningReports || t('dashboard.release.warningEvidence.missing')}</dd>
              </div>
              <div>
                <dt>{t('dashboard.release.warningEvidence.packages')}</dt>
                <dd>{dependencyPackages || t('dashboard.release.warningEvidence.missing')}</dd>
              </div>
              <div>
                <dt>{t('dashboard.release.warningEvidence.findingCount')}</dt>
                <dd>{formatLocaleNumber(dependencyWarnings.findingCount ?? 0)}</dd>
              </div>
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.warningEvidence.findings')}</dt>
                <dd>{dependencyFindings || t('dashboard.release.warningEvidence.missing')}</dd>
              </div>
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.warningEvidence.versions')}</dt>
                <dd>{dependencyVersions || t('dashboard.release.warningEvidence.missing')}</dd>
              </div>
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.warningEvidence.pins')}</dt>
                <dd>
                  {[dependencyPins, dependencyWarnings.pinSource]
                    .filter(Boolean)
                    .join(` ${t('dashboard.release.warningEvidence.from')} `)
                    || t('dashboard.release.warningEvidence.missing')}
                </dd>
              </div>
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.warningEvidence.reviewCommand')}</dt>
                <dd>
                  {dependencyWarnings.reviewCommand ? (
                    <span className="release-cockpit__warning-command">
                      <CopyButton
                        value={dependencyWarnings.reviewCommand}
                        label={t('dashboard.release.warningEvidence.copyReviewCommand')}
                      />
                      <span>{dependencyWarnings.reviewCommand}</span>
                    </span>
                  ) : t('dashboard.release.warningEvidence.missing')}
                </dd>
              </div>
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.warningEvidence.resolverCheck')}</dt>
                <dd>
                  {[
                    dependencyWarnings.resolverCheck?.status,
                    dependencyWarnings.resolverCheck?.latestKnownFrom,
                    dependencyWarnings.resolverCheck?.command,
                  ].filter(Boolean).join(' / ') || t('dashboard.release.warningEvidence.missing')}
                </dd>
              </div>
            </dl>
            {dependencyWarnings.remediationCommand && (
              <div className="release-cockpit__warning-command release-cockpit__warning-command--note">
                <CopyButton
                  value={dependencyWarnings.remediationCommand}
                  label={t('dashboard.release.warningEvidence.copyRemediationCommand')}
                />
                <span>{dependencyWarnings.remediationCommand}</span>
              </div>
            )}
          </details>
        </details>
      )}

      {blockerQueue.length > 0 && (
        <div
          className="release-cockpit__blocker-queue"
          data-release-section="decision"
          aria-label={t('dashboard.release.blockerQueue.title')}
        >
          <div className="release-cockpit__blocker-queue-head">
            <span className="release-cockpit__blocker-queue-title">
              {t('dashboard.release.blockerQueue.title')}
            </span>
            <StatusBadge
              status="FAIL"
              label={t('dashboard.release.blockerQueue.count', { count: blockerQueue.length })}
            />
          </div>
          <ol className="release-cockpit__blocker-list">
            {blockerQueue.map((item) => (
              <li key={item.key} className="release-cockpit__blocker-item">
                {item.path ? (
                  <Link to={item.path} className="release-cockpit__blocker-link">
                    <span className="release-cockpit__blocker-step">
                      {item.stepNumber ?? '-'}
                    </span>
                    <span className="release-cockpit__blocker-copy">
                      <span className="release-cockpit__blocker-report">{item.report}</span>
                      <span className="release-cockpit__blocker-gate">{item.gateLabel}</span>
                      <span className="release-cockpit__blocker-remediation">{item.remediation}</span>
                    </span>
                  </Link>
                ) : (
                  <span className="release-cockpit__blocker-link release-cockpit__blocker-link--static">
                    <span className="release-cockpit__blocker-step">-</span>
                    <span className="release-cockpit__blocker-copy">
                      <span className="release-cockpit__blocker-report">{item.report}</span>
                      <span className="release-cockpit__blocker-gate">{item.gateLabel}</span>
                      <span className="release-cockpit__blocker-remediation">{item.remediation}</span>
                    </span>
                  </span>
                )}
              </li>
            ))}
          </ol>
          {releaseReadinessCommand && (
            <div className="release-cockpit__blocker-command">
              <div>
                <span className="release-cockpit__blocker-command-label">
                  {t('dashboard.release.blockerQueue.regenerate')}
                </span>
                <code>{releaseReadinessCommand}</code>
              </div>
              <CopyButton
                value={releaseReadinessCommand}
                label={t('dashboard.release.blockerQueue.releaseCommand')}
              />
            </div>
          )}
        </div>
      )}

      {smokeHandoffVisible && (
        <details
          className="release-cockpit__handoff"
          data-release-section="evidence"
          aria-label={t('dashboard.release.smokeHandoff.title')}
        >
          <summary className="release-cockpit__handoff-head">
            <span className="release-cockpit__handoff-title">
              {t('dashboard.release.smokeHandoff.title')}
            </span>
            <Link className="btn btn-secondary btn-sm" to={RELEASE_WORKFLOW_PATHS_BY_ID.integrations}>
              {t('dashboard.release.smokeHandoff.openIntegrationSmoke')}
            </Link>
            <StatusBadge
              status="FAIL"
              label={t('dashboard.release.smokeHandoff.blocked')}
            />
          </summary>
          <dl className="release-cockpit__handoff-grid">
            {smokeMissingEnv && (
              <div>
                <dt>{t('dashboard.release.smokeHandoff.missingEnv')}</dt>
                <dd>{smokeMissingEnv}</dd>
              </div>
            )}
            {smokeMissingEnvAnyOf && (
              <div>
                <dt>{t('dashboard.release.smokeHandoff.missingEnvAnyOf')}</dt>
                <dd>{smokeMissingEnvAnyOf}</dd>
              </div>
            )}
            {smokeBlockerBreakdown.length > 0 && (
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.smokeHandoff.blockerBreakdown')}</dt>
                <dd>
                  <ol
                    className="release-cockpit__command-list"
                    aria-label={t('dashboard.release.smokeHandoff.blockerBreakdown')}
                  >
                    {smokeBlockerBreakdown.map(({ gateId, env }) => (
                      <li key={gateId}>
                        <Link to={gatePaths[gateId]}>
                          <span className="release-cockpit__blocker-step">
                            {gateStepNumbers[gateId]}
                          </span>
                          {t(`dashboard.release.gates.${gateId}`)}
                        </Link>
                        <span>{smokeBlockerDescription(t, gateId)}</span>
                        <code>{env.join(', ')}</code>
                      </li>
                    ))}
                  </ol>
                </dd>
              </div>
            )}
            {preflightEnvFileCommand && (
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.smokeHandoff.preflightCommand')}</dt>
                <dd>
                  <span className="release-cockpit__warning-command">
                    <CopyButton
                      value={preflightEnvFileCommand}
                      label={t('dashboard.release.smokeHandoff.copyPreflightCommand')}
                    />
                    <span>{preflightEnvFileCommand}</span>
                  </span>
                </dd>
              </div>
            )}
            {releaseSmokeEnvFileCommand && (
              <div className="release-cockpit__warning-wide">
                <dt>{t('dashboard.release.smokeHandoff.releaseSmokeCommand')}</dt>
                <dd>
                  <span className="release-cockpit__warning-command">
                    <CopyButton
                      value={releaseSmokeEnvFileCommand}
                      label={t('dashboard.release.smokeHandoff.copyReleaseSmokeCommand')}
                    />
                    <span>{releaseSmokeEnvFileCommand}</span>
                  </span>
                </dd>
              </div>
            )}
          </dl>
        </details>
      )}

      {(requiredReports.length > 0
        || missingReports.length > 0
        || requiredEnvAnyOf
        || missingEnvAnyOf
        || recommendedEnv
        || releaseReadinessCommand) && (
        <details
          className="release-cockpit__handoff"
          data-release-section="evidence"
          aria-label={t('dashboard.release.handoff.title')}
        >
          <summary className="release-cockpit__handoff-head">
            <span className="release-cockpit__handoff-title">
              {t('dashboard.release.handoff.title')}
            </span>
            <StatusBadge
              status={missingReports.length > 0 ? 'WARN' : 'PASS'}
              label={t('dashboard.release.handoff.reportSummary', {
                required: requiredReports.length,
                missing: missingReports.length,
              })}
            />
          </summary>
          {(requiredReports.length > 0
            || missingReports.length > 0
            || requiredEnvAnyOf
            || missingEnvAnyOf
            || recommendedEnv) && (
            <dl className="release-cockpit__handoff-grid">
              <div>
                <dt>{t('dashboard.release.handoff.requiredReports')}</dt>
                <dd>{requiredReportLinks ?? '-'}</dd>
              </div>
              <div>
                <dt>{t('dashboard.release.handoff.missingReports')}</dt>
                <dd>{missingReportLinks ?? t('dashboard.release.handoff.noneMissing')}</dd>
              </div>
              {requiredEnvAnyOf && (
                <div>
                  <dt>{t('dashboard.release.handoff.requiredEnvAnyOf')}</dt>
                  <dd>{requiredEnvAnyOf}</dd>
                </div>
              )}
              {missingEnvAnyOf && (
                <div>
                  <dt>{t('dashboard.release.handoff.missingEnvAnyOf')}</dt>
                  <dd>{missingEnvAnyOf}</dd>
                </div>
              )}
              {recommendedEnv && (
                <div>
                  <dt>{t('dashboard.release.handoff.recommendedEnv')}</dt>
                  <dd>{recommendedEnv}</dd>
                </div>
              )}
            </dl>
          )}
          {releaseReadinessCommand && (
            <div className="release-cockpit__command-row">
              <code className="release-cockpit__command">
                {releaseReadinessCommand}
              </code>
              <CopyButton
                value={releaseReadinessCommand}
                label={t('dashboard.release.handoff.copyCommand')}
              />
            </div>
          )}
        </details>
      )}

      {showLangsmithSync && (
        <details
          className="release-cockpit__langsmith"
          data-release-section="evidence"
          aria-label={t('dashboard.release.langsmith.title')}
        >
          <summary className="release-cockpit__langsmith-head">
            <span className="release-cockpit__langsmith-title">
              {t('dashboard.release.langsmith.title')}
            </span>
            <StatusBadge
              status={langsmithSync?.secretFree === false ? 'FAIL' : langsmithSyncReady ? 'PASS' : 'WARN'}
              label={langsmithSync?.secretFree === false
                ? t('dashboard.release.langsmith.secretScanFail')
                : langsmithSyncReady
                  ? t('dashboard.release.langsmith.secretScanPass')
                  : t('dashboard.release.langsmith.missing')}
            />
          </summary>
          <dl className="release-cockpit__langsmith-grid">
            <div>
              <dt>{t('dashboard.release.langsmith.dataset')}</dt>
              <dd>{langsmithSync?.datasetName || t('dashboard.release.langsmith.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.langsmith.examples')}</dt>
              <dd>{formatLocaleNumber(langsmithSync?.exampleCount ?? 0)}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.langsmith.cases')}</dt>
              <dd>{formatLocaleNumber(langsmithSync?.caseCount ?? 0)}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.langsmith.splits')}</dt>
              <dd>{splitSummary || t('dashboard.release.langsmith.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.langsmith.sdkContract')}</dt>
              <dd>{langsmithSync?.sdkContract || t('dashboard.release.langsmith.missing')}</dd>
            </div>
            <div className="release-cockpit__langsmith-wide">
              <dt>{t('dashboard.release.langsmith.sdkContractFields')}</dt>
              <dd>
                {sdkContractFieldsSummary
                  ? <code className="release-cockpit__langsmith-evidence">{sdkContractFieldsSummary}</code>
                  : t('dashboard.release.langsmith.missing')}
              </dd>
            </div>
            <div className="release-cockpit__langsmith-wide">
              <dt>{t('dashboard.release.langsmith.exampleContract')}</dt>
              <dd>
                {exampleContractSummary
                  ? <code className="release-cockpit__langsmith-evidence">{exampleContractSummary}</code>
                  : t('dashboard.release.langsmith.missing')}
              </dd>
            </div>
            <div>
              <dt>{t('dashboard.release.langsmith.exampleIds')}</dt>
              <dd>{exampleIdsSummary || t('dashboard.release.langsmith.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.langsmith.caseIds')}</dt>
              <dd>{caseIdsSummary || t('dashboard.release.langsmith.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.langsmith.metadataCaseIds')}</dt>
              <dd>{metadataCaseIdsSummary || t('dashboard.release.langsmith.missing')}</dd>
            </div>
          </dl>
        </details>
      )}

      {ragIngestionLifecycle && (
        <details
          className="release-cockpit__rag"
          data-release-section="evidence"
          aria-label={t('dashboard.release.rag.title')}
        >
          <summary className="release-cockpit__rag-head">
            <span className="release-cockpit__rag-title">
              {t('dashboard.release.rag.title')}
            </span>
            <StatusBadge
              status={ragIngestionLifecycle.status === 'verified' ? 'PASS' : 'WARN'}
              label={ragIngestionLifecycle.status === 'verified'
                ? t('dashboard.release.rag.verified')
                : t('dashboard.release.rag.missing')}
            />
          </summary>
          <dl className="release-cockpit__rag-grid">
            <div>
              <dt>{t('dashboard.release.rag.runtime')}</dt>
              <dd>{ragRuntimeSummary || t('dashboard.release.rag.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.rag.embeddingBoundary')}</dt>
              <dd>{ragIngestionLifecycle.embeddingBoundary || t('dashboard.release.rag.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.rag.citationStyle')}</dt>
              <dd>{ragAnswerContract?.citationStyle || t('dashboard.release.rag.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.rag.sourceLabels')}</dt>
              <dd>
                {formatBoolean(
                  ragAnswerContract?.requiresSourceLabels,
                  t('dashboard.release.rag.required'),
                  t('dashboard.release.rag.optional'),
                  t('dashboard.release.rag.missing'),
                )}
              </dd>
            </div>
            <div>
              <dt>{t('dashboard.release.rag.uncitedClaims')}</dt>
              <dd>
                {formatBoolean(
                  ragAnswerContract?.uncitedClaimsAllowed,
                  t('dashboard.release.rag.allowed'),
                  t('dashboard.release.rag.blocked'),
                  t('dashboard.release.rag.missing'),
                )}
              </dd>
            </div>
            <div>
              <dt>{t('dashboard.release.rag.readinessContracts')}</dt>
              <dd>{ragReleaseContracts || t('dashboard.release.rag.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.rag.diagnosticsApi')}</dt>
              <dd>{ragDiagnosticsApi || t('dashboard.release.rag.missing')}</dd>
            </div>
            <div className="release-cockpit__rag-wide">
              <dt>{t('dashboard.release.rag.poisoningEvalCases')}</dt>
              <dd>{ragPoisoningEvalCases || t('dashboard.release.rag.missing')}</dd>
            </div>
          </dl>
        </details>
      )}

      {showFeedbackReviewQueue && (
        <details
          className="release-cockpit__feedback"
          data-release-section="evidence"
          aria-label={t('dashboard.release.feedback.title')}
        >
          <summary className="release-cockpit__feedback-head">
            <span className="release-cockpit__feedback-title">
              {t('dashboard.release.feedback.title')}
            </span>
            <StatusBadge
              status={feedbackReviewQueue?.status === 'passed' ? 'PASS' : 'WARN'}
              label={feedbackReviewQueue?.status === 'passed'
                ? t('dashboard.release.feedback.reviewed')
                : t('dashboard.release.feedback.missing')}
            />
          </summary>
          {feedbackReviewQueue?.reviewNote && (
            <p className="release-cockpit__feedback-note">{feedbackReviewQueue.reviewNote}</p>
          )}
          <dl className="release-cockpit__feedback-grid">
            <div>
              <dt>{t('dashboard.release.feedback.candidateTag')}</dt>
              <dd>{feedbackReviewQueue?.candidateTag || t('dashboard.release.feedback.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.feedback.caseIds')}</dt>
              <dd>{feedbackCaseIds || t('dashboard.release.feedback.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.feedback.reviewTags')}</dt>
              <dd>{feedbackReviewTags || t('dashboard.release.feedback.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.feedback.ratingCounts')}</dt>
              <dd>{feedbackRatingCounts || t('dashboard.release.feedback.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.feedback.sourceCounts')}</dt>
              <dd>{feedbackSourceCounts || t('dashboard.release.feedback.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.feedback.workflowCounts')}</dt>
              <dd>{feedbackWorkflowCounts || t('dashboard.release.feedback.missing')}</dd>
            </div>
            <div className="release-cockpit__feedback-wide">
              <dt>{t('dashboard.release.feedback.expectedCitationCounts')}</dt>
              <dd>{feedbackExpectedCitationCounts || t('dashboard.release.feedback.missing')}</dd>
            </div>
          </dl>
        </details>
      )}

      {showSmokeHandoff && (
        <details
          className="release-cockpit__smoke"
          data-release-section="evidence"
          aria-label={t('dashboard.release.smoke.title')}
        >
          <summary className="release-cockpit__smoke-head">
            <span className="release-cockpit__smoke-title">
              {t('dashboard.release.smoke.title')}
            </span>
            <span className="release-cockpit__surface-links">
              <Link to={gatePaths.slack}>{t('dashboard.release.smoke.openSlack')}</Link>
              <Link to={gatePaths.a2a}>{t('dashboard.release.smoke.openA2a')}</Link>
            </span>
            <StatusBadge
              status={smokeVerified ? 'PASS' : 'WARN'}
              label={smokeVerified
                ? t('dashboard.release.smoke.verified')
                : t('dashboard.release.smoke.needsEvidence')}
            />
          </summary>
          <dl className="release-cockpit__smoke-grid">
            <div>
              <dt>{t('dashboard.release.smoke.slackGateway')}</dt>
              <dd>{slackGatewaySmoke?.gateway || t('dashboard.release.smoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.smoke.slackIngress')}</dt>
              <dd>{slackGatewaySmoke?.ingress || t('dashboard.release.smoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.smoke.slackReplyRoute')}</dt>
              <dd>{slackGatewaySmoke?.currentThreadReplyRoute || t('dashboard.release.smoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.smoke.slackChecks')}</dt>
              <dd>{slackRequiredChecks || t('dashboard.release.smoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.smoke.slackPolicy')}</dt>
              <dd>
                {[
                  `${t('dashboard.release.smoke.signature')}: ${formatBoolean(slackGatewaySmoke?.signatureVerificationRequired, t('common.yes'), t('common.no'), t('dashboard.release.smoke.missing'))}`,
                  `${t('dashboard.release.smoke.responseUrl')}: ${formatBoolean(slackGatewaySmoke?.responseUrlRouteSupported, t('common.yes'), t('common.no'), t('dashboard.release.smoke.missing'))}`,
                  `${t('dashboard.release.smoke.mcpOverlap')}: ${formatBoolean(slackGatewaySmoke?.mcpWriteOverlapForbidden, t('common.yes'), t('common.no'), t('dashboard.release.smoke.missing'))}`,
                ].join(', ')}
              </dd>
            </div>
            <div>
              <dt>{t('dashboard.release.smoke.a2aAgent')}</dt>
              <dd>{a2aAgentCard?.name || t('dashboard.release.smoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.smoke.a2aBindings')}</dt>
              <dd>{a2aBindings || t('dashboard.release.smoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.smoke.a2aVersions')}</dt>
              <dd>{a2aVersions || t('dashboard.release.smoke.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.smoke.a2aTaskApi')}</dt>
              <dd>
                {[a2aTaskApi?.status, a2aTaskApi?.taskStatus, a2aTaskApi?.path]
                  .filter(Boolean)
                  .join(' / ') || t('dashboard.release.smoke.missing')}
              </dd>
            </div>
            <div>
              <dt>{t('dashboard.release.smoke.a2aProtocol')}</dt>
              <dd>
                {[a2aDiagnostics?.protocolVersion, a2aNegotiation?.requestHeader, a2aNegotiation?.responseVersion]
                  .filter(Boolean)
                  .join(' / ') || t('dashboard.release.smoke.missing')}
              </dd>
            </div>
            <div className="release-cockpit__smoke-wide">
              <dt>{t('dashboard.release.smoke.a2aOperations')}</dt>
              <dd>
                {[
                  `${t('dashboard.release.smoke.audit')}: ${formatBoolean(a2aOperational?.auditRecorded, t('common.yes'), t('common.no'), t('dashboard.release.smoke.missing'))}`,
                  `${t('dashboard.release.smoke.idempotency')}: ${formatBoolean(a2aOperational?.idempotencyEnforced, t('common.yes'), t('common.no'), t('dashboard.release.smoke.missing'))}`,
                  `${t('dashboard.release.smoke.telemetry')}: ${formatBoolean(a2aOperational?.telemetryEnabled, t('common.yes'), t('common.no'), t('dashboard.release.smoke.missing'))}`,
                  `${t('dashboard.release.smoke.pushOutbox')}: ${formatBoolean(a2aOperational?.pushOutboxRouted, t('common.yes'), t('common.no'), t('dashboard.release.smoke.missing'))}`,
                  `${t('dashboard.release.smoke.secretFree')}: ${formatBoolean(a2aProtocol?.secretFree, t('common.yes'), t('common.no'), t('dashboard.release.smoke.missing'))}`,
                  `${t('dashboard.release.smoke.tls')}: ${formatBoolean(a2aProtocol?.tlsRequired, t('common.yes'), t('common.no'), t('dashboard.release.smoke.missing'))}`,
                ].join(', ')}
              </dd>
            </div>
          </dl>
        </details>
      )}

      {showProviderHandoff && (
        <details
          className="release-cockpit__provider"
          data-release-section="evidence"
          aria-label={t('dashboard.release.provider.title')}
        >
          <summary className="release-cockpit__provider-head">
            <span className="release-cockpit__provider-title">
              {t('dashboard.release.provider.title')}
            </span>
            <span className="release-cockpit__surface-links">
              <Link to={gatePaths.provider}>{t('dashboard.release.provider.openProvider')}</Link>
            </span>
            <StatusBadge
              status={providerSmokeReady ? 'PASS' : 'WARN'}
              label={providerSmokeReady
                ? t('dashboard.release.provider.verified')
                : t('dashboard.release.provider.missing')}
            />
          </summary>
          <dl className="release-cockpit__provider-grid">
            <div>
              <dt>{t('dashboard.release.provider.provider')}</dt>
              <dd>{backendProviderIntegration?.provider || t('dashboard.release.provider.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.provider.model')}</dt>
              <dd>{backendProviderIntegration?.model || t('dashboard.release.provider.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.provider.usage')}</dt>
              <dd>{providerUsageSummary || t('dashboard.release.provider.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.provider.source')}</dt>
              <dd>{providerUsage?.source || t('dashboard.release.provider.missing')}</dd>
            </div>
            <div>
              <dt>{t('dashboard.release.provider.breakdown')}</dt>
              <dd>{providerUsage?.totalMatchesBreakdown ? t('common.yes') : t('common.no')}</dd>
            </div>
            <div className="release-cockpit__provider-wide">
              <dt>{t('dashboard.release.provider.requiredChecks')}</dt>
              <dd>{providerChecksSummary || t('dashboard.release.provider.missing')}</dd>
            </div>
            {localProviderNoKey && (
              <div>
                <dt>{t('dashboard.release.provider.credentialMode')}</dt>
                <dd>
                  <span className="badge badge-green">
                    {t('dashboard.release.provider.localProviderNoKey')}
                  </span>
                </dd>
              </div>
            )}
          </dl>
          {showProviderRemediation && (
            <section
              className="release-cockpit__provider-remediation"
              aria-label={t('dashboard.release.provider.remediationTitle')}
            >
              <div>
                <h4>{t('dashboard.release.provider.remediationTitle')}</h4>
                <p>{t('dashboard.release.provider.remediationDesc')}</p>
              </div>
              <dl>
                <div>
                  <dt>{t('dashboard.release.provider.remediationMissing')}</dt>
                  <dd>
                    <ul>
                      {missingProviderSmokeChecks.map((check) => (
                        <li key={check}>{check}</li>
                      ))}
                    </ul>
                  </dd>
                </div>
              </dl>
              <div className="release-cockpit__provider-remediation-links">
                <Link to={gatePaths.provider}>{t('dashboard.release.provider.openProvider')}</Link>
                <Link to={RELEASE_WORKFLOW_PATHS_BY_ID.integrations}>
                  {t('dashboard.release.smoke.openIntegrationSmoke')}
                </Link>
              </div>
            </section>
          )}
        </details>
      )}

      {smokeChecklistVisible && (
        <details
          className="release-cockpit__smoke-checklist"
          data-release-section="evidence"
          aria-label={t('dashboard.release.smoke.checklistTitle')}
        >
          <summary className="release-cockpit__smoke-checklist-head">
            <span className="release-cockpit__smoke-checklist-title">
              {t('dashboard.release.smoke.checklistTitle')}
            </span>
            <StatusBadge
              status={smokeVerified && providerSmokeReady ? 'PASS' : 'WARN'}
              label={t('dashboard.release.smoke.checklistLabel')}
            />
          </summary>
          <ol className="release-cockpit__smoke-checklist-list">
            <li>
              <span>{t('dashboard.release.smoke.slackChecklist')}</span>
              <code>{slackRequiredChecks || t('dashboard.release.smoke.missing')}</code>
            </li>
            <li>
              <span>{t('dashboard.release.smoke.a2aChecklist')}</span>
              <code>
                {[a2aTaskApi?.status, a2aTaskApi?.taskStatus, a2aTaskApi?.path]
                  .filter(Boolean)
                  .join(' / ') || t('dashboard.release.smoke.missing')}
              </code>
            </li>
            <li>
              <span>{t('dashboard.release.smoke.providerChecklist')}</span>
              <code>{providerChecksSummary || t('dashboard.release.smoke.missing')}</code>
            </li>
            {releaseReadinessCommand && (
              <li>
                <span>{t('dashboard.release.smoke.commandChecklist')}</span>
                <span className="release-cockpit__warning-command">
                  <CopyButton
                    value={releaseReadinessCommand}
                    label={t('dashboard.release.smoke.copyReadinessCommand')}
                  />
                  <code>{releaseReadinessCommand}</code>
                </span>
              </li>
            )}
          </ol>
        </details>
      )}

      {view === 'all' && (blockers.length > 0 || warnings.length > 0 || !readiness) && (
        <div className="release-cockpit__notes">
          {!readiness && <span>{t('dashboard.release.missingEvidence')}</span>}
          {blockers.length > 0 && (
            <div className="release-cockpit__report-group">
              <span className="release-cockpit__report-label">
                {t('dashboard.release.blockers', { count: blockers.length })}
              </span>
              <ul className="release-cockpit__report-list" aria-label={t('dashboard.release.blockerListLabel')}>
                {blockers.map((report) => {
                  return (
                    <li key={report}>
                      <ReleaseReportLink report={report} />
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
          {warnings.length > 0 && (
            <div className="release-cockpit__report-group">
              <span className="release-cockpit__report-label">
                {t('dashboard.release.warnings', { count: warnings.length })}
              </span>
              <ul className="release-cockpit__report-list" aria-label={t('dashboard.release.warningListLabel')}>
                {warnings.map((report) => {
                  return (
                    <li key={report}>
                      <ReleaseReportLink report={report} />
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

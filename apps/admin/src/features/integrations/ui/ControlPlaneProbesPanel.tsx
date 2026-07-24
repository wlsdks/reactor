import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { CheckCircle2, ChevronRight, FileQuestion, HelpCircle } from 'lucide-react'
import { CopyButton, DataTable, EmptyState, HelpHint, SkeletonCard, SkeletonTable, RefreshButton, ReleaseReportLink, ReleaseReportList, StatusBadge, Tooltip } from '../../../shared/ui'
import {
  hasProviderSmokeEvidence,
  listProviderSmokeMissingCheckIds,
  type ProviderSmokeCheckId,
} from '../../../shared/lib/providerSmokeEvidence'
import {
  hasA2aSmokeEvidence,
  hasSlackSmokeEvidence,
  listA2aSmokeMissingCheckIds,
  listSlackSmokeMissingCheckIds,
  type A2aSmokeCheckId,
  type SlackSmokeCheckId,
} from '../../../shared/lib/liveSmokeEvidence'
import { resolveReleaseNextActionCommand } from '../../../shared/lib/releaseNextActionCommand'
import {
  RELEASE_A2A_PROTOCOL_ANCHOR_ID,
  RELEASE_A2A_PROTOCOL_PATH,
  RELEASE_INTEGRATION_SMOKE_ANCHOR_ID,
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_SMOKE_GATE_IDS,
  RELEASE_SLACK_GATEWAY_ANCHOR_ID,
  RELEASE_SLACK_GATEWAY_PATH,
  RELEASE_WORKFLOW_GATE_PATHS,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  releaseReportBelongsToGate,
  releaseReportPath,
  type ReleaseWorkflowGateId,
} from '../../../shared/releaseWorkflow'
import type { ControlPlaneProbeSnapshot, ControlPlaneProbeSummary } from '../controlPlaneProbes'
import { describeManifestStatus, describeProbeReason, describeProbeStatus } from './probeDescribers'
import type {
  DashboardReleaseGateSummary,
  DashboardReleaseNextAction,
  DashboardReleaseReadinessSummary,
} from '../../dashboard/types'
import { ExternalSmokeOperations } from './ExternalSmokeOperations'

/**
 * Manifest status cell — pairs a semantic icon with the existing label so
 * users with color-vision deficiency get a non-color cue (icon shape) in
 * addition to text, satisfying WCAG 1.4.1.
 *
 * Icon mapping:
 *  - declared: CheckCircle2 in --green
 *  - undeclared: FileQuestion in --yellow (semantic: "no manifest entry")
 *  - unknown: HelpCircle in --text-muted (manifest fetch failed / not loaded)
 */
function ManifestStatusCell({ row }: { row: ControlPlaneProbeSnapshot }) {
  const { t } = useTranslation()
  const label = describeManifestStatus(t, row)

  let Icon = HelpCircle
  let color = 'var(--text-muted)'
  if (row.manifestDeclared === true) {
    Icon = CheckCircle2
    color = 'var(--green)'
  } else if (row.manifestDeclared === false) {
    Icon = FileQuestion
    color = 'var(--yellow)'
  }

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)' }}>
      <Icon size={14} color={color} aria-hidden="true" />
      <span>{label}</span>
    </span>
  )
}

/**
 * Threshold-coloured latency cell — right-aligned monospace digits with
 * tabular-nums for vertical alignment across rows. Threshold colours give a
 * scannable health cue that pairs with the textual "{ms} ms" value (never
 * colour-only).
 *
 *   <100 ms  → muted (no concern)
 *   100-499  → primary text (normal)
 *   500-999  → yellow (slow)
 *   ≥1000    → red (very slow)
 */
function LatencyCell({ ms }: { ms: number }) {
  const { t } = useTranslation()
  let color = 'var(--text-muted)'
  if (ms >= 1000) color = 'var(--red)'
  else if (ms >= 500) color = 'var(--yellow)'
  else if (ms >= 100) color = 'var(--text-primary)'

  return (
    <span
      style={{
        display: 'block',
        textAlign: 'right',
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
        color,
      }}
      aria-label={t('integrationsPage.probes.latencyAria', { ms })}
    >
      {ms} ms
    </span>
  )
}

interface ControlPlaneProbesPanelProps {
  view?: 'overview' | 'run' | 'evidence'
  loading: boolean
  error: string | null
  probes: ControlPlaneProbeSnapshot[]
  summary: ControlPlaneProbeSummary | null
  releaseReadiness?: DashboardReleaseReadinessSummary | null
  onRefresh: () => Promise<unknown>
  onRefreshReadiness: () => Promise<unknown>
  readinessRefreshing?: boolean
}

const releaseSmokeProbeIds = new Set<ControlPlaneProbeSnapshot['id']>([
  'slackCommands',
  'slackEvents',
  'a2aDiagnostics',
  'providerModels',
])

function resolveGate(
  readiness: DashboardReleaseReadinessSummary | null | undefined,
  id: DashboardReleaseGateSummary['id'],
): DashboardReleaseGateSummary {
  return readiness?.gates?.find((gate) => gate.id === id) ?? { id, status: 'missing' }
}

function resolveSmokeGateReports(
  gateId: ReleaseWorkflowGateId,
  blockers: string[],
  warnings: string[],
): string[] {
  return [...blockers, ...warnings].filter((report) => releaseReportBelongsToGate(report, gateId))
}

function describeSmokeGateLabel(t: (key: string) => string, gateId: ReleaseWorkflowGateId): string {
  if (gateId === 'slack') return t('integrationsPage.releaseSmoke.gates.slack')
  if (gateId === 'a2a') return t('integrationsPage.releaseSmoke.gates.a2a')
  return t('integrationsPage.releaseSmoke.gates.provider')
}

function describeSmokeGateStatus(t: (key: string) => string, status: DashboardReleaseGateSummary['status']): string {
  if (status === 'passed') return t('integrationsPage.releaseSmoke.gateStatus.passed')
  if (status === 'warning') return t('integrationsPage.releaseSmoke.gateStatus.warning')
  if (status === 'blocked') return t('integrationsPage.releaseSmoke.gateStatus.blocked')
  return t('integrationsPage.releaseSmoke.gateStatus.missing')
}

function describeSmokeGateRemediation(t: (key: string) => string, gateId: ReleaseWorkflowGateId): string {
  if (gateId === 'slack') return t('integrationsPage.releaseSmoke.gateRemediation.slack')
  if (gateId === 'a2a') return t('integrationsPage.releaseSmoke.gateRemediation.a2a')
  return t('integrationsPage.releaseSmoke.gateRemediation.provider')
}

function describeSmokeGateActionLabel(t: (key: string) => string, gateId: ReleaseWorkflowGateId): string {
  if (gateId === 'slack') return t('integrationsPage.releaseSmoke.workflowSlack')
  if (gateId === 'a2a') return t('integrationsPage.releaseSmoke.workflowA2a')
  return t('integrationsPage.releaseSmoke.workflowProvider')
}

function describeSmokeGateNextAction(t: (key: string) => string, gateId: ReleaseWorkflowGateId): string {
  if (gateId === 'slack') return t('integrationsPage.releaseSmoke.actionGuidance.slack')
  if (gateId === 'a2a') return t('integrationsPage.releaseSmoke.actionGuidance.a2a')
  return t('integrationsPage.releaseSmoke.actionGuidance.provider')
}

function releaseGateStatusClassName(status: DashboardReleaseGateSummary['status']): string {
  if (status === 'passed') return 'release-evidence-status--pass'
  if (status === 'blocked') return 'release-evidence-status--fail'
  if (status === 'warning') return 'release-evidence-status--warn'
  return 'release-evidence-status--muted'
}

function ReleaseEvidenceStatus({
  status,
  t,
}: {
  status: DashboardReleaseGateSummary['status']
  t: TFunction
}) {
  return (
    <span className={`release-evidence-status ${releaseGateStatusClassName(status)}`}>
      <span aria-hidden="true" />
      {describeSmokeGateStatus(t, status)}
    </span>
  )
}

function resolveEvidenceDetailStatus(
  reportedStatus: string | null | undefined,
  contractReady: boolean,
): DashboardReleaseGateSummary['status'] {
  const normalized = reportedStatus?.trim().toLowerCase()
  if (normalized === 'verified' || normalized === 'passed' || normalized === 'ready') return 'passed'
  if (normalized === 'blocked' || normalized === 'failed' || normalized === 'fail') return 'blocked'
  if (normalized === 'warning' || normalized === 'warn') return 'warning'
  return contractReady ? 'passed' : 'warning'
}

function formatEnvAnyOf(groups: string[][] | null | undefined): string {
  return groups
    ?.filter((group) => group.length > 0)
    .map((group) => group.join(' or '))
    .join('; ') ?? ''
}

const releaseSmokeEnvGroups = [
  {
    id: 'slack',
    env: ['REACTOR_SLACK_BOT_TOKEN', 'REACTOR_SLACK_SIGNING_SECRET'],
  },
  {
    id: 'a2a',
    env: ['REACTOR_A2A_BASE_URL', 'REACTOR_A2A_API_KEY'],
  },
  {
    id: 'provider',
    env: ['OPENAI_API_KEY'],
  },
  {
    id: 'langsmith',
    env: ['LANGSMITH_API_KEY', 'REACTOR_OBSERVABILITY_LANGSMITH_API_KEY'],
  },
] as const

type ReleaseSmokeEnvGroupId = typeof releaseSmokeEnvGroups[number]['id']
type ReleaseSmokeEnvStatus = 'required' | 'recommended' | 'present'

function releaseSmokeEnvStatus(
  env: readonly string[],
  requiredEnvAnyOf: string[][] | null | undefined,
  missingEnvAnyOf: string[] | null | undefined,
  missingEnv: string[] | null | undefined,
  recommendedEnv: string[] | null | undefined,
): ReleaseSmokeEnvStatus {
  const names = new Set(env)
  const missing = missingEnvAnyOf?.some((name) => names.has(name)) === true
    || missingEnv?.some((name) => names.has(name)) === true
  const required = requiredEnvAnyOf?.some((group) => group.some((name) => names.has(name))) === true
  if (missing || required) return 'required'
  const recommended = recommendedEnv?.some((name) => names.has(name)) === true
  if (recommended) return 'recommended'
  return 'present'
}

function releaseSmokeEnvGroupLabel(t: TFunction, groupId: ReleaseSmokeEnvGroupId): string {
  if (groupId === 'slack') return t('integrationsPage.releaseSmoke.envGroups.slack')
  if (groupId === 'a2a') return t('integrationsPage.releaseSmoke.envGroups.a2a')
  if (groupId === 'provider') return t('integrationsPage.releaseSmoke.envGroups.provider')
  return t('integrationsPage.releaseSmoke.envGroups.langsmith')
}

function releaseSmokeEnvStatusLabel(t: TFunction, status: ReleaseSmokeEnvStatus): string {
  if (status === 'required') return t('integrationsPage.releaseSmoke.envRequired')
  if (status === 'recommended') return t('integrationsPage.releaseSmoke.envRecommended')
  return t('integrationsPage.releaseSmoke.envPresent')
}

function releaseSmokeEnvValueLabel(
  t: TFunction,
  group: { id: ReleaseSmokeEnvGroupId; env: readonly string[] },
  localProviderNoKey: boolean,
): string {
  if (group.id === 'provider' && localProviderNoKey) {
    return t('integrationsPage.releaseSmoke.localProviderNoKey')
  }
  return group.env.join(', ')
}

function releaseSmokeEnvGroupPath(groupId: ReleaseSmokeEnvGroupId): string {
  if (groupId === 'slack') return RELEASE_SLACK_GATEWAY_PATH
  if (groupId === 'a2a') return RELEASE_A2A_PROTOCOL_PATH
  if (groupId === 'provider') return RELEASE_WORKFLOW_PATHS_BY_ID.provider
  return RELEASE_LANGSMITH_SYNC_PATH
}

function releaseSmokeGateMissingEnv(
  gateId: ReleaseWorkflowGateId,
  readiness: DashboardReleaseReadinessSummary | null | undefined,
  localProviderNoKey = false,
): string[] {
  if (gateId === 'provider' && localProviderNoKey) return []
  const group = releaseSmokeEnvGroups.find((item) => item.id === gateId)
  if (!group) return []

  const missing = new Set([
    ...(readiness?.missingEnvAnyOf ?? []),
    ...(readiness?.tagRecommendation?.missingEnv ?? []),
  ])

  return group.env.filter((name) => missing.has(name))
}

function filterLocalProviderEnv(names: string[] | null | undefined, localProviderNoKey: boolean): string[] {
  const values = names?.filter(Boolean) ?? []
  if (!localProviderNoKey) return values
  return values.filter((name) => name !== 'OPENAI_API_KEY')
}

function formatList(values: string[] | null | undefined): string {
  return values?.filter(Boolean).join(', ') ?? ''
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

function renderLinkedReports(values: string[] | null | undefined) {
  return <ReleaseReportList reports={values} />
}

function resolveGateActionHandoffs(
  readiness: DashboardReleaseReadinessSummary | null | undefined,
  gateId: ReleaseWorkflowGateId,
) {
  const actionStates = readiness?.nextActionStates ?? {}
  const readyActionIds = new Set(readiness?.readyNextActionIds ?? [])
  const handoffs = new Map<string, {
    action: DashboardReleaseNextAction
    command: string | null
    itemName: string | null
    itemPath: string | null
    state: string | null
  }>()

  for (const item of readiness?.items ?? []) {
    const itemName = item.name ?? null
    const itemBelongsToGate = itemName ? releaseReportBelongsToGate(itemName, gateId) : false
    for (const action of item.nextActions ?? []) {
      const command = resolveReleaseNextActionCommand(action)
      const id = action.id?.trim() ?? ''
      const actionText = [
        id,
        action.label,
        command,
      ].filter(Boolean).join(' ').toLowerCase()
      const actionBelongsToGate =
        itemBelongsToGate
        || actionText.includes(gateId)
        || (gateId === 'slack' && actionText.includes('workspace'))
        || (gateId === 'a2a' && actionText.includes('peer'))
        || (gateId === 'provider' && actionText.includes('model'))
      if (!actionBelongsToGate) continue

      const key = id || `${itemName ?? gateId}:${action.label ?? ''}:${command ?? ''}`
      if (!key || handoffs.has(key)) continue
      handoffs.set(key, {
        action,
        command,
        itemName,
        itemPath: itemName ? releaseReportPath(itemName) : null,
        state: id ? actionStates[id] ?? (readyActionIds.has(id) ? 'ready' : null) : null,
      })
    }
  }

  return Array.from(handoffs.values())
}

function resolveGateReadinessItem(
  readiness: DashboardReleaseReadinessSummary | null | undefined,
  gateId: ReleaseWorkflowGateId,
) {
  return readiness?.items?.find((item) =>
    item.name ? releaseReportBelongsToGate(item.name, gateId) : false,
  ) ?? null
}

type BackendProviderIntegrationEvidence =
  DashboardReleaseReadinessSummary['backendProviderIntegration']

function slackSmokeCheckLabel(t: TFunction, checkId: SlackSmokeCheckId): string {
  const labels: Record<SlackSmokeCheckId, string> = {
    gateway: t('integrationsPage.releaseSmoke.slackGateway'),
    workspace: t('integrationsPage.releaseSmoke.slackWorkspace'),
    channel: t('integrationsPage.releaseSmoke.slackChannel'),
    bot_user: t('integrationsPage.releaseSmoke.slackBotUser'),
    ingress: t('integrationsPage.releaseSmoke.slackIngress'),
    reply_route: t('integrationsPage.releaseSmoke.slackReplyRoute'),
    signature: t('integrationsPage.releaseSmoke.signatureVerification'),
    response_url: t('integrationsPage.releaseSmoke.responseUrlRoute'),
    mcp_write_overlap: t('integrationsPage.releaseSmoke.mcpWriteOverlap'),
    auth_test: t('integrationsPage.releaseSmoke.slackAuthTest'),
    feedback_action: t('integrationsPage.releaseSmoke.slackFeedbackAction'),
    eval_promotion: t('integrationsPage.releaseSmoke.slackEvalPromotion'),
  }
  return labels[checkId]
}

function a2aSmokeCheckLabel(t: TFunction, checkId: A2aSmokeCheckId): string {
  const labels: Record<A2aSmokeCheckId, string> = {
    agent: t('integrationsPage.releaseSmoke.a2aAgent'),
    agent_card_path: t('integrationsPage.releaseSmoke.a2aAgentCardPath'),
    interfaces: t('integrationsPage.releaseSmoke.a2aInterfaces'),
    sdk_available: t('integrationsPage.releaseSmoke.a2aDiagnostics'),
    diagnostics_path: t('integrationsPage.releaseSmoke.a2aDiagnosticsPath'),
    negotiation: t('integrationsPage.releaseSmoke.a2aNegotiation'),
    sdk_fastapi_surface: t('integrationsPage.releaseSmoke.a2aSdkSurface'),
    server_task_ids: t('integrationsPage.releaseSmoke.a2aServerTaskIds'),
    telemetry: t('integrationsPage.releaseSmoke.a2aTelemetry'),
    task_api: t('integrationsPage.releaseSmoke.a2aTaskApi'),
    task_path: t('integrationsPage.releaseSmoke.a2aTaskPath'),
    operations: t('integrationsPage.releaseSmoke.a2aOperational'),
    secret_free: t('integrationsPage.releaseSmoke.secretFree'),
    tls_required: t('integrationsPage.releaseSmoke.tlsRequired'),
  }
  return labels[checkId]
}

function providerSmokeCheckLabel(t: TFunction, checkId: ProviderSmokeCheckId): string {
  const labels: Record<ProviderSmokeCheckId, string> = {
    provider: t('integrationsPage.releaseSmoke.providerName'),
    model: t('integrationsPage.releaseSmoke.providerModel'),
    usage_present: t('integrationsPage.releaseSmoke.providerUsagePresent'),
    usage_source: t('integrationsPage.releaseSmoke.providerUsageSource'),
    usage_tokens: t('integrationsPage.releaseSmoke.providerUsageTokens'),
    usage_breakdown: t('integrationsPage.releaseSmoke.providerTokenBreakdown'),
    required_usage_metadata: t('integrationsPage.releaseSmoke.providerRequiredChecks'),
  }
  return labels[checkId]
}

export function resolveProviderSmokeChecks(
  backendProviderIntegration: BackendProviderIntegrationEvidence | null | undefined,
  t: TFunction,
): Array<{ ok: boolean; label: string }> {
  const missing = new Set(listProviderSmokeMissingCheckIds(backendProviderIntegration))
  const checkIds: ProviderSmokeCheckId[] = [
    'provider',
    'model',
    'usage_present',
    'usage_source',
    'usage_tokens',
    'usage_breakdown',
    'required_usage_metadata',
  ]
  return checkIds.map((checkId) => ({
    ok: !missing.has(checkId),
    label: providerSmokeCheckLabel(t, checkId),
  }))
}

function buildEnvTemplate(items: Array<{ env: readonly string[] }>): string {
  const names = new Set<string>()
  for (const item of items) {
    for (const name of item.env) {
      if (name) names.add(name)
    }
  }
  return Array.from(names).map((name) => `${name}=`).join('\n')
}

export function ControlPlaneProbesPanel({
  view = 'overview',
  loading,
  error,
  probes,
  summary,
  releaseReadiness,
  onRefresh,
  onRefreshReadiness,
  readinessRefreshing,
}: ControlPlaneProbesPanelProps) {
  const { t } = useTranslation()
  const releaseSmokeProbes = probes.filter((probe) => releaseSmokeProbeIds.has(probe.id))
  const a2aSummaryProbe = releaseSmokeProbes.find((probe) => probe.id === 'a2aDiagnostics')
  const providerSummaryProbe = releaseSmokeProbes.find((probe) => probe.id === 'providerModels')
  const releaseSmokePassed = releaseSmokeProbes.filter((probe) => probe.status === 'PASS').length
  const releaseSmokeFailures = releaseSmokeProbes.filter((probe) => probe.status === 'FAIL').length
  const releaseSmokeDecision = releaseSmokeFailures > 0 || releaseReadiness?.status === 'blocked'
    ? 'fail'
    : releaseSmokePassed === releaseSmokeProbes.length && releaseSmokeProbes.length > 0
      ? 'pass'
      : 'warn'
  const releaseReadinessCommand = releaseReadiness?.tagRecommendation?.releaseReadinessCommand ?? null
  const requiredReports = releaseReadiness?.requiredReports ?? []
  const missingReports = releaseReadiness?.missingReports ?? []
  const blockers = releaseReadiness?.blockingReports ?? []
  const warnings = releaseReadiness?.warningReports ?? releaseReadiness?.tagRecommendation?.warningReports ?? []
  const requiredEnvAnyOf = formatEnvAnyOf(releaseReadiness?.requiredEnvAnyOf)
  const missingEnvAnyOf = releaseReadiness?.missingEnvAnyOf?.filter(Boolean).join(', ') ?? ''
  const preflightEnvFileCommand = releaseReadiness?.tagRecommendation?.preflightEnvFileCommand ?? null
  const releaseSmokeEnvFileCommand = releaseReadiness?.tagRecommendation?.releaseSmokeEnvFileCommand ?? null
  const backendProviderIntegration = releaseReadiness?.backendProviderIntegration ?? null
  const localProviderNoKey = backendProviderIntegration?.provider === 'ollama'
  const missingEnv = filterLocalProviderEnv(
    releaseReadiness?.tagRecommendation?.missingEnv,
    localProviderNoKey,
  ).join(', ')
  const recommendedEnv = filterLocalProviderEnv(
    releaseReadiness?.recommendedEnv,
    localProviderNoKey,
  ).join(', ')
  const envHandoffItems = releaseReadiness
    ? releaseSmokeEnvGroups.map((group) => {
      const env = group.id === 'provider' && localProviderNoKey ? [] : group.env
      return {
        ...group,
        env,
        status: releaseSmokeEnvStatus(
          env,
          releaseReadiness.requiredEnvAnyOf,
          releaseReadiness.missingEnvAnyOf,
          releaseReadiness.tagRecommendation?.missingEnv,
          releaseReadiness.recommendedEnv,
        ),
      }
    })
    : []
  const envTemplate = buildEnvTemplate(envHandoffItems)
  const slackGatewaySmoke = releaseReadiness?.slackGatewaySmoke ?? null
  const feedbackReviewQueue = releaseReadiness?.feedbackReviewQueue ?? null
  const langsmithSync = releaseReadiness?.langsmithSync ?? null
  const a2aProtocol = releaseReadiness?.a2aProtocol ?? null
  const providerUsage = backendProviderIntegration?.usageMetadata ?? null
  const a2aAgentCard = a2aProtocol?.agentCard ?? null
  const a2aDiagnostics = a2aProtocol?.diagnostics ?? null
  const a2aNegotiation = a2aProtocol?.protocolNegotiation ?? null
  const a2aTaskApi = a2aProtocol?.taskApi ?? null
  const a2aOperational = a2aProtocol?.operationalEvidence ?? null
  const missingSlackGatewayChecks = listSlackSmokeMissingCheckIds(slackGatewaySmoke)
    .map((checkId) => slackSmokeCheckLabel(t, checkId))
  const slackRemediationLabels = new Set([
    t('integrationsPage.releaseSmoke.signatureVerification'),
    t('integrationsPage.releaseSmoke.responseUrlRoute'),
    t('integrationsPage.releaseSmoke.mcpWriteOverlap'),
    t('integrationsPage.releaseSmoke.slackAuthTest'),
    t('integrationsPage.releaseSmoke.slackFeedbackAction'),
    t('integrationsPage.releaseSmoke.slackEvalPromotion'),
  ])
  const missingSlackRemediationChecks = missingSlackGatewayChecks
    .filter((label) => slackRemediationLabels.has(label))
  const slackGatewayReady = hasSlackSmokeEvidence(slackGatewaySmoke)
  const showSlackGatewayHandoff = releaseReadiness !== null && releaseReadiness !== undefined
  const slackFeedbackPromotedCaseIds = feedbackReviewQueue?.caseIds?.filter(Boolean) ?? []
  const slackFeedbackPromotedCases = formatList(slackFeedbackPromotedCaseIds)
  const slackFeedbackLangsmithCoverage = coverageSummary(slackFeedbackPromotedCaseIds, langsmithSync?.caseIds)
  const slackFeedbackMetadataCoverage = coverageSummary(slackFeedbackPromotedCaseIds, langsmithSync?.metadataCaseIds)
  const { covered: slackFeedbackSyncedCases, missing: slackFeedbackUnsyncedCases } = splitCoverage(
    slackFeedbackPromotedCaseIds,
    langsmithSync?.caseIds,
  )
  const { missing: slackFeedbackMetadataMissingCases } = splitCoverage(
    slackFeedbackPromotedCaseIds,
    langsmithSync?.metadataCaseIds,
  )
  const missingA2aProtocolChecks = listA2aSmokeMissingCheckIds(a2aProtocol)
    .map((checkId) => a2aSmokeCheckLabel(t, checkId))
  const a2aRemediationLabels = new Set([
    t('integrationsPage.releaseSmoke.a2aTaskApi'),
    t('integrationsPage.releaseSmoke.a2aTaskPath'),
    t('integrationsPage.releaseSmoke.a2aOperational'),
  ])
  const missingA2aRemediationChecks = missingA2aProtocolChecks
    .filter((label) => a2aRemediationLabels.has(label))
  const a2aProtocolReady = hasA2aSmokeEvidence(a2aProtocol)
  const showA2aProtocolHandoff = releaseReadiness !== null && releaseReadiness !== undefined
  const providerSmokeChecks = resolveProviderSmokeChecks(backendProviderIntegration, t)
  const missingProviderSmokeChecks = providerSmokeChecks
    .filter((item) => !item.ok)
    .map((item) => item.label)
  const providerUsageRemediationLabels = new Set([
    t('integrationsPage.releaseSmoke.providerUsagePresent'),
    t('integrationsPage.releaseSmoke.providerUsageTokens'),
    t('integrationsPage.releaseSmoke.providerTokenBreakdown'),
  ])
  const missingProviderUsageChecks = providerSmokeChecks
    .filter((item) => !item.ok && providerUsageRemediationLabels.has(item.label))
    .map((item) => item.label)
  const providerSmokeReady = hasProviderSmokeEvidence(backendProviderIntegration)
  const showProviderSmokeHandoff = releaseReadiness !== null && releaseReadiness !== undefined
  const slackGate = releaseReadiness ? resolveGate(releaseReadiness, 'slack') : null
  const a2aGate = releaseReadiness ? resolveGate(releaseReadiness, 'a2a') : null
  const providerGate = releaseReadiness ? resolveGate(releaseReadiness, 'provider') : null
  const slackGateItem = resolveGateReadinessItem(releaseReadiness, 'slack')
  const a2aGateItem = resolveGateReadinessItem(releaseReadiness, 'a2a')
  const providerGateItem = resolveGateReadinessItem(releaseReadiness, 'provider')
  const slackRelatedReports = resolveSmokeGateReports('slack', blockers, warnings)
  const a2aRelatedReports = resolveSmokeGateReports('a2a', blockers, warnings)
  const providerRelatedReports = resolveSmokeGateReports('provider', blockers, warnings)
  const slackMissingEnv = releaseSmokeGateMissingEnv('slack', releaseReadiness)
  const a2aMissingEnv = releaseSmokeGateMissingEnv('a2a', releaseReadiness)
  const providerMissingEnv = releaseSmokeGateMissingEnv('provider', releaseReadiness)

  const columns = [
    {
      key: 'endpoint',
      header: t('integrationsPage.probeEndpoint'),
      width: '22%',
      render: (row: ControlPlaneProbeSnapshot) => (
        <div>
          <strong>{t(`integrationsPage.probes.${row.id}`)}</strong>
          <div className="detail-note" style={{ marginTop: 'var(--space-2)' }}>
            <code>{row.path}</code>
          </div>
        </div>
      ),
    },
    {
      key: 'manifest',
      header: (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-1)' }}>
          {t('integrationsPage.probeManifest')}
          <HelpHint label={t('integrationsPage.help.manifest')} />
        </span>
      ),
      width: '14%',
      render: (row: ControlPlaneProbeSnapshot) => <ManifestStatusCell row={row} />,
    },
    {
      key: 'live',
      header: (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-1)' }}>
          {t('integrationsPage.probeLive')}
          <HelpHint label={t('integrationsPage.help.liveProbe')} />
        </span>
      ),
      width: '12%',
      render: (row: ControlPlaneProbeSnapshot) => (
        <StatusBadge status={row.status} label={describeProbeStatus(t, row.status)} />
      ),
    },
    {
      key: 'latency',
      header: t('integrationsPage.probeLatency'),
      width: '12%',
      render: (row: ControlPlaneProbeSnapshot) => <LatencyCell ms={row.durationMs} />,
    },
    {
      key: 'detail',
      header: t('integrationsPage.probeDetail'),
      width: '28%',
      render: (row: ControlPlaneProbeSnapshot) => {
        const detail = `${describeProbeReason(t, row)} ${row.detail}`.trim()
        return detail ? (
          <Tooltip content={detail}>
            <span className="text-truncate">
              {describeProbeReason(t, row)} {row.detail}
            </span>
          </Tooltip>
        ) : (
          <span className="text-truncate">
            {describeProbeReason(t, row)} {row.detail}
          </span>
        )
      },
    },
    {
      key: 'route',
      header: t('integrationsPage.probeRoute'),
      width: '12%',
      render: (row: ControlPlaneProbeSnapshot) => row.routePath
        ? <Link className="btn btn-secondary btn-sm" to={row.routePath}>{t('integrationsPage.openRelated')}</Link>
        : '-',
    },
  ]

  return (
    <section className="integrations-operations" data-view={view}>
      <div className="detail-section-header">
        <h2 className="section-title" style={{ marginBottom: 0 }}>{t('integrationsPage.controlPlaneTitle')}</h2>
        <RefreshButton onRefresh={onRefresh} isFetching={loading} />
      </div>
      <p className="detail-note">{t('integrationsPage.controlPlaneDescription')}</p>
      <div
        id={RELEASE_INTEGRATION_SMOKE_ANCHOR_ID}
        className="release-smoke-overview"
        role="region"
        aria-label={t('integrationsPage.releaseSmoke.title')}
      >
          {view === 'overview' && (
          <div className="release-smoke-overview__content">
          <div className="detail-section-header">
            <div>
              <h3 className="section-title" style={{ marginBottom: 0 }}>
                {t('integrationsPage.releaseSmoke.title')}
              </h3>
              <p className="detail-note" style={{ marginTop: 'var(--space-2)' }}>
                {t('integrationsPage.releaseSmoke.description')}
              </p>
            </div>
            <div
              className={`release-smoke-decision release-smoke-decision--${releaseSmokeDecision}`}
              role="status"
            >
              <span aria-hidden="true" />
              {t('integrationsPage.releaseSmoke.summary', {
                passed: releaseSmokePassed,
                total: releaseSmokeProbes.length,
              })}
            </div>
          </div>
          <dl className="release-smoke-summary">
            <div>
              <dt>{t('integrationsPage.releaseSmoke.slack')}</dt>
              <dd>{releaseSmokeProbes.filter((probe) => probe.id === 'slackCommands' || probe.id === 'slackEvents').filter((probe) => probe.status === 'PASS').length}/2</dd>
            </div>
            <div>
              <dt>{t('integrationsPage.releaseSmoke.a2a')}</dt>
              <dd>{a2aSummaryProbe
                ? describeProbeStatus(t, a2aSummaryProbe.status)
                : t('integrationsPage.statusLabels.unavailable')}</dd>
            </div>
            <div>
              <dt>{t('integrationsPage.releaseSmoke.provider')}</dt>
              <dd>{providerSummaryProbe
                ? describeProbeStatus(t, providerSummaryProbe.status)
                : t('integrationsPage.statusLabels.unavailable')}</dd>
            </div>
            <div>
              <dt>{t('integrationsPage.releaseSmoke.reports')}</dt>
              <dd>{missingReports.length === 0 ? requiredReports.length : `${requiredReports.length - missingReports.length}/${requiredReports.length}`}</dd>
            </div>
          </dl>
          </div>
          )}
          {view === 'evidence' && (
          <>
          {envHandoffItems.length > 0 && (
            <div
              className="release-smoke-env"
              aria-label={t('integrationsPage.releaseSmoke.envHandoffTitle')}
            >
              <div className="detail-section-header">
                <div>
                  <div className="release-smoke-env__heading">
                    <h4 className="section-title">
                    {t('integrationsPage.releaseSmoke.envHandoffTitle')}
                    </h4>
                    <HelpHint label={t('integrationsPage.releaseSmoke.envHandoffHelp')} />
                  </div>
                  <p className="detail-note">
                    {t('integrationsPage.releaseSmoke.envHandoffDescription')}
                  </p>
                </div>
              </div>
              <ul className="release-smoke-env__list">
                {envHandoffItems.map((item) => (
                  <li key={item.id}>
                    <Link className="release-smoke-env__service" to={releaseSmokeEnvGroupPath(item.id)}>
                      {releaseSmokeEnvGroupLabel(t, item.id)}
                    </Link>
                    <span className={`release-smoke-env__status release-smoke-env__status--${item.status}`}>
                      {releaseSmokeEnvStatusLabel(t, item.status)}
                    </span>
                  </li>
                ))}
              </ul>
              <details className="release-smoke-env__technical">
                <summary>
                  <span>{t('integrationsPage.releaseSmoke.technicalSetupTitle')}</span>
                  <ChevronRight size={16} aria-hidden="true" />
                </summary>
                <div className="release-smoke-env__technical-body">
                  <div className="release-smoke-reports">
                    <span>{t('integrationsPage.releaseSmoke.requiredReports')}</span>
                    {renderLinkedReports(requiredReports) ?? '-'}
                    {missingReports.length > 0 && (
                      <>
                        <span>{t('integrationsPage.releaseSmoke.missingReports')}</span>
                        {renderLinkedReports(missingReports)}
                      </>
                    )}
                  </div>
                  {(requiredEnvAnyOf || missingEnvAnyOf || missingEnv || recommendedEnv) && (
                    <div className="release-smoke-context">
                      {requiredEnvAnyOf && <span>{t('integrationsPage.releaseSmoke.requiredEnvAnyOf')}: {requiredEnvAnyOf}</span>}
                      {missingEnvAnyOf && <span>{t('integrationsPage.releaseSmoke.missingEnvAnyOf')}: {missingEnvAnyOf}</span>}
                      {missingEnv && <span>{t('integrationsPage.releaseSmoke.missingEnv')}: {missingEnv}</span>}
                      {recommendedEnv && <span>{t('integrationsPage.releaseSmoke.recommendedEnv')}: {recommendedEnv}</span>}
                    </div>
                  )}
                  <ul className="release-smoke-env__technical-list">
                    {envHandoffItems.map((item) => (
                      <li key={item.id}>
                        <span>{releaseSmokeEnvGroupLabel(t, item.id)}</span>
                        <code>{item.env.length > 0 ? item.env.join(', ') : releaseSmokeEnvValueLabel(t, item, localProviderNoKey)}</code>
                      </li>
                    ))}
                  </ul>
                  {envTemplate && (
                    <div className="release-smoke-env__template">
                      <div className="release-smoke-env__template-header">
                        <span>{t('integrationsPage.releaseSmoke.envTemplateTitle')}</span>
                        <CopyButton
                          value={envTemplate}
                          label={t('integrationsPage.releaseSmoke.copyEnvTemplate')}
                        />
                      </div>
                      <code>{envTemplate}</code>
                    </div>
                  )}
                  {(preflightEnvFileCommand || releaseSmokeEnvFileCommand) && (
                    <div className="release-smoke-env__commands">
                  {preflightEnvFileCommand && (
                    <div>
                      <CopyButton
                        value={preflightEnvFileCommand}
                        label={t('integrationsPage.releaseSmoke.copyPreflightCommand')}
                      />
                      <code>{preflightEnvFileCommand}</code>
                    </div>
                  )}
                  {releaseSmokeEnvFileCommand && (
                    <div>
                      <CopyButton
                        value={releaseSmokeEnvFileCommand}
                        label={t('integrationsPage.releaseSmoke.copyReleaseSmokeCommand')}
                      />
                      <code>{releaseSmokeEnvFileCommand}</code>
                    </div>
                  )}
                    </div>
                  )}
                </div>
              </details>
            </div>
          )}
          {releaseReadiness && (
            <section
              className="release-smoke-gates"
              aria-label={t('integrationsPage.releaseSmoke.gatesLabel')}
            >
              {RELEASE_SMOKE_GATE_IDS.map((gateId) => {
                const gate = resolveGate(releaseReadiness, gateId)
                const gateLabel = gate.label ?? describeSmokeGateLabel(t, gateId)
                const relatedReports = resolveSmokeGateReports(gateId, blockers, warnings)
                const gateMissingEnv = releaseSmokeGateMissingEnv(
                  gateId,
                  releaseReadiness,
                  localProviderNoKey,
                )
                const gatePath = RELEASE_WORKFLOW_GATE_PATHS[gateId]
                const gateActionHandoffs = resolveGateActionHandoffs(releaseReadiness, gateId)
                return (
                  <article key={gateId} className="release-smoke-gate">
                    <div className="release-smoke-gate__header">
                      <div className="release-smoke-gate__identity">
                        <span className={`release-evidence-status ${releaseGateStatusClassName(gate.status)}`}>
                          <span aria-hidden="true" />
                          {describeSmokeGateStatus(t, gate.status)}
                        </span>
                        <strong>{gateLabel}</strong>
                      </div>
                      <Link className="release-smoke-gate__link" to={gatePath}>
                        {t('integrationsPage.releaseSmoke.openGate', {
                          gate: describeSmokeGateActionLabel(t, gateId),
                        })}
                        <ChevronRight size={16} aria-hidden="true" />
                      </Link>
                    </div>
                    <p className="release-smoke-gate__description">
                      {describeSmokeGateRemediation(t, gateId)}
                    </p>
                    {gateActionHandoffs.length > 0 && (
                      <p className="release-smoke-gate__next-action">
                        <span>{t('integrationsPage.releaseSmoke.nextAction')}</span>
                        {describeSmokeGateNextAction(t, gateId)}
                      </p>
                    )}
                    <details className="release-smoke-gate__technical">
                      <summary>{t('integrationsPage.releaseSmoke.technicalEvidenceTitle')}</summary>
                      <dl>
                        <div>
                          <dt>{t('integrationsPage.releaseSmoke.detailGateReports')}</dt>
                          <dd>{relatedReports.length > 0
                            ? renderLinkedReports(relatedReports)
                            : t('integrationsPage.releaseSmoke.noRelatedReports')}</dd>
                        </div>
                        <div>
                          <dt>{t('integrationsPage.releaseSmoke.detailGateMissingEnv')}</dt>
                          <dd>{gateMissingEnv.length > 0
                            ? gateMissingEnv.join(', ')
                            : t('integrationsPage.releaseSmoke.noneMissing')}</dd>
                        </div>
                        {gateActionHandoffs.map(({ action, command, itemName, itemPath, state }) => (
                          <div key={action.id || `${itemName ?? gateId}:${action.label ?? ''}:${command ?? ''}`}>
                            <dt>{t('integrationsPage.releaseSmoke.actionQueueAction')}</dt>
                            <dd>
                              <span>{action.label || action.id || t('integrationsPage.releaseSmoke.noNextAction')}</span>
                              {state && <span className="release-smoke-gate__technical-state">{state}</span>}
                              {itemName && (itemPath ? <Link to={itemPath}>{itemName}</Link> : <span>{itemName}</span>)}
                              {command && (
                                <span className="integration-evidence-detail__command">
                                  <code>{command}</code>
                                  <CopyButton value={command} label={t('integrationsPage.releaseSmoke.nextActionCommand')} />
                                </span>
                              )}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    </details>
                  </article>
                )
              })}
            </section>
          )}
          </>
          )}
          {view === 'run' && (
          <ExternalSmokeOperations
            releaseReadiness={releaseReadiness}
            readinessRefreshing={readinessRefreshing}
            onRefreshReadiness={onRefreshReadiness}
          />
          )}
          {view === 'evidence' && (
          <>
          {showSlackGatewayHandoff && (
            <details
              id={RELEASE_SLACK_GATEWAY_ANCHOR_ID}
              className="integration-evidence-detail"
              aria-label={t('integrationsPage.releaseSmoke.slackGatewayTitle')}
            >
              <summary className="integration-evidence-detail__summary">
                <div>
                  <strong>
                    {t('integrationsPage.releaseSmoke.slackGatewayTitle')}
                  </strong>
                  <span>
                    {t('integrationsPage.releaseSmoke.slackGatewayDescription')}
                  </span>
                </div>
                <ReleaseEvidenceStatus
                  status={resolveEvidenceDetailStatus(slackGatewaySmoke?.status, slackGatewayReady)}
                  t={t}
                />
              </summary>
              <dl className="meta-grid" style={{ marginTop: 'var(--space-3)' }}>
                <span>{t('integrationsPage.releaseSmoke.detailGateStatus')}: {slackGate ? describeSmokeGateStatus(t, slackGate.status) : t('integrationsPage.releaseSmoke.missing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateReports')}: {slackRelatedReports.length > 0 ? slackRelatedReports.map((report, index) => (
                  <span key={`${report}-${index}`}>
                    {index > 0 && ', '}
                    <ReleaseReportLink report={report} includeStep />
                  </span>
                )) : t('integrationsPage.releaseSmoke.noneMissing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateMissingEnv')}: {slackMissingEnv.length > 0 ? slackMissingEnv.join(', ') : t('integrationsPage.releaseSmoke.noneMissing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateMode')}: {slackGateItem?.mode ?? t('integrationsPage.releaseSmoke.missing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateScope')}: {slackGateItem?.scope ?? t('integrationsPage.releaseSmoke.missing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateArtifact')}: {slackGateItem?.artifact ?? t('integrationsPage.releaseSmoke.missing')}</span>
              </dl>
              <dl className="meta-grid" style={{ marginTop: 'var(--space-3)' }}>
                <span>{t('integrationsPage.releaseSmoke.slackGateway')}: {slackGatewaySmoke?.gateway ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackWorkspace')}: {[
                  slackGatewaySmoke?.workspaceName,
                  slackGatewaySmoke?.workspaceId ? `(${slackGatewaySmoke.workspaceId})` : null,
                ].filter(Boolean).join(' ') || '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackChannel')}: {slackGatewaySmoke?.channelId ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackBotUser')}: {slackGatewaySmoke?.botUserId ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackIngress')}: {slackGatewaySmoke?.ingress ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackReplyRoute')}: {slackGatewaySmoke?.currentThreadReplyRoute ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackRequiredChecks')}: {formatList(slackGatewaySmoke?.requiredChecks) || '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackAuthTest')}: {slackGatewaySmoke?.authTestOk ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.slackFeedbackAction')}: {slackGatewaySmoke?.feedbackActionRoute ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackEvalPromotion')}: {slackGatewaySmoke?.evalPromotionRoute ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackFeedbackReviewStatus')}: {feedbackReviewQueue?.reviewStatus ?? feedbackReviewQueue?.status ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackFeedbackCandidateTag')}: {feedbackReviewQueue?.candidateTag ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackFeedbackPromotedCases')}: {slackFeedbackPromotedCases || '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackFeedbackLangsmithCoverage')}: {slackFeedbackLangsmithCoverage || '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackFeedbackSyncedCases')}: {slackFeedbackSyncedCases.length > 0 ? slackFeedbackSyncedCases.join(', ') : '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackFeedbackUnsyncedCases')}: {slackFeedbackUnsyncedCases.length > 0 ? slackFeedbackUnsyncedCases.join(', ') : '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackFeedbackMetadataCoverage')}: {slackFeedbackMetadataCoverage || '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.slackFeedbackMetadataMissingCases')}: {slackFeedbackMetadataMissingCases.length > 0 ? slackFeedbackMetadataMissingCases.join(', ') : '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.signatureVerification')}: {slackGatewaySmoke?.signatureVerificationRequired ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.responseUrlRoute')}: {slackGatewaySmoke?.responseUrlRouteSupported ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.mcpWriteOverlap')}: {slackGatewaySmoke?.mcpWriteOverlapForbidden ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.slackContract')}: {missingSlackGatewayChecks.length === 0
                  ? t('integrationsPage.releaseSmoke.contractReady')
                  : t('integrationsPage.releaseSmoke.contractMissing', {
                    fields: missingSlackGatewayChecks.join(', '),
                  })}</span>
              </dl>
              {missingSlackRemediationChecks.length > 0 && (
                <div
                  className="integration-evidence-detail__remediation"
                  role="region"
                  aria-label={t('integrationsPage.releaseSmoke.slackRemediation')}
                >
                  <div className="detail-section-header">
                    <div>
                      <h5 className="section-title" style={{ marginBottom: 0 }}>
                        {t('integrationsPage.releaseSmoke.slackRemediation')}
                      </h5>
                      <p className="detail-note" style={{ marginTop: 'var(--space-2)' }}>
                        {t('integrationsPage.releaseSmoke.slackRemediationDesc')}
                      </p>
                    </div>
                    <ReleaseEvidenceStatus status="warning" t={t} />
                  </div>
                  <dl className="meta-grid" style={{ marginTop: 'var(--space-3)' }}>
                    {missingSlackRemediationChecks.map((label) => (
                      <span key={label}>{label}</span>
                    ))}
                  </dl>
                  <div className="inline-actions" style={{ marginTop: 'var(--space-3)' }}>
                    <Link className="btn btn-secondary btn-sm" to={RELEASE_SLACK_GATEWAY_PATH}>
                      {t('integrationsPage.releaseSmoke.workflowSlack')}
                    </Link>
                    <Link className="btn btn-secondary btn-sm" to={RELEASE_WORKFLOW_PATHS_BY_ID.cockpit}>
                      {t('integrationsPage.releaseSmoke.workflowReadiness')}
                    </Link>
                  </div>
                </div>
              )}
            </details>
          )}
          {showA2aProtocolHandoff && (
            <details
              id={RELEASE_A2A_PROTOCOL_ANCHOR_ID}
              className="integration-evidence-detail"
              aria-label={t('integrationsPage.releaseSmoke.a2aProtocolTitle')}
            >
              <summary className="integration-evidence-detail__summary">
                <div>
                  <strong>
                    {t('integrationsPage.releaseSmoke.a2aProtocolTitle')}
                  </strong>
                  <span>
                    {t('integrationsPage.releaseSmoke.a2aProtocolDescription')}
                  </span>
                </div>
                <ReleaseEvidenceStatus
                  status={resolveEvidenceDetailStatus(a2aProtocol?.status, a2aProtocolReady)}
                  t={t}
                />
              </summary>
              <dl className="meta-grid" style={{ marginTop: 'var(--space-3)' }}>
                <span>{t('integrationsPage.releaseSmoke.detailGateStatus')}: {a2aGate ? describeSmokeGateStatus(t, a2aGate.status) : t('integrationsPage.releaseSmoke.missing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateReports')}: {a2aRelatedReports.length > 0 ? a2aRelatedReports.map((report, index) => (
                  <span key={`${report}-${index}`}>
                    {index > 0 && ', '}
                    <ReleaseReportLink report={report} includeStep />
                  </span>
                )) : t('integrationsPage.releaseSmoke.noneMissing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateMissingEnv')}: {a2aMissingEnv.length > 0 ? a2aMissingEnv.join(', ') : t('integrationsPage.releaseSmoke.noneMissing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateMode')}: {a2aGateItem?.mode ?? t('integrationsPage.releaseSmoke.missing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateScope')}: {a2aGateItem?.scope ?? t('integrationsPage.releaseSmoke.missing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateArtifact')}: {a2aGateItem?.artifact ?? t('integrationsPage.releaseSmoke.missing')}</span>
              </dl>
              <dl className="meta-grid" style={{ marginTop: 'var(--space-3)' }}>
                <span>{t('integrationsPage.releaseSmoke.a2aAgent')}: {a2aAgentCard?.name ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aAgentCardPath')}: {a2aAgentCard?.wellKnownPath ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aInterfaces')}: {a2aAgentCard?.interfaceCount ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aBindings')}: {formatList(a2aAgentCard?.interfaceProtocolBindings) || '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aVersions')}: {formatList(a2aAgentCard?.interfaceProtocolVersions) || '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aDiagnostics')}: {a2aDiagnostics?.protocolVersion ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aDiagnosticsPath')}: {a2aDiagnostics?.path ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aNegotiation')}: {a2aNegotiation?.requestHeader ?? '-'} {a2aNegotiation?.responseVersion ?? ''}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aRequestedVersion')}: {a2aNegotiation?.requestedVersion ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aMajorMinorOnly')}: {a2aNegotiation?.majorMinorOnly ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aAgentCardVersionsChecked')}: {a2aNegotiation?.agentCardVersionsChecked ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aSdkSurface')}: {a2aNegotiation?.sdkFastApiSurface ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aServerTaskIds')}: {a2aNegotiation?.serverGeneratedTaskIds ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aTelemetry')}: {a2aNegotiation?.telemetryInstrumentation ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aTaskApi')}: {a2aTaskApi?.status ?? '-'} {a2aTaskApi?.taskStatus ?? ''}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aTaskPath')}: {a2aTaskApi?.path ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aOperational')}: {[
                  a2aOperational?.auditRecorded ? 'audit' : null,
                  a2aOperational?.idempotencyEnforced ? 'idempotency' : null,
                  a2aOperational?.telemetryEnabled ? 'telemetry' : null,
                  a2aOperational?.pushOutboxRouted ? 'push_outbox' : null,
                ].filter(Boolean).join(', ') || '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.secretFree')}: {a2aProtocol?.secretFree ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.tlsRequired')}: {a2aProtocol?.tlsRequired ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.a2aContract')}: {missingA2aProtocolChecks.length === 0
                  ? t('integrationsPage.releaseSmoke.contractReady')
                  : t('integrationsPage.releaseSmoke.contractMissing', {
                    fields: missingA2aProtocolChecks.join(', '),
                  })}</span>
              </dl>
              {missingA2aRemediationChecks.length > 0 && (
                <div
                  className="integration-evidence-detail__remediation"
                  role="region"
                  aria-label={t('integrationsPage.releaseSmoke.a2aRemediation')}
                >
                  <div className="detail-section-header">
                    <div>
                      <h5 className="section-title" style={{ marginBottom: 0 }}>
                        {t('integrationsPage.releaseSmoke.a2aRemediation')}
                      </h5>
                      <p className="detail-note" style={{ marginTop: 'var(--space-2)' }}>
                        {t('integrationsPage.releaseSmoke.a2aRemediationDesc')}
                      </p>
                    </div>
                    <ReleaseEvidenceStatus status="warning" t={t} />
                  </div>
                  <dl className="meta-grid" style={{ marginTop: 'var(--space-3)' }}>
                    {missingA2aRemediationChecks.map((label) => (
                      <span key={label}>{label}</span>
                    ))}
                    {a2aDiagnostics?.path && (
                      <span>{t('integrationsPage.releaseSmoke.a2aDiagnosticsPath')}: {a2aDiagnostics.path}</span>
                    )}
                  </dl>
                  <div className="inline-actions" style={{ marginTop: 'var(--space-3)' }}>
                    <Link className="btn btn-secondary btn-sm" to={RELEASE_A2A_PROTOCOL_PATH}>
                      {t('integrationsPage.releaseSmoke.workflowA2a')}
                    </Link>
                    <Link className="btn btn-secondary btn-sm" to={RELEASE_WORKFLOW_PATHS_BY_ID.cockpit}>
                      {t('integrationsPage.releaseSmoke.workflowReadiness')}
                    </Link>
                  </div>
                </div>
              )}
            </details>
          )}
          {showProviderSmokeHandoff && (
            <details
              className="integration-evidence-detail"
              aria-label={t('integrationsPage.releaseSmoke.providerEvidenceTitle')}
            >
              <summary className="integration-evidence-detail__summary">
                <div>
                  <strong>
                    {t('integrationsPage.releaseSmoke.providerEvidenceTitle')}
                  </strong>
                  <span>
                    {t('integrationsPage.releaseSmoke.providerEvidenceDescription')}
                  </span>
                </div>
                <ReleaseEvidenceStatus
                  status={resolveEvidenceDetailStatus(backendProviderIntegration?.status, providerSmokeReady)}
                  t={t}
                />
              </summary>
              <dl className="meta-grid" style={{ marginTop: 'var(--space-3)' }}>
                <span>{t('integrationsPage.releaseSmoke.detailGateStatus')}: {providerGate ? describeSmokeGateStatus(t, providerGate.status) : t('integrationsPage.releaseSmoke.missing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateReports')}: {providerRelatedReports.length > 0 ? providerRelatedReports.map((report, index) => (
                  <span key={`${report}-${index}`}>
                    {index > 0 && ', '}
                    <ReleaseReportLink report={report} includeStep />
                  </span>
                )) : t('integrationsPage.releaseSmoke.noneMissing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateMissingEnv')}: {providerMissingEnv.length > 0 ? providerMissingEnv.join(', ') : t('integrationsPage.releaseSmoke.noneMissing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateMode')}: {providerGateItem?.mode ?? t('integrationsPage.releaseSmoke.missing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateScope')}: {providerGateItem?.scope ?? t('integrationsPage.releaseSmoke.missing')}</span>
                <span>{t('integrationsPage.releaseSmoke.detailGateArtifact')}: {providerGateItem?.artifact ?? t('integrationsPage.releaseSmoke.missing')}</span>
                <span>{t('integrationsPage.releaseSmoke.providerName')}: {backendProviderIntegration?.provider ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.providerModel')}: {backendProviderIntegration?.model ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.providerUsageSource')}: {providerUsage?.source ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.providerUsagePresent')}: {providerUsage?.present ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.providerUsageTokens')}: {providerUsage?.inputTokens ?? '-'} / {providerUsage?.outputTokens ?? '-'} / {providerUsage?.totalTokens ?? '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.providerTokenBreakdown')}: {providerUsage?.totalMatchesBreakdown ? t('common.yes') : t('common.no')}</span>
                <span>{t('integrationsPage.releaseSmoke.providerRequiredChecks')}: {formatList(backendProviderIntegration?.requiredChecks) || '-'}</span>
                <span>{t('integrationsPage.releaseSmoke.providerContract')}: {missingProviderSmokeChecks.length === 0
                  ? t('integrationsPage.releaseSmoke.contractReady')
                  : t('integrationsPage.releaseSmoke.contractMissing', {
                    fields: missingProviderSmokeChecks.join(', '),
                  })}</span>
              </dl>
              {missingProviderUsageChecks.length > 0 && (
                <div
                  className="integration-evidence-detail__remediation"
                  role="region"
                  aria-label={t('integrationsPage.releaseSmoke.providerUsageRemediation')}
                >
                  <div className="detail-section-header">
                    <div>
                      <h5 className="section-title" style={{ marginBottom: 0 }}>
                        {t('integrationsPage.releaseSmoke.providerUsageRemediation')}
                      </h5>
                      <p className="detail-note" style={{ marginTop: 'var(--space-2)' }}>
                        {t('integrationsPage.releaseSmoke.providerUsageRemediationDesc')}
                      </p>
                    </div>
                    <ReleaseEvidenceStatus status="warning" t={t} />
                  </div>
                  <dl className="meta-grid" style={{ marginTop: 'var(--space-3)' }}>
                    {missingProviderUsageChecks.map((label) => (
                      <span key={label}>{label}</span>
                    ))}
                  </dl>
                  <div className="inline-actions" style={{ marginTop: 'var(--space-3)' }}>
                    <Link className="btn btn-secondary btn-sm" to={RELEASE_WORKFLOW_PATHS_BY_ID.provider}>
                      {t('integrationsPage.releaseSmoke.workflowProvider')}
                    </Link>
                    <Link className="btn btn-secondary btn-sm" to={RELEASE_WORKFLOW_PATHS_BY_ID.cockpit}>
                      {t('integrationsPage.releaseSmoke.workflowReadiness')}
                    </Link>
                  </div>
                </div>
              )}
            </details>
          )}
          {releaseReadinessCommand && (
            <details className="release-smoke-command">
              <summary>{t('integrationsPage.releaseSmoke.readinessCommandTitle')}</summary>
              <div className="release-smoke-command__body">
                <Link className="release-smoke-command__link" to={RELEASE_WORKFLOW_PATHS_BY_ID.cockpit}>
                  {t('integrationsPage.releaseSmoke.workflowReadiness')}
                </Link>
                <code>{releaseReadinessCommand}</code>
                <CopyButton
                  value={releaseReadinessCommand}
                  label={t('integrationsPage.releaseSmoke.copyReadinessCommand')}
                />
              </div>
            </details>
          )}
          </>
          )}
      </div>
      {error && (
        <div className="alert alert-error alert-with-retry" style={{ marginTop: 'var(--space-3)' }}>
          <span className="alert-message">{error}</span>
          <button className="btn btn-sm btn-secondary" onClick={onRefresh}>
            {t('common.retry')}
          </button>
        </div>
      )}
      {view === 'evidence' && (
      <div className="integrations-operations__evidence-list">
      {loading ? (
        <>
          <div className="stat-grid" style={{ marginTop: 'var(--space-3)', marginBottom: 'var(--space-4)' }}>
            <SkeletonCard height={80} />
            <SkeletonCard height={80} />
            <SkeletonCard height={80} />
            <SkeletonCard height={80} />
          </div>
          <SkeletonTable rows={5} columns={6} />
        </>
      ) : probes.length === 0 ? (
        <EmptyState message={t('integrationsPage.controlPlaneEmpty')} />
      ) : (
        <>
          {summary && (
            <dl className="control-plane-summary">
              <div><dt>{t('integrationsPage.controlPlaneTotal')}</dt><dd>{summary.total}</dd></div>
              <div><dt>{t('integrationsPage.controlPlanePass')}</dt><dd>{summary.passCount}</dd></div>
              <div><dt>{t('integrationsPage.controlPlaneWarn')}</dt><dd>{summary.warnCount}</dd></div>
              <div><dt>{t('integrationsPage.controlPlaneFail')}</dt><dd>{summary.failCount}</dd></div>
            </dl>
          )}
          <DataTable
            columns={columns}
            data={probes}
            keyFn={(row) => row.id}
          />
        </>
      )}
      </div>
      )}
    </section>
  )
}

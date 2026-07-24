import type { ApprovalAttentionItem, ApprovalOpsSummary, ApprovalSignal } from '../approvals/approvalOps'
import type { AuditOpsSignal } from '../audit/auditOps'
import type { ControlPlaneRecoveryItem } from '../integrations/controlPlaneRecovery'
import type { ControlPlaneProbeStatus } from '../integrations/controlPlaneProbes'
import type { ConfigReadinessSignal, RegistryKnownServerSnapshot, PolicySignal, McpSecuritySignal } from './mcpHelpers'
import type { McpPreflightResponse } from '../mcp-servers/types'
import type { OutputGuardSignal } from '../output-guard/outputGuardOps'
import type { SchedulerAttentionItem, SchedulerOpsSummary, SchedulerSignal } from '../scheduler/schedulerOps'
import type { ToolPolicySignal } from '../tool-policy/toolPolicyOps'
import type {
  IssueCenterSnapshot,
  IssueCenterSnapshotInput,
  IssueSeverity,
  IssueSource,
  OperatorIssue,
  McpIssueSnapshot,
} from './types'
import { humanizeToolName } from '../../shared/lib/humanizeToolName'
import { displayMcpServerName } from '../mcp-servers/mcpDisplay'

const SOURCE_ORDER: IssueSource[] = [
  'integrations',
  'mcpServers',
  'scheduler',
  'approvals',
  'mcpSecurity',
  'toolPolicy',
  'outputGuard',
  'audit',
]

function severityFromStatus(status: ControlPlaneProbeStatus): IssueSeverity {
  return status === 'FAIL' ? 'critical' : 'warning'
}

function toEpoch(value: number | string | null | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Date.parse(value)
    return Number.isNaN(parsed) ? null : parsed
  }
  return null
}

function sourceIndex(source: IssueSource): number {
  const index = SOURCE_ORDER.indexOf(source)
  return index === -1 ? SOURCE_ORDER.length : index
}

function sortIssues(items: OperatorIssue[]): OperatorIssue[] {
  return [...items].sort((left, right) => {
    if (left.severity !== right.severity) {
      return left.severity === 'critical' ? -1 : 1
    }

    if ((left.detectedAt ?? 0) !== (right.detectedAt ?? 0)) {
      return (right.detectedAt ?? 0) - (left.detectedAt ?? 0)
    }

    return sourceIndex(left.source) - sourceIndex(right.source)
  })
}

function buildControlPlaneIssue(item: ControlPlaneRecoveryItem): OperatorIssue {
  const detail = item.probe.httpStatus == null
    ? item.probe.detail
    : `HTTP ${item.probe.httpStatus} · ${item.probe.detail}`

  return {
    id: `control-plane:${item.probe.id}`,
    severity: severityFromStatus(item.status),
    source: 'integrations',
    title: { key: `integrationsPage.probes.${item.probe.id}` },
    summary: { key: `integrationsPage.recoveryKinds.${item.kind}` },
    detectedAt: null,
    routePath: item.route.path,
    routeLabelKey: item.route.labelKey,
    evidence: [
      item.probe.path,
      detail,
    ].filter(Boolean),
  }
}

function knownServerLabelKey(snapshot: RegistryKnownServerSnapshot): string {
  return snapshot.id === 'atlassian'
    ? 'mcpServers.knownServerAtlassian'
    : 'mcpServers.knownServerSwagger'
}

function firstNonPassConfigSignal(snapshot: McpIssueSnapshot): ConfigReadinessSignal | null {
  return snapshot.configReadiness?.signals.find((signal) => signal.status !== 'PASS') ?? null
}

function firstNonPassPolicySignal(snapshot: McpIssueSnapshot): PolicySignal | null {
  return snapshot.policyDiagnostics?.signals.find((signal) => signal.status !== 'PASS') ?? null
}

function buildMissingServerIssue(snapshot: RegistryKnownServerSnapshot): OperatorIssue {
  return {
    id: `mcp-missing:${snapshot.id}`,
    severity: 'critical',
    source: 'mcpServers',
    title: { key: knownServerLabelKey(snapshot) },
    summary: { key: 'mcpServers.knownServerMissing' },
    detectedAt: null,
    routePath: '/mcp-servers',
    routeLabelKey: 'nav.mcpServers',
    evidence: [],
  }
}

function buildDisconnectedServerIssue(snapshot: McpIssueSnapshot): OperatorIssue {
  return {
    id: `mcp-disconnected:${snapshot.server.name}`,
    severity: 'critical',
    source: 'mcpServers',
    title: { key: 'issuesPage.titles.serverDisconnected', values: { name: displayMcpServerName(snapshot.server.name) } },
    summary: { key: 'mcpServers.knownServerDisconnected' },
    detectedAt: null,
    routePath: '/mcp-servers',
    routeLabelKey: 'nav.mcpServers',
    evidence: [
      snapshot.server.status,
      snapshot.server.transportType,
    ],
  }
}

function buildConfigIssue(snapshot: McpIssueSnapshot): OperatorIssue | null {
  if (!snapshot.configReadiness || snapshot.configReadiness.status === 'PASS') return null

  const leadSignal = firstNonPassConfigSignal(snapshot)
  return {
    id: `mcp-config:${snapshot.server.name}`,
    severity: snapshot.configReadiness.status === 'FAIL' ? 'critical' : 'warning',
    source: 'mcpServers',
    title: { key: 'issuesPage.titles.configReadiness', values: { name: displayMcpServerName(snapshot.server.name) } },
    summary: leadSignal
      ? {
          key: `mcpServers.configReadinessDetails.${leadSignal.detailId}`,
          values: {
            timeoutMs: leadSignal.meta?.timeoutMs ?? '-',
            connectTimeoutMs: leadSignal.meta?.connectTimeoutMs ?? '-',
          },
        }
      : { key: 'mcpServers.configReadinessDescription' },
    detectedAt: null,
    routePath: '/mcp-servers',
    routeLabelKey: 'nav.mcpServers',
    evidence: snapshot.configReadiness.signals
      .filter((signal) => signal.status !== 'PASS')
      .map((signal) => signal.id),
  }
}

function buildDetailErrorIssue(snapshot: McpIssueSnapshot): OperatorIssue | null {
  if (!snapshot.detailError) return null

  return {
    id: `mcp-detail:${snapshot.server.name}`,
    severity: 'critical',
    source: 'mcpServers',
    title: { key: 'issuesPage.titles.serverDetail', values: { name: displayMcpServerName(snapshot.server.name) } },
    summary: { key: 'issuesPage.messages.detailUnavailable' },
    detectedAt: null,
    routePath: '/mcp-servers',
    routeLabelKey: 'nav.mcpServers',
    evidence: [snapshot.detailError],
  }
}

function preflightSummary(preflight: McpPreflightResponse): string[] {
  return [
    `PASS ${preflight.summary.passCount}`,
    `WARN ${preflight.summary.warnCount}`,
    `FAIL ${preflight.summary.failCount}`,
  ]
}

function buildPreflightIssue(snapshot: McpIssueSnapshot): OperatorIssue | null {
  if (snapshot.preflightError) {
    return {
      id: `mcp-preflight-error:${snapshot.server.name}`,
      severity: 'critical',
      source: 'mcpServers',
      title: { key: 'issuesPage.titles.preflight', values: { name: displayMcpServerName(snapshot.server.name) } },
      summary: { key: 'issuesPage.messages.preflightUnavailable' },
      detectedAt: null,
      routePath: '/mcp-servers',
      routeLabelKey: 'nav.mcpServers',
      evidence: [snapshot.preflightError],
    }
  }

  if (!snapshot.preflight || snapshot.preflight.readyForProduction) return null

  return {
    id: `mcp-preflight:${snapshot.server.name}`,
    severity: snapshot.preflight.ok ? 'warning' : 'critical',
    source: 'mcpServers',
    title: { key: 'issuesPage.titles.preflight', values: { name: displayMcpServerName(snapshot.server.name) } },
    summary: { key: snapshot.preflight.ok ? 'mcpServers.preflightNeedsAttention' : 'mcpServers.preflightFailed' },
    detectedAt: toEpoch(snapshot.preflight.checkedAt),
    routePath: '/mcp-servers',
    routeLabelKey: 'nav.mcpServers',
    evidence: preflightSummary(snapshot.preflight),
  }
}

function policySignalValues(signal: PolicySignal): Record<string, string | number> {
  return {
    count: signal.meta?.count ?? 0,
    openCount: signal.meta?.openCount ?? 0,
    totalCount: signal.meta?.totalCount ?? 0,
  }
}

function buildPolicyIssue(snapshot: McpIssueSnapshot): OperatorIssue | null {
  if (snapshot.policyError) {
    return {
      id: `mcp-policy-error:${snapshot.server.name}`,
      severity: 'critical',
      source: 'mcpServers',
      title: { key: 'issuesPage.titles.accessPolicy', values: { name: displayMcpServerName(snapshot.server.name) } },
      summary: { key: 'issuesPage.messages.policyUnavailable' },
      detectedAt: null,
      routePath: '/mcp-servers',
      routeLabelKey: 'nav.mcpServers',
      evidence: [snapshot.policyError],
    }
  }

  if (!snapshot.policyDiagnostics || snapshot.policyDiagnostics.status === 'PASS') return null

  const leadSignal = firstNonPassPolicySignal(snapshot)
  return {
    id: `mcp-policy:${snapshot.server.name}`,
    severity: snapshot.policyDiagnostics.status === 'FAIL' ? 'critical' : 'warning',
    source: 'mcpServers',
    title: { key: 'issuesPage.titles.accessPolicy', values: { name: displayMcpServerName(snapshot.server.name) } },
    summary: leadSignal
      ? {
          key: `mcpServers.policySignalDetails.${leadSignal.detailId}`,
          values: policySignalValues(leadSignal),
        }
      : { key: 'mcpServers.accessPolicyDescription' },
    detectedAt: null,
    routePath: '/mcp-servers',
    routeLabelKey: 'nav.mcpServers',
    evidence: [
      `attention:${snapshot.policyDiagnostics.attentionCount}`,
      `drift:${snapshot.policyDiagnostics.diffFields.length}`,
    ],
  }
}

function buildSchedulerSignalIssue(signal: SchedulerSignal): OperatorIssue {
  return {
    id: `scheduler-signal:${signal.id}`,
    severity: signal.status === 'FAIL' ? 'critical' : 'warning',
    source: 'scheduler',
    title: { key: `scheduler.signals.${signal.id}` },
    summary: {
      key: `scheduler.signalDetails.${signal.detailId}`,
      values: {
        count: signal.meta?.count ?? 0,
        total: signal.meta?.total ?? 0,
      },
    },
    detectedAt: null,
    routePath: '/scheduler',
    routeLabelKey: 'nav.scheduler',
    evidence: [],
  }
}

function buildSchedulerAttentionIssue(item: SchedulerAttentionItem): OperatorIssue {
  return {
    id: `scheduler-attention:${item.id}`,
    severity: item.status === 'FAIL' ? 'critical' : 'warning',
    source: 'scheduler',
    title: { key: 'issuesPage.titles.schedulerJob', values: { name: item.job.name } },
    summary: { key: `scheduler.attentionDetails.${item.detailId}` },
    detectedAt: item.job.lastRunAt,
    routePath: '/scheduler',
    routeLabelKey: 'nav.scheduler',
    evidence: [
      item.job.lastStatus ?? 'UNKNOWN',
      item.job.cronExpression,
    ],
  }
}

function buildApprovalSignalIssue(signal: ApprovalSignal): OperatorIssue {
  return {
    id: `approvals-signal:${signal.id}`,
    severity: signal.status === 'FAIL' ? 'critical' : 'warning',
    source: 'approvals',
    title: { key: `approvals.signals.${signal.id}` },
    summary: {
      key: `approvals.signalDetails.${signal.detailId}`,
      values: {
        count: signal.meta?.count ?? 0,
        total: signal.meta?.total ?? 0,
      },
    },
    detectedAt: null,
    routePath: '/approvals',
    routeLabelKey: 'nav.approvals',
    evidence: [],
  }
}

function buildApprovalAttentionIssue(item: ApprovalAttentionItem): OperatorIssue {
  return {
    id: `approvals-attention:${item.id}`,
    severity: item.status === 'FAIL' ? 'critical' : 'warning',
    source: 'approvals',
    title: { key: 'issuesPage.titles.approvalRequest', values: { tool: humanizeToolName(item.approval.toolName) } },
    summary: {
      key: `approvals.attentionDetails.${item.detailId}`,
      values: { ageMinutes: item.ageMinutes },
    },
    detectedAt: toEpoch(item.approval.requestedAt),
    routePath: '/approvals',
    routeLabelKey: 'nav.approvals',
    evidence: [
      item.approval.runId,
      item.approval.status,
    ],
  }
}

function buildToolPolicyIssue(signal: ToolPolicySignal): OperatorIssue {
  return {
    id: `tool-policy:${signal.id}`,
    severity: signal.status === 'FAIL' ? 'critical' : 'warning',
    source: 'toolPolicy',
    title: { key: `toolPolicyPage.signals.${signal.id}` },
    summary: {
      key: `toolPolicyPage.signalDetails.${signal.detailId}`,
      values: { count: signal.meta?.count ?? 0 },
    },
    detectedAt: null,
    routePath: '/safety-rules?tab=tool-policy',
    routeLabelKey: 'nav.safetyRules',
    evidence: [],
  }
}

function buildMcpSecurityIssue(signal: McpSecuritySignal): OperatorIssue {
  return {
    id: `mcp-security:${signal.id}`,
    severity: signal.status === 'FAIL' ? 'critical' : 'warning',
    source: 'mcpSecurity',
    title: { key: `mcpSecurityPage.signals.${signal.id}` },
    summary: {
      key: `mcpSecurityPage.signalDetails.${signal.detailId}`,
      values: { count: signal.meta?.count ?? 0 },
    },
    detectedAt: null,
    routePath: '/mcp-servers',
    routeLabelKey: 'nav.mcpServers',
    evidence: [],
  }
}

function buildOutputGuardIssue(signal: OutputGuardSignal): OperatorIssue {
  return {
    id: `output-guard:${signal.id}`,
    severity: signal.status === 'FAIL' ? 'critical' : 'warning',
    source: 'outputGuard',
    title: { key: `outputGuardPage.signals.${signal.id}` },
    summary: {
      key: `outputGuardPage.signalDetails.${signal.detailId}`,
      values: {
        count: signal.meta?.count ?? 0,
        names: signal.meta?.names?.join(', ') ?? '-',
      },
    },
    detectedAt: null,
    routePath: '/safety-rules?tab=output-guard',
    routeLabelKey: 'nav.safetyRules',
    evidence: [],
  }
}

function buildAuditIssue(signal: AuditOpsSignal): OperatorIssue {
  return {
    id: `audit:${signal.id}`,
    severity: signal.status === 'FAIL' ? 'critical' : 'warning',
    source: 'audit',
    title: { key: `auditPage.signals.${signal.id}` },
    summary: {
      key: `auditPage.signalDetails.${signal.detailId}`,
      values: {
        count: signal.meta?.count ?? 0,
        total: signal.meta?.total ?? 0,
      },
    },
    detectedAt: null,
    routePath: '/audit',
    routeLabelKey: 'nav.audit',
    evidence: [],
  }
}

function buildMcpIssues(
  input: IssueCenterSnapshotInput,
): OperatorIssue[] {
  const issues: OperatorIssue[] = []
  const registry = input.registryOverview

  for (const snapshot of registry.knownServers) {
    if (!snapshot.server) {
      issues.push(buildMissingServerIssue(snapshot))
      continue
    }
  }

  for (const snapshot of input.mcpServers) {
    if (snapshot.server.status !== 'CONNECTED') {
      issues.push(buildDisconnectedServerIssue(snapshot))
    }

    const detailIssue = buildDetailErrorIssue(snapshot)
    if (detailIssue) issues.push(detailIssue)

    const configIssue = buildConfigIssue(snapshot)
    if (configIssue) issues.push(configIssue)

    const preflightIssue = buildPreflightIssue(snapshot)
    if (preflightIssue) issues.push(preflightIssue)

    const policyIssue = buildPolicyIssue(snapshot)
    if (policyIssue) issues.push(policyIssue)
  }

  return issues
}

function buildSchedulerIssues(summary: SchedulerOpsSummary, degradedRoutes: Set<string>): OperatorIssue[] {
  const issues = summary.attentionItems.map(buildSchedulerAttentionIssue)
  if (!degradedRoutes.has('/scheduler')) {
    issues.unshift(
      ...summary.signals
        .filter((signal) => signal.status !== 'PASS')
        .map(buildSchedulerSignalIssue),
    )
  }
  return issues
}

function buildApprovalIssues(summary: ApprovalOpsSummary, degradedRoutes: Set<string>): OperatorIssue[] {
  const issues = summary.attentionItems.map(buildApprovalAttentionIssue)
  if (!degradedRoutes.has('/approvals')) {
    issues.unshift(
      ...summary.signals
        .filter((signal) => signal.status !== 'PASS')
        .map(buildApprovalSignalIssue),
    )
  }
  return issues
}

function buildSignalIssues<T extends { status: 'PASS' | 'WARN' | 'FAIL' }>(
  signals: T[],
  mapper: (signal: T) => OperatorIssue,
): OperatorIssue[] {
  return signals.filter((signal) => signal.status !== 'PASS').map(mapper)
}

export function buildIssueCenterSnapshot(input: IssueCenterSnapshotInput): IssueCenterSnapshot {
  const degradedRoutes = new Set(
    input.controlPlaneRecovery.items.map((item) => item.route.path.split(/[?#]/, 1)[0]),
  )

  const issues = sortIssues([
    ...input.controlPlaneRecovery.items.map(buildControlPlaneIssue),
    ...buildMcpIssues(input),
    ...buildSchedulerIssues(input.scheduler, degradedRoutes),
    ...buildApprovalIssues(input.approvals, degradedRoutes),
    ...buildSignalIssues(
      degradedRoutes.has('/safety-rules') ? [] : input.toolPolicy.signals,
      buildToolPolicyIssue,
    ),
    ...buildSignalIssues(
      degradedRoutes.has('/mcp-servers') ? [] : input.mcpSecurity.signals,
      buildMcpSecurityIssue,
    ),
    ...buildSignalIssues(input.outputGuard.signals, buildOutputGuardIssue),
    ...buildSignalIssues(
      degradedRoutes.has('/audit') ? [] : input.audit.signals,
      buildAuditIssue,
    ),
  ])

  const sources = SOURCE_ORDER.map((source) => {
    const sourceIssues = issues.filter((issue) => issue.source === source)
    return {
      source,
      total: sourceIssues.length,
      criticalCount: sourceIssues.filter((issue) => issue.severity === 'critical').length,
      warningCount: sourceIssues.filter((issue) => issue.severity === 'warning').length,
    }
  }).filter((source) => source.total > 0)

  return {
    generatedAt: input.generatedAt ?? Date.now(),
    total: issues.length,
    criticalCount: issues.filter((issue) => issue.severity === 'critical').length,
    warningCount: issues.filter((issue) => issue.severity === 'warning').length,
    sources,
    items: issues,
  }
}

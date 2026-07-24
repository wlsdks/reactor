import type { ConfigReadinessSummary, RegistryOverviewSummary, PolicyDiagnosticsSummary, McpSecurityOpsSummary } from './mcpHelpers'
import type { KnownMcpServerKind } from '../mcp-servers/presets'
import type { McpPreflightResponse, McpServerDetailResponse } from '../mcp-servers/types'
import type { ControlPlaneRecoverySummary } from '../integrations/controlPlaneRecovery'
import type { SchedulerOpsSummary } from '../scheduler/schedulerOps'
import type { ApprovalOpsSummary } from '../approvals/approvalOps'
import type { ToolPolicyOpsSummary } from '../tool-policy/toolPolicyOps'
import type { OutputGuardOpsSummary } from '../output-guard/outputGuardOps'
import type { AuditOpsSummary } from '../audit/auditOps'

export type IssueSeverity = 'critical' | 'warning'

export type IssueSource =
  | 'integrations'
  | 'mcpServers'
  | 'scheduler'
  | 'approvals'
  | 'toolPolicy'
  | 'mcpSecurity'
  | 'outputGuard'
  | 'audit'

export interface IssueMessageDescriptor {
  key: string
  values?: Record<string, string | number>
}

export interface OperatorIssue {
  id: string
  severity: IssueSeverity
  source: IssueSource
  title: IssueMessageDescriptor
  summary: IssueMessageDescriptor
  detectedAt: number | null
  routePath: string
  routeLabelKey: string
  evidence: string[]
}

export interface IssueSourceSummary {
  source: IssueSource
  total: number
  criticalCount: number
  warningCount: number
}

export interface IssueCenterSnapshot {
  generatedAt: number
  total: number
  criticalCount: number
  warningCount: number
  sources: IssueSourceSummary[]
  items: OperatorIssue[]
}

export interface McpIssueSnapshot {
  kind: Extract<KnownMcpServerKind, 'atlassian' | 'swagger'>
  server: McpServerDetailResponse
  detailError: string | null
  configReadiness: ConfigReadinessSummary | null
  preflight: McpPreflightResponse | null
  preflightError: string | null
  policyDiagnostics: PolicyDiagnosticsSummary | null
  policyError: string | null
}

export interface IssueCenterSnapshotInput {
  generatedAt?: number
  controlPlaneRecovery: ControlPlaneRecoverySummary
  registryOverview: RegistryOverviewSummary
  mcpServers: McpIssueSnapshot[]
  scheduler: SchedulerOpsSummary
  approvals: ApprovalOpsSummary
  toolPolicy: ToolPolicyOpsSummary
  mcpSecurity: McpSecurityOpsSummary
  outputGuard: OutputGuardOpsSummary
  audit: AuditOpsSummary
}

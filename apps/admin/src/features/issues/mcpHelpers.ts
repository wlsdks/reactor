/**
 * MCP helper logic copied from mcp-servers and mcp-security features
 * to decouple the Issues feature before those modules are deleted.
 *
 * Sources:
 * - mcp-servers/operatorReadiness.ts
 * - mcp-servers/policyDiagnostics.ts
 * - mcp-security/mcpSecurityOps.ts
 */

import { detectMcpServerKind, type KnownMcpServerKind } from '../mcp-servers/presets'
import type { McpAccessPolicy, McpAccessPolicySnapshot, McpServerDetailResponse, McpServerResponse, OperatorStatus } from '../mcp-servers/types'
import type { McpSecurityPolicyState } from '../mcp-security/types'

// ─── Operator Readiness (from operatorReadiness.ts) ──────────────────────────

export type { OperatorStatus }

export type ConfigReadinessSignalId =
  | 'transportTarget'
  | 'adminUrl'
  | 'adminToken'
  | 'adminHmac'
  | 'timeouts'
  | 'autoConnect'

export type ConfigReadinessDetailId =
  | 'transportUrlReady'
  | 'transportCommandReady'
  | 'transportMissingUrl'
  | 'transportMissingCommand'
  | 'adminUrlReady'
  | 'adminUrlDerived'
  | 'adminUrlMissing'
  | 'adminUrlOptional'
  | 'adminTokenReady'
  | 'adminTokenMissing'
  | 'adminTokenPlaceholder'
  | 'adminTokenOptional'
  | 'adminHmacReady'
  | 'adminHmacMissing'
  | 'adminHmacPlaceholder'
  | 'adminHmacDisabled'
  | 'timeoutsReady'
  | 'timeoutsDefault'
  | 'timeoutsNeedReview'
  | 'autoConnectEnabled'
  | 'autoConnectDisabled'

export interface ConfigReadinessSignal {
  id: ConfigReadinessSignalId
  status: OperatorStatus
  detailId: ConfigReadinessDetailId
  meta?: {
    transportType?: string
    timeoutMs?: number
    connectTimeoutMs?: number
  }
}

export interface ConfigReadinessSummary {
  status: OperatorStatus
  passCount: number
  warnCount: number
  failCount: number
  signals: ConfigReadinessSignal[]
}

export interface RegistryKnownServerSnapshot {
  id: 'atlassian' | 'swagger'
  server: McpServerResponse | null
}

export interface RegistryOverviewSummary {
  totalServers: number
  connectedCount: number
  disconnectedCount: number
  knownServers: RegistryKnownServerSnapshot[]
}

interface ConfigReadinessInput {
  transportType: string
  config: Record<string, unknown>
  autoConnect: boolean
  kind: KnownMcpServerKind
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value)
}

function isPlaceholderValue(value: string): boolean {
  const normalized = value.trim().toLowerCase()
  return normalized === '' ||
    normalized.includes('<set-') ||
    normalized.includes('change-me') ||
    normalized.includes('<token') ||
    normalized.includes('<secret')
}

function summarizeReadinessStatus(signals: ConfigReadinessSignal[]): Pick<ConfigReadinessSummary, 'status' | 'passCount' | 'warnCount' | 'failCount'> {
  const passCount = signals.filter((signal) => signal.status === 'PASS').length
  const warnCount = signals.filter((signal) => signal.status === 'WARN').length
  const failCount = signals.filter((signal) => signal.status === 'FAIL').length

  return {
    status: failCount > 0 ? 'FAIL' : warnCount > 0 ? 'WARN' : 'PASS',
    passCount,
    warnCount,
    failCount,
  }
}

function summarizeTransportSignal(input: ConfigReadinessInput): ConfigReadinessSignal {
  const targetUrl = asString(input.config.url)
  const command = asString(input.config.command)

  if (input.transportType === 'STDIO') {
    return command
      ? { id: 'transportTarget', status: 'PASS', detailId: 'transportCommandReady', meta: { transportType: input.transportType } }
      : { id: 'transportTarget', status: 'FAIL', detailId: 'transportMissingCommand', meta: { transportType: input.transportType } }
  }

  return isHttpUrl(targetUrl)
    ? { id: 'transportTarget', status: 'PASS', detailId: 'transportUrlReady', meta: { transportType: input.transportType } }
    : { id: 'transportTarget', status: 'FAIL', detailId: 'transportMissingUrl', meta: { transportType: input.transportType } }
}

function summarizeAdminUrlSignal(input: ConfigReadinessInput): ConfigReadinessSignal {
  const targetUrl = asString(input.config.url)
  const adminUrl = asString(input.config.adminUrl)
  const canDeriveAdminUrl = input.transportType === 'SSE' && isHttpUrl(targetUrl)
  const requiresAdminUrl = input.kind === 'atlassian' || input.kind === 'swagger'

  if (isHttpUrl(adminUrl)) {
    return { id: 'adminUrl', status: 'PASS', detailId: 'adminUrlReady' }
  }

  if (requiresAdminUrl && canDeriveAdminUrl) {
    return { id: 'adminUrl', status: 'WARN', detailId: 'adminUrlDerived' }
  }

  if (requiresAdminUrl) {
    return { id: 'adminUrl', status: 'FAIL', detailId: 'adminUrlMissing' }
  }

  return { id: 'adminUrl', status: 'WARN', detailId: 'adminUrlOptional' }
}

function summarizeAdminTokenSignal(input: ConfigReadinessInput): ConfigReadinessSignal {
  const adminToken = asString(input.config.adminToken)
  const adminUrl = asString(input.config.adminUrl)
  const requiresAdminToken = input.kind !== 'generic' || !!adminUrl

  if (!requiresAdminToken) {
    return { id: 'adminToken', status: 'WARN', detailId: 'adminTokenOptional' }
  }

  if (!adminToken) {
    return { id: 'adminToken', status: 'FAIL', detailId: 'adminTokenMissing' }
  }

  if (isPlaceholderValue(adminToken)) {
    return { id: 'adminToken', status: 'FAIL', detailId: 'adminTokenPlaceholder' }
  }

  return { id: 'adminToken', status: 'PASS', detailId: 'adminTokenReady' }
}

function summarizeAdminHmacSignal(input: ConfigReadinessInput): ConfigReadinessSignal {
  const hmacRequired = input.config.adminHmacRequired === true
  const hmacSecret = asString(input.config.adminHmacSecret)

  if (!hmacRequired) {
    return { id: 'adminHmac', status: 'WARN', detailId: 'adminHmacDisabled' }
  }

  if (!hmacSecret) {
    return { id: 'adminHmac', status: 'FAIL', detailId: 'adminHmacMissing' }
  }

  if (isPlaceholderValue(hmacSecret)) {
    return { id: 'adminHmac', status: 'FAIL', detailId: 'adminHmacPlaceholder' }
  }

  return { id: 'adminHmac', status: 'PASS', detailId: 'adminHmacReady' }
}

function summarizeTimeoutSignal(input: ConfigReadinessInput): ConfigReadinessSignal {
  const timeoutMs = asNumber(input.config.adminTimeoutMs)
  const connectTimeoutMs = asNumber(input.config.adminConnectTimeoutMs)

  if (timeoutMs == null && connectTimeoutMs == null) {
    return { id: 'timeouts', status: 'WARN', detailId: 'timeoutsDefault' }
  }

  const requestOutOfRange = timeoutMs != null && (timeoutMs < 100 || timeoutMs > 30_000)
  const connectOutOfRange = connectTimeoutMs != null && (connectTimeoutMs < 100 || connectTimeoutMs > 10_000)
  const connectExceedsRequest = timeoutMs != null && connectTimeoutMs != null && connectTimeoutMs > timeoutMs

  if (requestOutOfRange || connectOutOfRange || connectExceedsRequest) {
    return {
      id: 'timeouts',
      status: 'WARN',
      detailId: 'timeoutsNeedReview',
      meta: {
        timeoutMs: timeoutMs ?? undefined,
        connectTimeoutMs: connectTimeoutMs ?? undefined,
      },
    }
  }

  return {
    id: 'timeouts',
    status: 'PASS',
    detailId: 'timeoutsReady',
    meta: {
      timeoutMs: timeoutMs ?? undefined,
      connectTimeoutMs: connectTimeoutMs ?? undefined,
    },
  }
}

function summarizeAutoConnectSignal(autoConnect: boolean): ConfigReadinessSignal {
  return autoConnect
    ? { id: 'autoConnect', status: 'PASS', detailId: 'autoConnectEnabled' }
    : { id: 'autoConnect', status: 'WARN', detailId: 'autoConnectDisabled' }
}

export function summarizeConfigReadiness(input: ConfigReadinessInput): ConfigReadinessSummary {
  const signals: ConfigReadinessSignal[] = [
    summarizeTransportSignal(input),
    summarizeAdminUrlSignal(input),
    summarizeAdminTokenSignal(input),
    summarizeAdminHmacSignal(input),
    summarizeTimeoutSignal(input),
    summarizeAutoConnectSignal(input.autoConnect),
  ]

  return {
    ...summarizeReadinessStatus(signals),
    signals,
  }
}

export function summarizeServerConfigReadiness(detail: McpServerDetailResponse): ConfigReadinessSummary {
  return summarizeConfigReadiness({
    transportType: detail.transportType,
    config: detail.config,
    autoConnect: detail.autoConnect,
    kind: detectMcpServerKind(detail),
  })
}

export function summarizeDraftConfigReadiness(
  transportType: string,
  config: Record<string, unknown>,
  autoConnect: boolean,
  kind: KnownMcpServerKind,
): ConfigReadinessSummary {
  return summarizeConfigReadiness({
    transportType,
    config,
    autoConnect,
    kind,
  })
}

export function summarizeRegistryOverview(servers: McpServerResponse[]): RegistryOverviewSummary {
  const connectedCount = servers.filter((server) => server.status === 'CONNECTED').length
  return {
    totalServers: servers.length,
    connectedCount,
    disconnectedCount: Math.max(servers.length - connectedCount, 0),
    knownServers: [
      {
        id: 'atlassian',
        server: servers.find((server) => detectMcpServerKind({ name: server.name }) === 'atlassian') ?? null,
      },
      {
        id: 'swagger',
        server: servers.find((server) => detectMcpServerKind({ name: server.name }) === 'swagger') ?? null,
      },
    ],
  }
}

// ─── Policy Diagnostics (from policyDiagnostics.ts) ──────────────────────────

export type PolicyDiagnosticsStatus = 'PASS' | 'WARN' | 'FAIL'

export type PolicySignalId =
  | 'policyMode'
  | 'resourceCoverage'
  | 'previewReads'
  | 'previewWrites'
  | 'directUrlLoads'
  | 'publishedScope'
  | 'dynamicDrift'

export type PolicySignalDetailId =
  | 'dynamicModeEnabled'
  | 'dynamicModeDisabled'
  | 'dynamicModeUnknown'
  | 'coverageScoped'
  | 'coveragePartiallyScoped'
  | 'coverageOpenAll'
  | 'previewReadsBlocked'
  | 'previewReadsAllowed'
  | 'previewWritesBlocked'
  | 'previewWritesAllowed'
  | 'directUrlLoadsBlocked'
  | 'directUrlLoadsAllowed'
  | 'publishedOnlyEnforced'
  | 'publishedScopeOpen'
  | 'dynamicPolicyInSync'
  | 'dynamicPolicyDrifted'
  | 'dynamicSnapshotMissing'
  | 'dynamicSnapshotNotUsed'

export type PolicyDiffFieldId =
  | 'allowedJiraProjectKeys'
  | 'allowedConfluenceSpaceKeys'
  | 'allowedBitbucketRepositories'
  | 'allowedSourceNames'
  | 'allowPreviewReads'
  | 'allowPreviewWrites'
  | 'allowDirectUrlLoads'
  | 'publishedOnly'

export type PolicyRunbookStepId =
  | 'tightenCoverage'
  | 'lockPreviewSurface'
  | 'reconcileDynamicPolicy'
  | 'steadyState'

export interface PolicySignal {
  id: PolicySignalId
  status: PolicyDiagnosticsStatus
  detailId: PolicySignalDetailId
  meta?: {
    count?: number
    openCount?: number
    totalCount?: number
  }
}

export interface PolicyDiffField {
  id: PolicyDiffFieldId
  effective: string[] | boolean
  dynamic: string[] | boolean
}

export interface PolicyDiagnosticsSummary {
  status: PolicyDiagnosticsStatus
  effectiveCoverageCount: number
  dynamicCoverageCount: number | null
  attentionCount: number
  riskySurfaceCount: number
  diffFields: PolicyDiffField[]
  signals: PolicySignal[]
  runbookSteps: PolicyRunbookStepId[]
}

const ATLASSIAN_COVERAGE_FIELDS: Array<
  'allowedJiraProjectKeys' | 'allowedConfluenceSpaceKeys' | 'allowedBitbucketRepositories'
> = [
  'allowedJiraProjectKeys',
  'allowedConfluenceSpaceKeys',
  'allowedBitbucketRepositories',
]

const SWAGGER_COVERAGE_FIELDS: Array<'allowedSourceNames'> = ['allowedSourceNames']

const ATLASSIAN_DIFF_FIELDS: PolicyDiffFieldId[] = [...ATLASSIAN_COVERAGE_FIELDS]
const SWAGGER_DIFF_FIELDS: PolicyDiffFieldId[] = [
  'allowedSourceNames',
  'allowPreviewReads',
  'allowPreviewWrites',
  'allowDirectUrlLoads',
  'publishedOnly',
]

function normalizeList(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))].sort((left, right) => left.localeCompare(right))
}

function listValue(snapshot: McpAccessPolicySnapshot, field: typeof ATLASSIAN_COVERAGE_FIELDS[number] | typeof SWAGGER_COVERAGE_FIELDS[number]): string[] {
  return normalizeList(snapshot[field])
}

function listFieldsForKind(kind: KnownMcpServerKind): Array<typeof ATLASSIAN_COVERAGE_FIELDS[number] | typeof SWAGGER_COVERAGE_FIELDS[number]> {
  if (kind === 'swagger') return SWAGGER_COVERAGE_FIELDS
  return ATLASSIAN_COVERAGE_FIELDS
}

function diffFieldsForKind(kind: KnownMcpServerKind): PolicyDiffFieldId[] {
  if (kind === 'swagger') return SWAGGER_DIFF_FIELDS
  return ATLASSIAN_DIFF_FIELDS
}

function compareField(
  effective: McpAccessPolicySnapshot,
  dynamic: McpAccessPolicySnapshot,
  field: PolicyDiffFieldId,
): boolean {
  if (field === 'publishedOnly' || field === 'allowPreviewReads' || field === 'allowPreviewWrites' || field === 'allowDirectUrlLoads') {
    return effective[field] === dynamic[field]
  }

  return JSON.stringify(normalizeList(effective[field])) === JSON.stringify(normalizeList(dynamic[field]))
}

function policyCoverageCount(snapshot: McpAccessPolicySnapshot, kind: KnownMcpServerKind): number {
  return listFieldsForKind(kind).reduce((total, field) => total + listValue(snapshot, field).length, 0)
}

function summarizePolicyStatus(signals: PolicySignal[]): PolicyDiagnosticsStatus {
  if (signals.some((signal) => signal.status === 'FAIL')) return 'FAIL'
  if (signals.some((signal) => signal.status === 'WARN')) return 'WARN'
  return 'PASS'
}

export function summarizePolicyDiagnostics(
  kind: KnownMcpServerKind,
  policy: McpAccessPolicy,
): PolicyDiagnosticsSummary {
  const effective = policy
  const dynamic = policy.dynamicPolicy ?? null
  const coverageFields = listFieldsForKind(kind)
  const openCoverageCount = coverageFields.filter((field) => listValue(effective, field).length === 0).length
  const diffFields = dynamic == null
    ? []
    : diffFieldsForKind(kind)
        .filter((field) => !compareField(effective, dynamic, field))
        .map((field) => ({
          id: field,
          effective: field === 'publishedOnly' || field === 'allowPreviewReads' || field === 'allowPreviewWrites' || field === 'allowDirectUrlLoads'
            ? effective[field]
            : normalizeList(effective[field]),
          dynamic: field === 'publishedOnly' || field === 'allowPreviewReads' || field === 'allowPreviewWrites' || field === 'allowDirectUrlLoads'
            ? dynamic[field]
            : normalizeList(dynamic[field]),
        }))

  const signals: PolicySignal[] = [
    policy.dynamicEnabled === true
      ? {
          id: 'policyMode',
          status: 'PASS',
          detailId: 'dynamicModeEnabled',
        }
      : policy.policySource === 'unknown'
        ? {
            id: 'policyMode',
            status: 'WARN',
            detailId: 'dynamicModeUnknown',
          }
        : {
            id: 'policyMode',
            status: 'WARN',
            detailId: 'dynamicModeDisabled',
          },
    openCoverageCount === 0
      ? {
          id: 'resourceCoverage',
          status: 'PASS',
          detailId: 'coverageScoped',
          meta: { count: policyCoverageCount(effective, kind) },
        }
      : openCoverageCount === coverageFields.length
        ? {
            id: 'resourceCoverage',
            status: 'FAIL',
            detailId: 'coverageOpenAll',
            meta: { openCount: openCoverageCount, totalCount: coverageFields.length },
          }
        : {
            id: 'resourceCoverage',
            status: 'WARN',
            detailId: 'coveragePartiallyScoped',
            meta: { openCount: openCoverageCount, totalCount: coverageFields.length },
          },
  ]

  if (kind === 'swagger') {
    signals.push(
      effective.allowPreviewReads
        ? { id: 'previewReads', status: 'WARN', detailId: 'previewReadsAllowed' }
        : { id: 'previewReads', status: 'PASS', detailId: 'previewReadsBlocked' },
      effective.allowPreviewWrites
        ? { id: 'previewWrites', status: 'WARN', detailId: 'previewWritesAllowed' }
        : { id: 'previewWrites', status: 'PASS', detailId: 'previewWritesBlocked' },
      effective.allowDirectUrlLoads
        ? { id: 'directUrlLoads', status: 'WARN', detailId: 'directUrlLoadsAllowed' }
        : { id: 'directUrlLoads', status: 'PASS', detailId: 'directUrlLoadsBlocked' },
      effective.publishedOnly === false
        ? { id: 'publishedScope', status: 'WARN', detailId: 'publishedScopeOpen' }
        : { id: 'publishedScope', status: 'PASS', detailId: 'publishedOnlyEnforced' },
    )
  }

  signals.push(
    dynamic == null
      ? policy.dynamicEnabled
        ? {
            id: 'dynamicDrift',
            status: 'WARN',
            detailId: 'dynamicSnapshotMissing',
          }
        : {
            id: 'dynamicDrift',
            status: 'PASS',
            detailId: 'dynamicSnapshotNotUsed',
          }
      : diffFields.length === 0
        ? {
            id: 'dynamicDrift',
            status: 'PASS',
            detailId: 'dynamicPolicyInSync',
          }
        : {
            id: 'dynamicDrift',
            status: 'WARN',
            detailId: 'dynamicPolicyDrifted',
            meta: { count: diffFields.length },
          },
  )

  const runbookSteps = new Set<PolicyRunbookStepId>()
  const attentionCount = signals.filter((signal) => signal.status !== 'PASS').length
  const riskySurfaceCount = kind === 'swagger'
    ? [effective.allowPreviewReads, effective.allowPreviewWrites, effective.allowDirectUrlLoads, effective.publishedOnly === false]
        .filter(Boolean)
        .length
    : openCoverageCount

  if (openCoverageCount > 0) runbookSteps.add('tightenCoverage')
  if (kind === 'swagger' && riskySurfaceCount > 0) runbookSteps.add('lockPreviewSurface')
  if (signals.some((signal) => signal.id === 'policyMode' && signal.status !== 'PASS') || diffFields.length > 0 || (policy.dynamicEnabled && dynamic == null)) {
    runbookSteps.add('reconcileDynamicPolicy')
  }
  if (runbookSteps.size === 0) runbookSteps.add('steadyState')

  return {
    status: summarizePolicyStatus(signals),
    effectiveCoverageCount: policyCoverageCount(effective, kind),
    dynamicCoverageCount: dynamic ? policyCoverageCount(dynamic, kind) : null,
    attentionCount,
    riskySurfaceCount,
    diffFields,
    signals,
    runbookSteps: [...runbookSteps],
  }
}

// ─── MCP Security Ops (from mcpSecurityOps.ts) ──────────────────────────────

export type McpSecurityOpsStatus = 'PASS' | 'WARN' | 'FAIL'
export type McpSecurityLoadIssue =
  | 'notAdvertised'
  | 'accessDenied'
  | 'transportFailure'
  | 'httpError'

export interface McpSecuritySignal {
  id: 'policyContract' | 'allowlistCoverage' | 'registryAlignment' | 'outputClamp' | 'storedPolicy' | 'policyDrift'
  status: McpSecurityOpsStatus
  detailId:
    | 'contractHealthy'
    | 'contractMissing'
    | 'contractDenied'
    | 'contractTransport'
    | 'contractError'
    | 'allowlistPresent'
    | 'allowlistEmpty'
    | 'registryCovered'
    | 'registeredBlocked'
    | 'allowlistStale'
    | 'registryUnavailable'
    | 'registryEmpty'
    | 'outputClampReady'
    | 'outputClampHigh'
    | 'outputClampTight'
    | 'storedPolicyPresent'
    | 'configDefaultActive'
    | 'policyInSync'
    | 'storedOverrideApplied'
    | 'policyDriftDetected'
  meta?: {
    count?: number
  }
}

export interface McpSecurityDiffEntry {
  id: 'allowedServerNames' | 'maxToolOutputLength'
  effective: string
  stored: string
  configDefault: string
  storedChanged: boolean
  configChanged: boolean
}

export interface McpSecurityOpsSummary {
  status: McpSecurityOpsStatus
  loadIssue: McpSecurityLoadIssue | null
  hasPolicy: boolean
  effectiveAllowedCount: number
  registeredCount: number
  blockedRegisteredCount: number
  staleAllowedCount: number
  storedExists: boolean
  diffFields: McpSecurityDiffEntry['id'][]
  blockedRegisteredNames: string[]
  staleAllowedNames: string[]
  signals: McpSecuritySignal[]
  diffs: McpSecurityDiffEntry[]
}

function summarizeSecurityStatus(signals: McpSecuritySignal[]): McpSecurityOpsStatus {
  if (signals.some((signal) => signal.status === 'FAIL')) return 'FAIL'
  if (signals.some((signal) => signal.status === 'WARN')) return 'WARN'
  return 'PASS'
}

function stableStringify(value: unknown): string {
  if (value == null) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return JSON.stringify([...value].map((item) => String(item)).sort(), null, 2)
  return JSON.stringify(value, null, 2)
}

function sameStringified(left: unknown, right: unknown): boolean {
  return stableStringify(left) === stableStringify(right)
}

function buildDiffs(state: McpSecurityPolicyState): McpSecurityDiffEntry[] {
  const stored = state.stored
  return [
    {
      id: 'allowedServerNames',
      effective: stableStringify(state.effective.allowedServerNames),
      stored: stableStringify(stored?.allowedServerNames ?? null),
      configDefault: stableStringify(state.configDefault.allowedServerNames),
      storedChanged: !sameStringified(state.effective.allowedServerNames, stored?.allowedServerNames ?? null),
      configChanged: !sameStringified(state.effective.allowedServerNames, state.configDefault.allowedServerNames),
    },
    {
      id: 'maxToolOutputLength',
      effective: stableStringify(state.effective.maxToolOutputLength),
      stored: stableStringify(stored?.maxToolOutputLength ?? null),
      configDefault: stableStringify(state.configDefault.maxToolOutputLength),
      storedChanged: !sameStringified(state.effective.maxToolOutputLength, stored?.maxToolOutputLength ?? null),
      configChanged: !sameStringified(state.effective.maxToolOutputLength, state.configDefault.maxToolOutputLength),
    },
  ]
}

export function classifyMcpSecurityLoadIssue(message: string | null): McpSecurityLoadIssue | null {
  const value = message?.trim().toLowerCase()
  if (!value) return null
  if (value.includes('http 404')) return 'notAdvertised'
  if (value.includes('http 401') || value.includes('http 403')) return 'accessDenied'
  if (
    value.includes('socket hang up')
    || value.includes('failed to fetch')
    || value.includes('networkerror')
    || value.includes('empty reply')
  ) {
    return 'transportFailure'
  }
  return 'httpError'
}

function summarizeContractSignal(loadIssue: McpSecurityLoadIssue | null): McpSecuritySignal {
  if (loadIssue === 'notAdvertised') return { id: 'policyContract', status: 'WARN', detailId: 'contractMissing' }
  if (loadIssue === 'accessDenied') return { id: 'policyContract', status: 'FAIL', detailId: 'contractDenied' }
  if (loadIssue === 'transportFailure') return { id: 'policyContract', status: 'FAIL', detailId: 'contractTransport' }
  if (loadIssue === 'httpError') return { id: 'policyContract', status: 'FAIL', detailId: 'contractError' }
  return { id: 'policyContract', status: 'PASS', detailId: 'contractHealthy' }
}

export function summarizeMcpSecurityOps(
  state: McpSecurityPolicyState | null,
  loadError: string | null,
  registeredServerNames: string[],
  registryError: string | null,
): McpSecurityOpsSummary {
  const loadIssue = classifyMcpSecurityLoadIssue(loadError)
  const contractSignal = summarizeContractSignal(loadIssue)

  if (!state) {
    return {
      status: summarizeSecurityStatus([contractSignal]),
      loadIssue,
      hasPolicy: false,
      effectiveAllowedCount: 0,
      registeredCount: registeredServerNames.length,
      blockedRegisteredCount: 0,
      staleAllowedCount: 0,
      storedExists: false,
      diffFields: [],
      blockedRegisteredNames: [],
      staleAllowedNames: [],
      signals: [contractSignal],
      diffs: [],
    }
  }

  const allowed = new Set(state.effective.allowedServerNames)
  const blockedRegisteredNames = registeredServerNames.filter((name) => !allowed.has(name))
  const staleAllowedNames = state.effective.allowedServerNames.filter((name) => !registeredServerNames.includes(name))
  const diffs = buildDiffs(state)

  const signals: McpSecuritySignal[] = [
    contractSignal,
    state.effective.allowedServerNames.length > 0
      ? { id: 'allowlistCoverage', status: 'PASS', detailId: 'allowlistPresent' }
      : { id: 'allowlistCoverage', status: 'WARN', detailId: 'allowlistEmpty' },
    registryError
      ? { id: 'registryAlignment', status: 'WARN', detailId: 'registryUnavailable' }
      : registeredServerNames.length === 0
        ? { id: 'registryAlignment', status: 'WARN', detailId: 'registryEmpty' }
        : blockedRegisteredNames.length > 0
          ? {
              id: 'registryAlignment',
              status: 'FAIL',
              detailId: 'registeredBlocked',
              meta: { count: blockedRegisteredNames.length },
            }
          : staleAllowedNames.length > 0
            ? {
                id: 'registryAlignment',
                status: 'WARN',
                detailId: 'allowlistStale',
                meta: { count: staleAllowedNames.length },
              }
            : {
                id: 'registryAlignment',
                status: 'PASS',
                detailId: 'registryCovered',
                meta: { count: registeredServerNames.length },
              },
    state.effective.maxToolOutputLength > 200_000
      ? { id: 'outputClamp', status: 'WARN', detailId: 'outputClampHigh' }
      : state.effective.maxToolOutputLength < 4_096
        ? { id: 'outputClamp', status: 'WARN', detailId: 'outputClampTight' }
        : { id: 'outputClamp', status: 'PASS', detailId: 'outputClampReady' },
    state.stored
      ? { id: 'storedPolicy', status: 'WARN', detailId: 'storedPolicyPresent' }
      : { id: 'storedPolicy', status: 'PASS', detailId: 'configDefaultActive' },
    state.stored
      ? diffs.some((diff) => diff.storedChanged)
        ? { id: 'policyDrift', status: 'FAIL', detailId: 'policyDriftDetected' }
        : { id: 'policyDrift', status: 'WARN', detailId: 'storedOverrideApplied' }
      : diffs.some((diff) => diff.configChanged)
        ? { id: 'policyDrift', status: 'FAIL', detailId: 'policyDriftDetected' }
        : { id: 'policyDrift', status: 'PASS', detailId: 'policyInSync' },
  ]

  return {
    status: summarizeSecurityStatus(signals),
    loadIssue,
    hasPolicy: true,
    effectiveAllowedCount: state.effective.allowedServerNames.length,
    registeredCount: registeredServerNames.length,
    blockedRegisteredCount: blockedRegisteredNames.length,
    staleAllowedCount: staleAllowedNames.length,
    storedExists: state.stored != null,
    diffFields: diffs.filter((diff) => diff.storedChanged || diff.configChanged).map((diff) => diff.id),
    blockedRegisteredNames,
    staleAllowedNames,
    signals,
    diffs,
  }
}

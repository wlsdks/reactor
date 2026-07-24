import { summarizeStatus, type OpsStatus } from '../../shared/lib/ops'
import type { AuditLogEntry } from './types'

export interface ParsedAuditDetail {
  raw: string | null
  formatted: string
  isJson: boolean
  hasText: boolean
  hasBeforeAfter: boolean
  changeKeys: string[]
}

export interface AuditRecoveryRoute {
  path: string
  labelKey:
    | 'nav.audit'
    | 'nav.mcpServers'
    | 'nav.safetyRules'
    | 'nav.scheduler'
    | 'nav.prompts'
    | 'nav.personas'
    | 'nav.approvals'
}

export interface AuditEntryInsight {
  entry: AuditLogEntry
  action: string
  highRisk: boolean
  hasResource: boolean
  hasDetail: boolean
  rollbackReady: boolean
  detail: ParsedAuditDetail
  recoveryRoute: AuditRecoveryRoute
}

export interface AuditOpsSignal {
  id: 'auditChannel' | 'resourceCoverage' | 'detailCoverage' | 'rollbackReadiness'
  status: OpsStatus
  detailId:
    | 'auditChannelReady'
    | 'auditChannelEmpty'
    | 'auditChannelUnavailable'
    | 'resourceCoverageReady'
    | 'resourceCoverageMissing'
    | 'detailCoverageReady'
    | 'detailCoverageMissing'
    | 'rollbackReadinessReady'
    | 'rollbackReadinessMissing'
  meta?: {
    count?: number
    total?: number
  }
}

export interface AuditResourceSummary {
  key: string
  label: string
  count: number
  latestAt: number
  latestAction: string
  latestActor: string
  rollbackReadyCount: number
  recoveryRoute: AuditRecoveryRoute
}

export interface AuditCategorySummary {
  category: string
  count: number
}

export interface AuditOpsSummary {
  status: OpsStatus
  totalLogs: number
  uniqueActors: number
  uniqueResources: number
  detailedLogs: number
  rollbackReadyCount: number
  highRiskCount: number
  signals: AuditOpsSignal[]
  categories: AuditCategorySummary[]
  resourceBundles: AuditResourceSummary[]
}

const HIGH_RISK_ACTIONS = new Set([
  'UPDATE',
  'DELETE',
  'DISABLE',
  'DEACTIVATE',
  'DISCONNECT',
  'REJECT',
  'ARCHIVE',
  'PUBLISH',
  'RESTORE',
  'RESET',
  'APPLY',
])

const MUTATING_ACTIONS = new Set([
  ...HIGH_RISK_ACTIONS,
  'CREATE',
  'CONNECT',
  'ENABLE',
  'ACTIVATE',
  'APPROVE',
])

function normalizeAction(action: string): string {
  return action.trim().toUpperCase()
}

function toObject(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function extractChangeKeys(record: Record<string, unknown>): string[] {
  const changes = toObject(record.changes)
  if (changes) return Object.keys(changes)

  const after = toObject(record.after) ?? toObject(record.current) ?? toObject(record.new) ?? toObject(record.to)
  if (after) return Object.keys(after)

  return []
}

export function parseAuditDetail(detail: string | null): ParsedAuditDetail {
  const raw = detail?.trim() ?? null
  if (!raw) {
    return {
      raw: null,
      formatted: '',
      isJson: false,
      hasText: false,
      hasBeforeAfter: false,
      changeKeys: [],
    }
  }

  if (!raw.startsWith('{') && !raw.startsWith('[')) {
    return {
      raw,
      formatted: raw,
      isJson: false,
      hasText: true,
      hasBeforeAfter: false,
      changeKeys: [],
    }
  }

  try {
    const parsed = JSON.parse(raw) as unknown
    const record = toObject(parsed)
    const hasBeforeAfter = record != null && (
      ('before' in record && 'after' in record)
      || ('previous' in record && 'current' in record)
      || ('old' in record && 'new' in record)
      || ('from' in record && 'to' in record)
    )

    return {
      raw,
      formatted: JSON.stringify(parsed, null, 2),
      isJson: true,
      hasText: true,
      hasBeforeAfter,
      changeKeys: record ? extractChangeKeys(record) : [],
    }
  } catch {
    return {
      raw,
      formatted: raw,
      isJson: false,
      hasText: true,
      hasBeforeAfter: false,
      changeKeys: [],
    }
  }
}

export function resolveAuditRecoveryRoute(entry: AuditLogEntry): AuditRecoveryRoute {
  const scope = `${entry.category} ${entry.resourceType ?? ''} ${entry.resourceId ?? ''}`.toUpperCase()

  if (scope.includes('OUTPUT') || scope.includes('GUARD')) {
    return { path: '/safety-rules?tab=output-guard', labelKey: 'nav.safetyRules' }
  }
  if (scope.includes('MCP') || scope.includes('SERVER') || scope.includes('SWAGGER') || scope.includes('ATLASSIAN')) {
    return { path: '/mcp-servers', labelKey: 'nav.mcpServers' }
  }
  if (scope.includes('POLICY')) {
    return { path: '/safety-rules?tab=tool-policy', labelKey: 'nav.safetyRules' }
  }
  if (scope.includes('SCHEDULER') || scope.includes('JOB')) {
    return { path: '/scheduler', labelKey: 'nav.scheduler' }
  }
  if (scope.includes('PROMPT')) {
    return { path: '/prompts', labelKey: 'nav.prompts' }
  }
  if (scope.includes('PERSONA')) {
    return { path: '/personas', labelKey: 'nav.personas' }
  }
  if (scope.includes('APPROVAL')) {
    return { path: '/approvals', labelKey: 'nav.approvals' }
  }

  return { path: '/audit', labelKey: 'nav.audit' }
}

export function deriveAuditEntryInsight(entry: AuditLogEntry): AuditEntryInsight {
  const detail = parseAuditDetail(entry.detail)
  const action = normalizeAction(entry.action)
  const hasResource = Boolean(entry.resourceType ?? entry.resourceId)
  const highRisk = HIGH_RISK_ACTIONS.has(action)
  const rollbackReady = (MUTATING_ACTIONS.has(action) || highRisk)
    && (hasResource || detail.isJson || detail.hasBeforeAfter)

  return {
    entry,
    action,
    highRisk,
    hasResource,
    hasDetail: detail.hasText,
    rollbackReady,
    detail,
    recoveryRoute: resolveAuditRecoveryRoute(entry),
  }
}

export function summarizeAuditLogs(logs: AuditLogEntry[], auditError: string | null): AuditOpsSummary {
  const safeLogs = Array.isArray(logs) ? logs : []
  const insights = safeLogs.map(deriveAuditEntryInsight)
  const withResource = insights.filter((insight) => insight.hasResource)
  const withDetail = insights.filter((insight) => insight.hasDetail)
  const rollbackReady = insights.filter((insight) => insight.rollbackReady)
  const highRisk = insights.filter((insight) => insight.highRisk)

  const signals: AuditOpsSignal[] = [
    auditError
      ? { id: 'auditChannel', status: 'FAIL', detailId: 'auditChannelUnavailable' }
      : safeLogs.length > 0
        ? {
            id: 'auditChannel',
            status: 'PASS',
            detailId: 'auditChannelReady',
            meta: { count: safeLogs.length },
          }
        : { id: 'auditChannel', status: 'WARN', detailId: 'auditChannelEmpty' },
    safeLogs.length > 0 && withResource.length / safeLogs.length >= 0.75
      ? {
          id: 'resourceCoverage',
          status: 'PASS',
          detailId: 'resourceCoverageReady',
          meta: { count: withResource.length, total: safeLogs.length },
        }
      : {
          id: 'resourceCoverage',
          status: safeLogs.length === 0 ? 'WARN' : 'WARN',
          detailId: 'resourceCoverageMissing',
          meta: { count: withResource.length, total: safeLogs.length },
        },
    safeLogs.length > 0 && withDetail.length / safeLogs.length >= 0.6
      ? {
          id: 'detailCoverage',
          status: 'PASS',
          detailId: 'detailCoverageReady',
          meta: { count: withDetail.length, total: safeLogs.length },
        }
      : {
          id: 'detailCoverage',
          status: 'WARN',
          detailId: 'detailCoverageMissing',
          meta: { count: withDetail.length, total: safeLogs.length },
        },
    rollbackReady.length > 0
      ? {
          id: 'rollbackReadiness',
          status: 'PASS',
          detailId: 'rollbackReadinessReady',
          meta: { count: rollbackReady.length, total: safeLogs.length },
        }
      : {
          id: 'rollbackReadiness',
          status: safeLogs.length === 0 ? 'WARN' : 'WARN',
          detailId: 'rollbackReadinessMissing',
          meta: { count: rollbackReady.length, total: safeLogs.length },
        },
  ]

  const categoryCounts = new Map<string, number>()
  const resourceBundles = new Map<string, AuditResourceSummary>()
  const uniqueActors = new Set<string>()
  const uniqueResources = new Set<string>()

  for (const insight of insights) {
    uniqueActors.add(insight.entry.actor)
    categoryCounts.set(insight.entry.category, (categoryCounts.get(insight.entry.category) ?? 0) + 1)

    const resourceLabel = insight.hasResource
      ? `${insight.entry.resourceType ?? '-'}:${insight.entry.resourceId ?? '-'}`
      : `${insight.entry.category}:unscoped`

    if (insight.hasResource) uniqueResources.add(resourceLabel)

    const existing = resourceBundles.get(resourceLabel)
    if (!existing || insight.entry.createdAt > existing.latestAt) {
      resourceBundles.set(resourceLabel, {
        key: resourceLabel,
        label: resourceLabel,
        count: (existing?.count ?? 0) + 1,
        latestAt: insight.entry.createdAt,
        latestAction: insight.entry.action,
        latestActor: insight.entry.actor,
        rollbackReadyCount: (existing?.rollbackReadyCount ?? 0) + (insight.rollbackReady ? 1 : 0),
        recoveryRoute: insight.recoveryRoute,
      })
      continue
    }

    existing.count += 1
    if (insight.rollbackReady) existing.rollbackReadyCount += 1
  }

  return {
    status: summarizeStatus(signals),
    totalLogs: safeLogs.length,
    uniqueActors: uniqueActors.size,
    uniqueResources: uniqueResources.size,
    detailedLogs: withDetail.length,
    rollbackReadyCount: rollbackReady.length,
    highRiskCount: highRisk.length,
    signals,
    categories: Array.from(categoryCounts.entries())
      .map(([category, count]) => ({ category, count }))
      .sort((left, right) => right.count - left.count)
      .slice(0, 6),
    resourceBundles: Array.from(resourceBundles.values())
      .sort((left, right) => right.latestAt - left.latestAt)
      .slice(0, 8),
  }
}

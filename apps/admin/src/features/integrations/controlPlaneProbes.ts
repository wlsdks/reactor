import i18n from 'i18next'
import type { EndpointProbeResult } from './types'

export type ControlPlaneProbeStatus = 'PASS' | 'WARN' | 'FAIL'

export type ControlPlaneProbeId =
  | 'capabilities'
  | 'opsDashboard'
  | 'mcpRegistry'
  | 'approvals'
  | 'metricsNames'
  | 'auditLogs'
  | 'toolPolicy'
  | 'mcpSecurity'
  | 'slackCommands'
  | 'slackEvents'
  | 'a2aDiagnostics'
  | 'providerModels'
  | 'errorReport'
  | 'schedulerJobs'

export type ControlPlaneProbeReason =
  | 'ready'
  | 'reachableUndeclared'
  | 'declaredBroken'
  | 'notAdvertised'
  | 'probeFailed'

export interface ControlPlaneProbeSpec {
  id: ControlPlaneProbeId
  path: string
  method?: string
  routePath?: string
  reachableStatusCodes?: number[]
}

export interface ControlPlaneProbeSnapshot extends ControlPlaneProbeSpec {
  status: ControlPlaneProbeStatus
  reason: ControlPlaneProbeReason
  manifestDeclared: boolean | null
  httpStatus: number | null
  durationMs: number
  detail: string
}

export interface ControlPlaneProbeSummary {
  total: number
  passCount: number
  warnCount: number
  failCount: number
  declaredCount: number
}

export const CONTROL_PLANE_PROBE_SPECS: ControlPlaneProbeSpec[] = [
  { id: 'capabilities', path: '/api/admin/capabilities', routePath: '/integrations' },
  { id: 'opsDashboard', path: '/api/ops/dashboard', routePath: '/' },
  { id: 'mcpRegistry', path: '/api/mcp/servers', routePath: '/mcp-servers' },
  { id: 'approvals', path: '/api/approvals', method: 'OPTIONS', routePath: '/approvals', reachableStatusCodes: [200, 204, 405] },
  { id: 'metricsNames', path: '/api/ops/metrics/names', routePath: '/' },
  { id: 'auditLogs', path: '/api/admin/audits?limit=5', routePath: '/audit' },
  { id: 'toolPolicy', path: '/api/tool-policy', routePath: '/safety-rules?tab=tool-policy' },
  { id: 'mcpSecurity', path: '/api/mcp/security', routePath: '/mcp-servers' },
  // These endpoints are POST-only in production. Probing with OPTIONS avoids
  // the browser-level "Failed to load resource" 4xx noise that GET produces,
  // while still proving the route contract is present. If OPTIONS is not
  // supported the server may respond 405 — kept as a reachable fallback.
  { id: 'slackCommands', path: '/api/slack/commands', method: 'OPTIONS', routePath: '/integrations', reachableStatusCodes: [200, 204, 405] },
  { id: 'slackEvents', path: '/api/slack/events', method: 'OPTIONS', routePath: '/integrations', reachableStatusCodes: [200, 204, 405] },
  { id: 'a2aDiagnostics', path: '/api/v1/a2a/diagnostics', routePath: '/integrations' },
  { id: 'providerModels', path: '/api/admin/models', routePath: '/models' },
  { id: 'errorReport', path: '/api/error-report', method: 'OPTIONS', routePath: '/integrations', reachableStatusCodes: [200, 204, 405] },
  { id: 'schedulerJobs', path: '/api/scheduler/jobs', routePath: '/scheduler' },
]

function manifestPath(path: string): string {
  return path.split('?')[0]
}

function isReachableStatus(spec: ControlPlaneProbeSpec, status: number): boolean {
  return (status >= 200 && status < 300) || (spec.reachableStatusCodes?.includes(status) ?? false)
}

function toDetail(spec: ControlPlaneProbeSpec, probe: EndpointProbeResult): string {
  if (probe.error) return probe.error
  if (probe.status != null && spec.reachableStatusCodes?.includes(probe.status)) {
    return `Route reachable (HTTP ${probe.status})`
  }
  if (probe.body && typeof probe.body === 'object') {
    const row = probe.body as { error?: unknown; message?: unknown; details?: unknown }
    if (typeof row.error === 'string' && row.error.trim()) return row.error
    if (typeof row.message === 'string' && row.message.trim()) return row.message
    if (typeof row.details === 'string' && row.details.trim()) return row.details
  }
  if (typeof probe.body === 'string' && probe.body.trim()) {
    return probe.body.slice(0, 180)
  }
  return probe.status == null ? i18n.t('integrationsPage.probeNoResponseBody') : `HTTP ${probe.status}`
}

export function summarizeControlPlaneProbe(
  spec: ControlPlaneProbeSpec,
  probe: EndpointProbeResult,
  capabilityManifest: Set<string> | null,
): ControlPlaneProbeSnapshot {
  const manifestDeclared = capabilityManifest ? capabilityManifest.has(manifestPath(spec.path)) : null

  if (probe.status != null && isReachableStatus(spec, probe.status)) {
    return {
      ...spec,
      status: manifestDeclared === false ? 'WARN' : 'PASS',
      reason: manifestDeclared === false ? 'reachableUndeclared' : 'ready',
      manifestDeclared,
      httpStatus: probe.status,
      durationMs: probe.durationMs,
      detail: toDetail(spec, probe),
    }
  }

  if (manifestDeclared === false && probe.status === 404) {
    return {
      ...spec,
      status: 'WARN',
      reason: 'notAdvertised',
      manifestDeclared,
      httpStatus: probe.status,
      durationMs: probe.durationMs,
      detail: toDetail(spec, probe),
    }
  }

  return {
    ...spec,
    status: manifestDeclared === false ? 'WARN' : 'FAIL',
    reason: probe.status == null ? 'probeFailed' : manifestDeclared === false ? 'notAdvertised' : 'declaredBroken',
    manifestDeclared,
    httpStatus: probe.status,
    durationMs: probe.durationMs,
    detail: toDetail(spec, probe),
  }
}

export function summarizeControlPlaneProbes(
  items: ControlPlaneProbeSnapshot[],
): ControlPlaneProbeSummary {
  return {
    total: items.length,
    passCount: items.filter((item) => item.status === 'PASS').length,
    warnCount: items.filter((item) => item.status === 'WARN').length,
    failCount: items.filter((item) => item.status === 'FAIL').length,
    declaredCount: items.filter((item) => item.manifestDeclared === true).length,
  }
}

import type {
  ControlPlaneProbeId,
  ControlPlaneProbeSnapshot,
  ControlPlaneProbeStatus,
} from './controlPlaneProbes'

export type ControlPlaneRecoveryKind =
  | 'transportFailure'
  | 'declaredBroken'
  | 'missingContract'
  | 'manifestDrift'

export interface ControlPlaneRecoveryRoute {
  path: string
  labelKey:
    | 'nav.dashboard'
    | 'nav.integrations'
    | 'nav.mcpServers'
    | 'nav.safetyRules'
    | 'nav.audit'
    | 'nav.scheduler'
    | 'nav.approvals'
    | 'nav.models'
}

export interface ControlPlaneRecoveryItem {
  probe: ControlPlaneProbeSnapshot
  status: ControlPlaneProbeStatus
  kind: ControlPlaneRecoveryKind
  route: ControlPlaneRecoveryRoute
  stepIds: Array<'checkManifest' | 'probeDirect' | 'inspectProxy' | 'reopenConsole'>
}

export interface ControlPlaneRecoverySummary {
  status: ControlPlaneProbeStatus
  attentionCount: number
  failCount: number
  transportFailureCount: number
  missingContractCount: number
  declaredBrokenCount: number
  manifestDriftCount: number
  items: ControlPlaneRecoveryItem[]
}

const RECOVERY_PRIORITY: ControlPlaneProbeId[] = [
  'toolPolicy',
  'mcpSecurity',
  'slackCommands',
  'slackEvents',
  'a2aDiagnostics',
  'providerModels',
  'errorReport',
  'auditLogs',
  'mcpRegistry',
  'schedulerJobs',
  'approvals',
  'capabilities',
  'opsDashboard',
  'metricsNames',
]

function routeBase(path: string | undefined): string | undefined {
  return path?.split(/[?#]/, 1)[0]
}

function resolveRoute(probe: ControlPlaneProbeSnapshot): ControlPlaneRecoveryRoute {
  const basePath = routeBase(probe.routePath)
  if (basePath === '/tool-policy') {
    return { path: '/safety-rules?tab=tool-policy', labelKey: 'nav.safetyRules' }
  }
  if (basePath === '/output-guard') {
    return { path: '/safety-rules?tab=output-guard', labelKey: 'nav.safetyRules' }
  }
  if (basePath === '/safety-rules') {
    return { path: probe.routePath ?? '/safety-rules', labelKey: 'nav.safetyRules' }
  }
  if (basePath === '/mcp-security' || basePath === '/mcp-servers') {
    return { path: '/mcp-servers', labelKey: 'nav.mcpServers' }
  }
  if (basePath === '/audit') {
    return { path: '/audit', labelKey: 'nav.audit' }
  }
  if (basePath === '/scheduler') {
    return { path: '/scheduler', labelKey: 'nav.scheduler' }
  }
  if (basePath === '/approvals') {
    return { path: '/approvals', labelKey: 'nav.approvals' }
  }
  if (basePath === '/models') {
    return { path: '/models', labelKey: 'nav.models' }
  }
  if (basePath === '/') {
    return { path: '/', labelKey: 'nav.dashboard' }
  }

  return { path: '/integrations', labelKey: 'nav.integrations' }
}

function classifyKind(probe: ControlPlaneProbeSnapshot): ControlPlaneRecoveryKind | null {
  if (probe.status === 'PASS') return null
  if (probe.reason === 'probeFailed') return 'transportFailure'
  if (probe.reason === 'declaredBroken') return 'declaredBroken'
  if (probe.reason === 'reachableUndeclared') return 'manifestDrift'
  return 'missingContract'
}

function resolveSteps(kind: ControlPlaneRecoveryKind): ControlPlaneRecoveryItem['stepIds'] {
  if (kind === 'missingContract') {
    return ['checkManifest', 'reopenConsole']
  }
  if (kind === 'manifestDrift') {
    return ['checkManifest', 'probeDirect', 'reopenConsole']
  }
  if (kind === 'transportFailure') {
    return ['probeDirect', 'inspectProxy', 'reopenConsole']
  }
  return ['probeDirect', 'inspectProxy', 'reopenConsole']
}

function summarizeStatus(items: ControlPlaneRecoveryItem[]): ControlPlaneProbeStatus {
  if (items.some((item) => item.status === 'FAIL')) return 'FAIL'
  if (items.some((item) => item.status === 'WARN')) return 'WARN'
  return 'PASS'
}

function priorityIndex(id: ControlPlaneProbeId): number {
  const index = RECOVERY_PRIORITY.indexOf(id)
  return index === -1 ? RECOVERY_PRIORITY.length : index
}

export function summarizeControlPlaneRecovery(
  probes: ControlPlaneProbeSnapshot[],
): ControlPlaneRecoverySummary {
  const items = probes
    .map((probe) => {
      const kind = classifyKind(probe)
      if (!kind) return null
      return {
        probe,
        status: probe.status,
        kind,
        route: resolveRoute(probe),
        stepIds: resolveSteps(kind),
      } satisfies ControlPlaneRecoveryItem
    })
    .filter((item): item is ControlPlaneRecoveryItem => item != null)
    .sort((left, right) => {
      if (left.status !== right.status) {
        return left.status === 'FAIL' ? -1 : 1
      }
      return priorityIndex(left.probe.id) - priorityIndex(right.probe.id)
    })

  return {
    status: summarizeStatus(items),
    attentionCount: items.length,
    failCount: items.filter((item) => item.status === 'FAIL').length,
    transportFailureCount: items.filter((item) => item.kind === 'transportFailure').length,
    missingContractCount: items.filter((item) => item.kind === 'missingContract').length,
    declaredBrokenCount: items.filter((item) => item.kind === 'declaredBroken').length,
    manifestDriftCount: items.filter((item) => item.kind === 'manifestDrift').length,
    items,
  }
}

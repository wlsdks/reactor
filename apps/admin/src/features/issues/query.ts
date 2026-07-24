import { useQuery } from '@tanstack/react-query'
import { fetchCapabilityManifestCached } from '../capabilities'
import {
  summarizeReactorConnection,
  summarizeMcpProjectConnection,
  type ReactorConnectionSnapshot,
  type McpProjectConnectionSnapshot,
} from '../integrations/projectConnections'
import { queryKeys } from '../../shared/lib/queryKeys'
import * as integrationsApi from '../integrations/api'
import { CONTROL_PLANE_PROBE_SPECS, summarizeControlPlaneProbe } from '../integrations/controlPlaneProbes'
import { summarizeControlPlaneRecovery } from '../integrations/controlPlaneRecovery'
import * as mcpApi from '../mcp-servers/api'
import { summarizeRegistryOverview, summarizeServerConfigReadiness, summarizePolicyDiagnostics, summarizeMcpSecurityOps } from './mcpHelpers'
import { summarizeSchedulerOps } from '../scheduler/schedulerOps'
import * as schedulerApi from '../scheduler/api'
import { summarizeApprovalOps } from '../approvals/approvalOps'
import * as approvalsApi from '../approvals/api'
import { summarizeToolPolicyOps } from '../tool-policy/toolPolicyOps'
import * as toolPolicyApi from '../tool-policy/api'
import * as mcpSecurityApi from '../mcp-security/api'
import { summarizeOutputGuardOps } from '../output-guard/outputGuardOps'
import * as outputGuardApi from '../output-guard/api'
import { summarizeAuditLogs } from '../audit/auditOps'
import * as auditApi from '../audit/api'
import { buildIssueCenterSnapshot } from './issueCenter'
import type { IssueCenterSnapshot, McpIssueSnapshot } from './types'

export const ISSUE_CENTER_QUERY_KEY = ['issue-center', 'snapshot'] as const
const DURABLE_CONTROL_PLANE_PROBES = new Set(['mcpRegistry', 'approvals', 'auditLogs'])

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

async function settle<T>(fn: () => Promise<T>): Promise<{ data: T | null, error: string | null }> {
  try {
    return {
      data: await fn(),
      error: null,
    }
  } catch (error) {
    return {
      data: null,
      error: errorMessage(error),
    }
  }
}

async function loadKnownMcpSnapshots(serverNames: string[]): Promise<McpIssueSnapshot[]> {
  const items = await Promise.all(serverNames.map(async (name): Promise<McpIssueSnapshot | null> => {
    const server = await settle(() => mcpApi.getMcpServer(name))
    if (!server.data) return null

    const kind = name === 'swagger' ? 'swagger' : name === 'atlassian' ? 'atlassian' : null
    if (!kind) return null

    const preflight = await settle(() => mcpApi.getMcpPreflight(name))
    const policy = await settle(() => mcpApi.getMcpAccessPolicy(name))

    return {
      kind,
      server: server.data,
      detailError: server.error,
      configReadiness: summarizeServerConfigReadiness(server.data),
      preflight: preflight.data,
      preflightError: preflight.error,
      policyDiagnostics: policy.data ? summarizePolicyDiagnostics(kind, policy.data) : null,
      policyError: policy.error,
    }
  }))

  return items.filter((item): item is McpIssueSnapshot => item != null)
}

export async function loadIssueCenterSnapshot(): Promise<IssueCenterSnapshot> {
  const capabilities = await fetchCapabilityManifestCached().catch(() => null)
  const durable = capabilities?.durable !== false

  const controlPlaneProbes = await Promise.all(
    CONTROL_PLANE_PROBE_SPECS.map(async (spec) => {
      const manifestPath = spec.path.split('?')[0]
      if (!durable && DURABLE_CONTROL_PLANE_PROBES.has(spec.id)) {
        return summarizeControlPlaneProbe(
          spec,
          { status: null, body: null, durationMs: 0 },
          new Set([...(capabilities ?? [])].filter((path) => path !== manifestPath)),
        )
      }
      // capabilities 매니페스트가 경로를 선언하지 않으면 network probe 를 생략
      // (Socket Mode Slack 엔드포인트, opt-in error-report 등 의도적 미탑재 대응).
      if (capabilities && !capabilities.has(manifestPath)) {
        return summarizeControlPlaneProbe(
          spec,
          { status: null, body: null, durationMs: 0 },
          capabilities,
        )
      }
      const probe = await integrationsApi.probeEndpoint({
        path: spec.path,
        method: spec.method,
      })
      return summarizeControlPlaneProbe(spec, probe, capabilities)
    }),
  )

  const controlPlaneRecovery = summarizeControlPlaneRecovery(controlPlaneProbes)

  const registry = durable
    ? await settle(() => mcpApi.listMcpServers())
    : { data: [], error: null }
  const servers = registry.data ?? []
  const registryOverview = summarizeRegistryOverview(servers)
  const mcpSnapshots = registry.data
    ? await loadKnownMcpSnapshots(registry.data.map((server) => server.name))
    : []

  const [scheduler, approvals, toolPolicy, mcpSecurity, outputGuardRules, outputGuardAudits, auditLogs] = await Promise.all([
    settle(() => schedulerApi.listJobs()),
    durable ? settle(() => approvalsApi.listAllApprovals()) : Promise.resolve({ data: null, error: null }),
    settle(() => toolPolicyApi.getPolicy()),
    settle(() => mcpSecurityApi.getMcpSecurityPolicy()),
    durable ? settle(() => outputGuardApi.listRules()) : Promise.resolve({ data: null, error: null }),
    durable ? settle(() => outputGuardApi.listRuleAudits(100)) : Promise.resolve({ data: null, error: null }),
    durable ? settle(() => auditApi.listAuditLogs(100)) : Promise.resolve({ data: null, error: null }),
  ])

  return buildIssueCenterSnapshot({
    generatedAt: Date.now(),
    controlPlaneRecovery,
    registryOverview,
    mcpServers: mcpSnapshots,
    scheduler: summarizeSchedulerOps(scheduler.data ?? [], scheduler.error),
    approvals: summarizeApprovalOps(approvals.data ?? [], approvals.error),
    toolPolicy: summarizeToolPolicyOps(toolPolicy.data, toolPolicy.error),
    mcpSecurity: summarizeMcpSecurityOps(
      mcpSecurity.data,
      mcpSecurity.error,
      servers.map((server) => server.name),
      registry.error,
    ),
    outputGuard: summarizeOutputGuardOps(outputGuardRules.data ?? [], outputGuardAudits.data ?? [], outputGuardAudits.error),
    audit: summarizeAuditLogs(Array.isArray(auditLogs.data) ? auditLogs.data : [], auditLogs.error),
  })
}

export function useIssueCenterSnapshot(enabled = true) {
  return useQuery({
    queryKey: ISSUE_CENTER_QUERY_KEY,
    queryFn: loadIssueCenterSnapshot,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    enabled,
  })
}

export interface TopologyData {
  reactor: ReactorConnectionSnapshot
  projects: McpProjectConnectionSnapshot[]
}

async function loadTopologyData(): Promise<TopologyData> {
  const [manifest, registry] = await Promise.all([
    fetchCapabilityManifestCached().catch(() => null),
    settle(() => mcpApi.listMcpServers()),
  ])

  const manifestSet = manifest ?? null

  const reactor = summarizeReactorConnection(manifestSet, registry.error)

  // 토폴로지는 레지스트리에 등록된 모든 MCP 서버를 동적으로 표시한다.
  // 하드코딩된 kinds 배열 대신 registry.data 를 순회하여 사용자 추가 서버
  // (예: clipping-mcp-server) 가 즉시 반영되도록 한다.
  const servers = registry.data ?? []
  const projects = await Promise.all(
    servers.map(async (server) => {
      const preflight = await settle(() => mcpApi.getMcpPreflight(server.name))
      return summarizeMcpProjectConnection(server, preflight.data, preflight.error ?? undefined)
    }),
  )

  return { reactor, projects }
}

export function useTopologyData(enabled = true) {
  return useQuery({
    queryKey: queryKeys.issues.topology(),
    queryFn: loadTopologyData,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    enabled,
  })
}

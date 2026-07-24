import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../../shared/lib/queryKeys'
import { resolveApiError } from '../../shared/lib/getErrorMessage'
import { STALE_TIMES } from '../../shared/lib/staleTimes'
import {
  listMcpServers,
  getMcpPreflight,
  listSwaggerSpecSources,
  findKnownProjectServer,
  summarizeReactorConnection,
  summarizeKnownProjectConnection,
} from '../../shared/api/adminApi'
import { fetchCapabilityManifestCached } from '../capabilities'
import * as dashboardApi from './api'
import { classifyMcpReadiness, classifyPlatformReadiness, summarizeMcpReadiness } from './readiness'

export function useDashboardData(
  customMetricNames?: string[],
  loadMetricNames = false,
  enabled = true,
) {
  const dashboardQuery = useQuery({
    queryKey: queryKeys.dashboard.main(customMetricNames),
    queryFn: () => dashboardApi.getDashboard(customMetricNames),
    staleTime: STALE_TIMES.STANDARD,
    enabled,
    // Defensive: never escalate to an error boundary. Both the Dashboard page
    // and the global GlobalStatusStrip handle the error string locally — an
    // uncaught throw here would tear down the entire authenticated layout
    // (the strip mounts on every page).
    throwOnError: false,
  })

  const metricNamesQuery = useQuery({
    queryKey: queryKeys.dashboard.metricNames(),
    queryFn: dashboardApi.listMetricNames,
    staleTime: STALE_TIMES.STATIC,
    enabled: enabled && loadMetricNames,
  })

  const integrationsQuery = useQuery({
    queryKey: queryKeys.dashboard.topology(),
    queryFn: async () => {
      const capabilities = await fetchCapabilityManifestCached().catch(() => null)
      const serversResult = capabilities?.durable === false
        ? { status: 'fulfilled' as const, value: [] }
        : await Promise.resolve(listMcpServers()).then(
            (value) => ({ status: 'fulfilled' as const, value }),
            (reason: unknown) => ({ status: 'rejected' as const, reason }),
          )
      const registryError = serversResult.status === 'rejected'
        ? (serversResult.reason instanceof Error ? serversResult.reason.message : String(serversResult.reason))
        : null

      if (serversResult.status !== 'fulfilled') {
        return {
          readinessSummary: null,
          reactorConnection: summarizeReactorConnection(capabilities, registryError),
          projectConnections: [
            summarizeKnownProjectConnection('atlassian', null, null, registryError ?? undefined),
            summarizeKnownProjectConnection('swagger', null, null, registryError ?? undefined, {
              sourceCount: 0,
              publishedSourceCount: 0,
            }),
          ],
          extraMcpServers: [],
        }
      }

      const servers = serversResult.value
      const atlassianServer = findKnownProjectServer('atlassian', servers)
      const swaggerServer = findKnownProjectServer('swagger', servers)
      const preflightResults = await Promise.all(servers.map(async (server) => {
        if (server.status !== 'CONNECTED') {
          return { server, preflight: null, error: undefined, snapshot: classifyMcpReadiness(server) }
        }
        try {
          const preflight = await getMcpPreflight(server.name)
          return { server, preflight, error: undefined, snapshot: classifyMcpReadiness(server, preflight, null) }
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error)
          return { server, preflight: null, error: message, snapshot: classifyMcpReadiness(server, null, error) }
        }
      }))
      const preflightByName = new Map(preflightResults.map((result) => [result.server.name, result]))
      const atlassianPreflight = atlassianServer ? preflightByName.get(atlassianServer.name) : undefined
      const swaggerPreflight = swaggerServer ? preflightByName.get(swaggerServer.name) : undefined
      const [swaggerSources] = await Promise.all([
        swaggerServer
          ? listSwaggerSpecSources(swaggerServer.name).catch(() => [])
          : Promise.resolve([]),
      ])

      // atlassian / swagger 이외의 MCP 서버(예: clipping-mcp-server)도 대시보드에
      // 노출하기 위해 registry 전체에서 제외 후 extra 로 분리.
      const knownNames = new Set([atlassianServer?.name, swaggerServer?.name].filter(Boolean) as string[])
      const extraMcpServers = servers
        .filter((s) => !knownNames.has(s.name))
        .map((s) => ({ name: s.name, status: s.status, toolCount: s.toolCount }))

      return {
        readinessSummary: summarizeMcpReadiness(preflightResults.map((result) => result.snapshot)),
        reactorConnection: summarizeReactorConnection(capabilities),
        projectConnections: [
          summarizeKnownProjectConnection('atlassian', atlassianServer, atlassianPreflight?.preflight ?? null, atlassianPreflight?.error),
          summarizeKnownProjectConnection(
            'swagger',
            swaggerServer,
            swaggerPreflight?.preflight ?? null,
            swaggerPreflight?.error,
            {
              sourceCount: swaggerSources.length,
              publishedSourceCount: swaggerSources.filter((source) => source.publishedRevisionId != null).length,
            },
          ),
        ],
        extraMcpServers,
      }
    },
    staleTime: STALE_TIMES.STANDARD,
    enabled,
  })

  const platformReadiness = dashboardQuery.data
    ? classifyPlatformReadiness({
        backendReachable: true,
        mcpSummary: integrationsQuery.data?.readinessSummary ?? null,
      })
    : dashboardQuery.error
      ? classifyPlatformReadiness({ backendReachable: false, mcpSummary: null })
      : null
  const dashboardError = dashboardQuery.error
    ? resolveApiError(dashboardQuery.error)
    : null

  return {
    data: dashboardQuery.data ?? null,
    metricNames: metricNamesQuery.data ?? [],
    readinessSummary: integrationsQuery.data?.readinessSummary ?? null,
    platformReadiness,
    reactorConnection: integrationsQuery.data?.reactorConnection ?? null,
    projectConnections: integrationsQuery.data?.projectConnections ?? [],
    extraMcpServers: integrationsQuery.data?.extraMcpServers ?? [],
    isLoading: dashboardQuery.isLoading,
    isFetching: dashboardQuery.isFetching,
    error: dashboardError?.message ?? null,
    errorHint: dashboardError?.hint ?? null,
    refetch: dashboardQuery.refetch,
    // Source-of-truth timestamp for the dashboard payload — used by the
    // health bar to render a localized "마지막 업데이트" line that ticks
    // automatically via `useRelativeTime`. 0 when the query has not yet
    // resolved a payload.
    dataUpdatedAt: dashboardQuery.dataUpdatedAt,
  }
}

import type { ControlPlaneProbeSnapshot, ControlPlaneProbeSummary } from '../controlPlaneProbes'
import type { ControlPlaneRecoverySummary } from '../controlPlaneRecovery'
import type { ReactorConnectionSnapshot, McpProjectConnectionSnapshot } from '../projectConnections'
import type { DashboardReleaseReadinessSummary } from '../../dashboard/types'
import { ControlPlaneProbesPanel } from './ControlPlaneProbesPanel'
import { ControlPlaneRecoveryPanel } from './ControlPlaneRecoveryPanel'
import { ProjectConnectionsPanel } from './ProjectConnectionsPanel'

interface IntegrationsControlPlaneTabProps {
  view: 'overview' | 'run' | 'evidence'
  loadingProbes: boolean
  probeError: string | null
  controlPlaneProbes: ControlPlaneProbeSnapshot[]
  probeSummary: ControlPlaneProbeSummary | null
  releaseReadiness?: DashboardReleaseReadinessSummary | null
  recoverySummary: ControlPlaneRecoverySummary
  onRefreshProbes: () => Promise<unknown>
  onRefreshReadiness: () => Promise<unknown>
  readinessRefreshing?: boolean

  loadingConnections: boolean
  connectionError: string | null
  reactorConnection: ReactorConnectionSnapshot | null
  projectConnections: McpProjectConnectionSnapshot[]
  onRefreshConnections: () => Promise<unknown>
}

export function IntegrationsControlPlaneTab({
  view,
  loadingProbes,
  probeError,
  controlPlaneProbes,
  probeSummary,
  releaseReadiness,
  recoverySummary,
  onRefreshProbes,
  onRefreshReadiness,
  readinessRefreshing,
  loadingConnections,
  connectionError,
  reactorConnection,
  projectConnections,
  onRefreshConnections,
}: IntegrationsControlPlaneTabProps) {
  return (
    <>
      <ControlPlaneProbesPanel
        view={view}
        loading={loadingProbes}
        error={probeError}
        probes={controlPlaneProbes}
        summary={probeSummary}
        releaseReadiness={releaseReadiness}
        onRefresh={onRefreshProbes}
        onRefreshReadiness={onRefreshReadiness}
        readinessRefreshing={readinessRefreshing}
      />

      {view === 'overview' && <ControlPlaneRecoveryPanel
        loading={loadingProbes}
        recoverySummary={recoverySummary}
      />}

      {view === 'overview' && <ProjectConnectionsPanel
        loading={loadingConnections}
        error={connectionError}
        reactorConnection={reactorConnection}
        projectConnections={projectConnections}
        onRefresh={onRefreshConnections}
      />}
    </>
  )
}

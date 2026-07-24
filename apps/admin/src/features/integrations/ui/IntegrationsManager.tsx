import { lazy, Suspense, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import type { TFunction } from 'i18next'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getDashboard } from '../../dashboard/api'
import { usePageHelp } from '../../../shared/lib/usePageHelp'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { isForbiddenError } from '../../../shared/lib/isForbiddenError'
import { EmptyState, LoadingSpinner, PageHeader, SectionErrorBoundary } from '../../../shared/ui'
import {
  listMcpServers,
  getMcpPreflight,
  listSwaggerSpecSources,
  findKnownProjectServer,
  summarizeReactorConnection,
  summarizeKnownProjectConnection,
  type ReactorConnectionSnapshot,
  type McpProjectConnectionSnapshot,
} from '../../../shared/api/adminApi'
import { fetchCapabilityManifestCached } from '../../capabilities'
import * as integrationsApi from '../api'
import {
  CONTROL_PLANE_PROBE_SPECS,
  summarizeControlPlaneProbe,
  summarizeControlPlaneProbes,
  type ControlPlaneProbeSnapshot,
} from '../controlPlaneProbes'
import { summarizeControlPlaneRecovery } from '../controlPlaneRecovery'
import { IntegrationsControlPlaneTab } from './IntegrationsControlPlaneTab'
import './IntegrationsManager.css'

// Tab content is conditional on `testerTab` selection — lazy-load to keep the
// initial IntegrationsPage chunk lean. Each tab brings in its own form/modal
// dependencies (e.g. SlackBotFormModal ~10KB, FAQ subcomponents) that operators
// rarely need on first paint.
const IntegrationsSlackTab = lazy(() =>
  import('./IntegrationsSlackTab').then((m) => ({ default: m.IntegrationsSlackTab })),
)
const IntegrationsErrorReportTab = lazy(() =>
  import('./IntegrationsErrorReportTab').then((m) => ({ default: m.IntegrationsErrorReportTab })),
)
const ProactiveChannelsManager = lazy(() =>
  import('../../proactive-channels/ui/ProactiveChannelsManager').then((m) => ({
    default: m.ProactiveChannelsManager,
  })),
)
const SlackActivityTab = lazy(() =>
  import('../../slack-activity/ui/SlackActivityTab').then((m) => ({ default: m.SlackActivityTab })),
)
const SlackBotTab = lazy(() =>
  import('../../slack-bots/ui/SlackBotTab').then((m) => ({ default: m.SlackBotTab })),
)
const SlackFaqTab = lazy(() =>
  import('../../slack-faq/ui/SlackFaqTab').then((m) => ({ default: m.SlackFaqTab })),
)

// ── Query functions ─────────────────────────────────────────────────────────

type TesterTab = 'slack' | 'error' | 'channels' | 'activity' | 'bots' | 'faq'
type OperationsView = 'overview' | 'run' | 'evidence' | 'tools'

const operationsViews = ['overview', 'run', 'evidence', 'tools'] as const

function parseOperationsView(value: string | null): OperationsView {
  return operationsViews.includes(value as OperationsView) ? value as OperationsView : 'overview'
}

const testerTabConfigs = [
  { id: 'slack' },
  { id: 'error' },
  { id: 'channels' },
  { id: 'activity' },
  { id: 'bots' },
  { id: 'faq' },
] as const satisfies Array<{ id: TesterTab }>

const testerTabs = new Set<TesterTab>(testerTabConfigs.map((tab) => tab.id))

function parseTesterTab(value: string | null): TesterTab | null {
  return value && testerTabs.has(value as TesterTab) ? (value as TesterTab) : null
}

function describeTesterTabLabel(t: TFunction, tab: TesterTab): string {
  if (tab === 'slack') return t('integrationsPage.testerTabSlack')
  if (tab === 'error') return t('integrationsPage.testerTabError')
  if (tab === 'channels') return t('integrationsPage.modeChannels')
  if (tab === 'activity') return t('integrationsPage.tabActivity')
  if (tab === 'bots') return t('slackBotsTab.tabTitle')
  return t('integrationsPage.tabSlackFaq')
}

async function fetchControlPlaneProbes(): Promise<ControlPlaneProbeSnapshot[]> {
  const capabilityManifest = await fetchCapabilityManifestCached({ skipGlobalError: true })
  const items = await Promise.all(
    CONTROL_PLANE_PROBE_SPECS.map(async (spec) => {
      const manifestPath = spec.path.split('?')[0]
      // capabilities 매니페스트가 선언하지 않은 경로는 네트워크 probe 를 생략해
      // 브라우저 콘솔에 4xx 가 기록되지 않도록 한다 (Socket Mode / opt-in 기능 등).
      if (capabilityManifest && !capabilityManifest.has(manifestPath)) {
        return summarizeControlPlaneProbe(
          spec,
          { status: null, body: null, durationMs: 0 },
          capabilityManifest,
        )
      }
      const result = await integrationsApi.probeEndpoint({
        path: spec.path,
        method: spec.method,
      })
      return summarizeControlPlaneProbe(spec, result, capabilityManifest)
    }),
  )
  return items
}

interface ProjectConnectionsResult {
  reactorConnection: ReactorConnectionSnapshot | null
  projectConnections: McpProjectConnectionSnapshot[]
}

async function fetchProjectConnections(): Promise<ProjectConnectionsResult> {
  const capabilities = await fetchCapabilityManifestCached({ skipGlobalError: true })
  const reactorConnection = summarizeReactorConnection(capabilities)

  const servers = await listMcpServers()
  const atlassianServer = findKnownProjectServer('atlassian', servers)
  const swaggerServer = findKnownProjectServer('swagger', servers)

  const [atlassianPreflight, swaggerPreflight, swaggerSources] = await Promise.all([
    atlassianServer
      ? getMcpPreflight(atlassianServer.name)
          .then((preflight) => ({ preflight, error: undefined }))
          .catch((e: Error) => ({ preflight: null, error: e.message }))
      : Promise.resolve({ preflight: null, error: undefined }),
    swaggerServer
      ? getMcpPreflight(swaggerServer.name)
          .then((preflight) => ({ preflight, error: undefined }))
          .catch((e: Error) => ({ preflight: null, error: e.message }))
      : Promise.resolve({ preflight: null, error: undefined }),
    swaggerServer
      ? listSwaggerSpecSources(swaggerServer.name).catch(() => [])
      : Promise.resolve([]),
  ])

  const projectConnections = [
    summarizeKnownProjectConnection('atlassian', atlassianServer, atlassianPreflight.preflight, atlassianPreflight.error),
    summarizeKnownProjectConnection(
      'swagger',
      swaggerServer,
      swaggerPreflight.preflight,
      swaggerPreflight.error,
      {
        sourceCount: swaggerSources.length,
        publishedSourceCount: swaggerSources.filter((source) => source.publishedRevisionId != null).length,
      },
    ),
  ]

  return { reactorConnection, projectConnections }
}

// ── Container component ─────────────────────────────────────────────────────

export function IntegrationsManager() {
  const { t } = useTranslation()
  usePageHelp({ helpKey: 'integrationsPage.helpOverlay' })
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedTesterTab = parseTesterTab(searchParams.get('tab'))
  const testerTab = requestedTesterTab ?? 'slack'
  const operationsView = searchParams.has('view')
    ? parseOperationsView(searchParams.get('view'))
    : requestedTesterTab
      ? 'tools'
      : 'overview'
  const [error, setError] = useState<string | null>(null)

  function selectTesterTab(tab: TesterTab) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('tab', tab)
      return next
    }, { replace: true })
  }

  function selectOperationsView(view: OperationsView) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (view === 'overview') next.delete('view')
      else next.set('view', view)
      if (view !== 'tools') next.delete('tab')
      return next
    }, { replace: true })
  }

  const { data: controlPlaneProbes = [], isLoading: loadingProbes, error: probeErrorRaw } = useQuery({
    queryKey: queryKeys.integrations.probes(),
    queryFn: fetchControlPlaneProbes,
    // This page renders probe failures inline, including expected 403 access
    // denials. Avoid duplicate dev-console/Sentry noise from the global query
    // error hook while preserving the local forbidden/error boundary.
    meta: { skipGlobalError: true },
  })

  const { data: connectionData = null, isLoading: loadingConnections, error: connectionErrorRaw } = useQuery({
    queryKey: queryKeys.integrations.connections(),
    queryFn: fetchProjectConnections,
    meta: { skipGlobalError: true },
  })

  const {
    data: dashboardData = null,
    isFetching: readinessRefreshing,
    refetch: refetchReadiness,
  } = useQuery({
    queryKey: queryKeys.dashboard.main(['reactor.release.readiness']),
    queryFn: () => getDashboard(['reactor.release.readiness']),
  })

  const probeError = probeErrorRaw ? getErrorMessage(probeErrorRaw) : null
  const connectionError = connectionErrorRaw ? getErrorMessage(connectionErrorRaw) : null
  const reactorConnection = connectionData?.reactorConnection ?? null
  const projectConnections = connectionData?.projectConnections ?? []

  // Both top-level queries fail with 403 → render forbidden EmptyState rather
  // than render a tab strip with empty probe/connection panels that would
  // each show their own "load failed" alert. We require both to be 403 so a
  // partial outage (e.g. probes 5xx, connections 200) still shows the page.
  if (
    isForbiddenError(probeErrorRaw) &&
    isForbiddenError(connectionErrorRaw)
  ) {
    return (
      <div className="page">
        <PageHeader
          title={t('nav.integrations')}
          description={t('nav.help.integrations')}
        />
        <EmptyState
          forbidden
          forbiddenContext={t('common.emptyState.forbiddenContext.integrations')}
        />
      </div>
    )
  }

  const probeSummary = controlPlaneProbes.length > 0 ? summarizeControlPlaneProbes(controlPlaneProbes) : null
  const recoverySummary = summarizeControlPlaneRecovery(controlPlaneProbes)

  const commandProbe = controlPlaneProbes.find((p) => p.id === 'slackCommands') ?? null
  const eventProbe = controlPlaneProbes.find((p) => p.id === 'slackEvents') ?? null
  const errorReportProbe = controlPlaneProbes.find((p) => p.id === 'errorReport') ?? null

  return (
    <div className="page">
      <PageHeader
        title={t('nav.integrations')}
        description={t('nav.help.integrations')}
      />

      <div className="integrations-workspace">
        <nav className="integrations-local-nav" aria-label={t('integrationsPage.operationsNavLabel')}>
          {operationsViews.map((view) => (
            <button
              key={view}
              type="button"
              className={operationsView === view ? 'is-active' : undefined}
              aria-current={operationsView === view ? 'page' : undefined}
              onClick={() => selectOperationsView(view)}
            >
              {t(`integrationsPage.operationsViews.${view}`)}
            </button>
          ))}
        </nav>

        <div className="integrations-workspace__content">
      {operationsView !== 'tools' && <IntegrationsControlPlaneTab
        view={operationsView}
        loadingProbes={loadingProbes}
        probeError={probeError}
        controlPlaneProbes={controlPlaneProbes}
        probeSummary={probeSummary}
        releaseReadiness={dashboardData?.releaseReadiness ?? null}
        recoverySummary={recoverySummary}
        onRefreshProbes={() => queryClient.invalidateQueries({ queryKey: queryKeys.integrations.probes() })}
        onRefreshReadiness={() => refetchReadiness()}
        readinessRefreshing={readinessRefreshing}
        loadingConnections={loadingConnections}
        connectionError={connectionError}
        reactorConnection={reactorConnection}
        projectConnections={projectConnections}
        onRefreshConnections={() => queryClient.invalidateQueries({ queryKey: queryKeys.integrations.connections() })}
      />}

      {operationsView === 'tools' && <>
      <div className="detail-tabs integrations-tool-tabs" role="tablist" aria-label={t('integrationsPage.testerTablistLabel')}>
        {testerTabConfigs.map((tab) => (
          <button
            key={tab.id}
            id={`integrations-tab-${tab.id}`}
            className={`tab-btn ${testerTab === tab.id ? 'active' : ''}`}
            role="tab"
            type="button"
            aria-selected={testerTab === tab.id}
            aria-controls={`integrations-tabpanel-${tab.id}`}
            onClick={() => selectTesterTab(tab.id)}
          >
            {describeTesterTabLabel(t, tab.id)}
          </button>
        ))}
      </div>

      {testerTab === 'slack' && (
        <div id="integrations-tabpanel-slack" role="tabpanel" aria-labelledby="integrations-tab-slack">
          <SectionErrorBoundary name="integrations-tester-slack">
            <Suspense fallback={<LoadingSpinner />}>
              <IntegrationsSlackTab
                commandProbe={commandProbe}
                eventProbe={eventProbe}
                error={error}
                onError={setError}
              />
            </Suspense>
          </SectionErrorBoundary>
        </div>
      )}

      {testerTab === 'error' && (
        <div id="integrations-tabpanel-error" role="tabpanel" aria-labelledby="integrations-tab-error">
          <SectionErrorBoundary name="integrations-tester-error">
            <Suspense fallback={<LoadingSpinner />}>
              <IntegrationsErrorReportTab
                errorReportProbe={errorReportProbe}
                error={error}
                onError={setError}
              />
            </Suspense>
          </SectionErrorBoundary>
        </div>
      )}

      {testerTab === 'channels' && (
        <div id="integrations-tabpanel-channels" role="tabpanel" aria-labelledby="integrations-tab-channels">
          <SectionErrorBoundary name="integrations-tester-channels">
            <Suspense fallback={<LoadingSpinner />}>
              <ProactiveChannelsManager />
            </Suspense>
          </SectionErrorBoundary>
        </div>
      )}

      {testerTab === 'activity' && (
        <div id="integrations-tabpanel-activity" role="tabpanel" aria-labelledby="integrations-tab-activity">
          <SectionErrorBoundary name="integrations-tester-activity">
            <Suspense fallback={<LoadingSpinner />}>
              <SlackActivityTab />
            </Suspense>
          </SectionErrorBoundary>
        </div>
      )}

      {testerTab === 'bots' && (
        <div id="integrations-tabpanel-bots" role="tabpanel" aria-labelledby="integrations-tab-bots">
          <SectionErrorBoundary name="integrations-tester-bots">
            <Suspense fallback={<LoadingSpinner />}>
              <SlackBotTab />
            </Suspense>
          </SectionErrorBoundary>
        </div>
      )}

      {testerTab === 'faq' && (
        <div id="integrations-tabpanel-faq" role="tabpanel" aria-labelledby="integrations-tab-faq">
          <SectionErrorBoundary name="integrations-tester-faq">
            <Suspense fallback={<LoadingSpinner />}>
              <SlackFaqTab />
            </Suspense>
          </SectionErrorBoundary>
        </div>
      )}
      </>}
        </div>
      </div>
    </div>
  )
}

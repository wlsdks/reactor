import { useTranslation } from 'react-i18next'
import type {
  ReactorConnectionSnapshot,
  McpProjectConnectionSnapshot,
} from '../../integrations/projectConnections'
import type { OpsMetricSnapshot, DashboardRecentTrustEvent } from '../types'
import { ActivityFeed } from './ActivityFeed'

interface DashboardInfraPanelProps {
  statusCounts: Record<string, number>
  reactorConnection: ReactorConnectionSnapshot | null
  projectConnections: McpProjectConnectionSnapshot[]
  /** projectConnections 에 포함되지 않은 추가 MCP 서버 (예: clipping 같은 커스텀). */
  extraMcpServers?: Array<{ name: string; status: string; toolCount?: number }>
  metrics: OpsMetricSnapshot[]
  trustEvents: DashboardRecentTrustEvent[]
  generatedAt: number
}

function getStatusDotColor(status: string): string {
  switch (status) {
    case 'PASS':
    case 'CONNECTED':
      return 'var(--green)'
    case 'WARN':
      return 'var(--yellow)'
    case 'FAIL':
    case 'DISCONNECTED':
      return 'var(--red)'
    default:
      return 'var(--text-dim)'
  }
}

function serverLabel(name: string): string {
  const normalized = name.trim().toLowerCase()
  if (normalized === 'atlassian') return 'Atlassian'
  if (normalized === 'swagger') return 'Swagger'
  return name
}

export function DashboardInfraPanel({
  statusCounts,
  reactorConnection,
  projectConnections,
  extraMcpServers,
  metrics,
  trustEvents,
  generatedAt,
}: DashboardInfraPanelProps) {
  const { t } = useTranslation()

  // Build the server list from Reactor and project connections.
  const servers: Array<{ name: string; status: string }> = []

  if (reactorConnection) {
    servers.push({ name: 'Reactor', status: reactorConnection.status })
  }

  for (const conn of projectConnections) {
    servers.push({
      // 실제 서버 이름이 존재하면 우선 사용. preset expectedName은 도메인 라벨이라
      // "atlassian" / "swagger"처럼 짧아 사용자 혼동을 유발하지 않음.
      name: conn.server?.name ?? conn.expectedName,
      status: conn.status,
    })
  }

  // 추가 등록 MCP 서버 (예: clipping) 도 노출
  if (extraMcpServers) {
    for (const extra of extraMcpServers) {
      servers.push({ name: extra.name, status: extra.status })
    }
  }

  // NOTE: 과거에는 `statusCounts`에 포함되지만 projectConnections에 없는 서버를
  // `connected-1` 같은 합성 이름으로 채워넣었는데, 이는 이미 표시된 서버의 상태가
  // preflight 실패로 FAIL이 나올 때 실제 CONNECTED 카운트를 두 번 집계하여
  // 유령 서버를 만들어내는 버그였다. (예: atlassian이 FAIL로 1번 + "connected-1"로
  // 다시 1번 등장). 동일 서버를 중복 표시하기보다는 projectConnections에서
  // 실제 상태만 보여주는 게 정확. 추가 서버는 전용 MCP Servers 페이지에서 관리.
  void statusCounts
  const hasActivity = metrics.some((metric) => metric.meterCount > 0) || trustEvents.length > 0

  return (
    <section className="infra-panel" aria-label={t('dashboard.infra.title')}>
      {/* MCP Server list */}
      <div className="infra-section">
        <h3 className="section-title">{t('dashboard.infra.mcpServers')}</h3>
        <div className="server-list">
          {servers.map((server, i) => (
            <div key={`${server.name}-${i}`} className="server-row">
              <span
                className="server-row__dot"
                style={{ background: getStatusDotColor(server.status) }}
              />
              <span className="server-row__name">{serverLabel(server.name)}</span>
              <span className="server-row__status">
                {t(`common.statuses.${server.status}`, { defaultValue: server.status })}
              </span>
            </div>
          ))}
          {servers.length === 0 && (
            <span className="text-muted">{t('common.noData')}</span>
          )}
        </div>
      </div>

      {/* Activity Feed */}
      <div className="infra-section infra-section--activity">
        <h3 className="section-title">{t('dashboard.infra.recentActivity')}</h3>
        {hasActivity ? (
          <ActivityFeed
            metrics={metrics}
            trustEvents={trustEvents}
            generatedAt={generatedAt}
          />
        ) : (
          <p className="infra-section__empty">{t('dashboard.infra.noRecentActivity')}</p>
        )}
      </div>
    </section>
  )
}

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { RefreshButton, SkeletonCard } from '../../../shared/ui'
import type { ReactorConnectionSnapshot, McpProjectConnectionSnapshot } from '../projectConnections'
import { describeProjectStatus } from './probeDescribers'

interface ProjectConnectionsPanelProps {
  loading: boolean
  error: string | null
  reactorConnection: ReactorConnectionSnapshot | null
  projectConnections: McpProjectConnectionSnapshot[]
  onRefresh: () => Promise<unknown>
}

function statusLabel(status: string, t: ReturnType<typeof useTranslation>['t']): string {
  const key = `common.statuses.${status}`
  const translated = t(key)
  return translated === key ? t('common.statusUnknown') : translated
}

export function ProjectConnectionsPanel({
  loading,
  error,
  reactorConnection,
  projectConnections,
  onRefresh,
}: ProjectConnectionsPanelProps) {
  const { t } = useTranslation()

  return (
    <section className="project-connections" aria-labelledby="project-connections-title">
      <div className="detail-section-header">
        <h2 id="project-connections-title" className="section-title project-connections__title">{t('integrationsPage.projectConnectionsTitle')}</h2>
        <RefreshButton onRefresh={onRefresh} isFetching={loading} />
      </div>
      <p className="detail-note">{t('integrationsPage.projectConnectionsDescription')}</p>

      {error && (
        <div className="alert alert-error alert-with-retry project-connections__error">
          <span className="alert-message">{error}</span>
          <button className="btn btn-sm btn-secondary" onClick={onRefresh}>{t('common.retry')}</button>
        </div>
      )}

      {loading ? (
        <div className="project-connections__loading">
          <SkeletonCard height={76} />
          <SkeletonCard height={76} />
          <SkeletonCard height={76} />
        </div>
      ) : (
        <div className="project-connections__list">
          {reactorConnection && (
            <article className="project-connections__item">
              <div className="project-connections__main">
                <span className={`project-connections__dot is-${reactorConnection.status.toLowerCase()}`} aria-hidden="true" />
                <div>
                  <strong>{t('integrationsPage.projects.reactor')}</strong>
                  <p>{reactorConnection.missingPaths.length === 0 ? t('integrationsPage.projectStatus.reactorHealthy') : t('integrationsPage.projectStatus.reactorMissing')}</p>
                </div>
              </div>
              <span className="project-connections__status">{statusLabel(reactorConnection.status, t)}</span>
              <details className="project-connections__technical">
                <summary>{t('common.technicalDetails')}</summary>
                <dl>
                  <div><dt>{t('integrationsPage.apiBase')}</dt><dd><code>{reactorConnection.apiBase}</code></dd></div>
                  <div><dt>{t('integrationsPage.requiredRoutes')}</dt><dd>4</dd></div>
                </dl>
                {reactorConnection.missingPaths.length > 0 && <ul>{reactorConnection.missingPaths.map((path) => <li key={path}><code>{path}</code></li>)}</ul>}
              </details>
            </article>
          )}

          {projectConnections.map((snapshot) => (
            <article key={snapshot.id} className="project-connections__item">
              <div className="project-connections__main">
                <span className={`project-connections__dot is-${snapshot.status.toLowerCase()}`} aria-hidden="true" />
                <div>
                  <strong>{snapshot.id === 'atlassian' ? t('integrationsPage.projects.atlassian') : t('integrationsPage.projects.swagger')}</strong>
                  <p>{describeProjectStatus(t, snapshot)}</p>
                </div>
              </div>
              <div className="project-connections__actions">
                <span className="project-connections__status">{statusLabel(snapshot.status, t)}</span>
                <Link className="btn btn-secondary btn-sm" to="/mcp-servers">{t('integrationsPage.openRegistry')}</Link>
              </div>
              <details className="project-connections__technical">
                <summary>{t('common.technicalDetails')}</summary>
                <dl>
                  <div><dt>{t('integrationsPage.expectedName')}</dt><dd>{snapshot.expectedName}</dd></div>
                  <div><dt>{t('integrationsPage.registeredName')}</dt><dd>{snapshot.server?.name ?? '—'}</dd></div>
                  <div><dt>{t('integrationsPage.registeredStatus')}</dt><dd>{snapshot.server?.status ? statusLabel(snapshot.server.status, t) : '—'}</dd></div>
                  <div><dt>{t('integrationsPage.toolCount')}</dt><dd>{snapshot.server?.toolCount ?? 0}</dd></div>
                  {snapshot.preflight && <>
                    <div><dt>{t('integrationsPage.preflightPass')}</dt><dd>{snapshot.preflight.summary.passCount}</dd></div>
                    <div><dt>{t('integrationsPage.preflightWarn')}</dt><dd>{snapshot.preflight.summary.warnCount}</dd></div>
                    <div><dt>{t('integrationsPage.preflightFail')}</dt><dd>{snapshot.preflight.summary.failCount}</dd></div>
                  </>}
                  {snapshot.id === 'swagger' && <>
                    <div><dt>{t('integrationsPage.sourceCount')}</dt><dd>{snapshot.sourceCount ?? 0}</dd></div>
                    <div><dt>{t('integrationsPage.publishedSourceCount')}</dt><dd>{snapshot.publishedSourceCount ?? 0}</dd></div>
                  </>}
                </dl>
              </details>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

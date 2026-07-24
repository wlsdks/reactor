import { FileSearch, Gavel, RefreshCw, Workflow } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { PageHeader, SkeletonCard, Tabs } from '../../../shared/ui'
import { ReleaseCockpit } from '../../dashboard/ui/ReleaseCockpit'
import { useReleaseOperationsData } from '../useReleaseOperationsData'
import '../../dashboard/ui/dashboard.css'
import './release-operations.css'

type ReleaseOperationsView = 'decision' | 'boundary' | 'evidence'

const releaseOperationsViews = new Set<ReleaseOperationsView>([
  'decision',
  'boundary',
  'evidence',
])

function resolveReleaseOperationsView(search: string, hash: string): ReleaseOperationsView {
  const requestedView = new URLSearchParams(search).get('view')
  if (requestedView && releaseOperationsViews.has(requestedView as ReleaseOperationsView)) {
    return requestedView as ReleaseOperationsView
  }
  if (hash === '#release-workflow') return 'boundary'
  if (hash === '#release-evidence') return 'evidence'
  return 'decision'
}

const viewHashes: Record<ReleaseOperationsView, string> = {
  decision: '#release-cockpit',
  boundary: '#release-workflow',
  evidence: '#release-evidence',
}

export function ReleaseOperationsWorkspace() {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const { readiness, isLoading, isFetching, error, refetch } = useReleaseOperationsData()
  const activeView = resolveReleaseOperationsView(location.search, location.hash)

  function handleViewChange(next: string) {
    if (!releaseOperationsViews.has(next as ReleaseOperationsView)) return
    const view = next as ReleaseOperationsView
    void navigate({
      pathname: location.pathname,
      search: `?view=${view}`,
      hash: viewHashes[view],
    }, { replace: true })
  }

  const tabs = [
    {
      value: 'decision',
      label: (
        <span className="release-operations-view-tab">
          <Gavel size={15} strokeWidth={1.75} aria-hidden="true" />
          {t('releaseOperations.views.decision')}
        </span>
      ),
      panel: (
        <div className="release-operations-view">
          <p className="release-operations-view__description">
            {t('releaseOperations.views.decisionDescription')}
          </p>
          <ReleaseCockpit readiness={readiness} view="decision" />
        </div>
      ),
    },
    {
      value: 'boundary',
      label: (
        <span className="release-operations-view-tab">
          <Workflow size={15} strokeWidth={1.75} aria-hidden="true" />
          {t('releaseOperations.views.boundary')}
        </span>
      ),
      panel: (
        <div className="release-operations-view">
          <p className="release-operations-view__description">
            {t('releaseOperations.views.boundaryDescription')}
          </p>
          <ReleaseCockpit readiness={readiness} view="boundary" />
        </div>
      ),
    },
    {
      value: 'evidence',
      label: (
        <span className="release-operations-view-tab">
          <FileSearch size={15} strokeWidth={1.75} aria-hidden="true" />
          {t('releaseOperations.views.evidence')}
        </span>
      ),
      panel: (
        <div id="release-evidence" className="release-operations-view">
          <p className="release-operations-view__description">
            {t('releaseOperations.views.evidenceDescription')}
          </p>
          <ReleaseCockpit readiness={readiness} view="evidence" />
        </div>
      ),
    },
  ]

  return (
    <div className="page release-operations-page">
      <PageHeader
        title={t('releaseOperations.title')}
        description={t('releaseOperations.description')}
        actions={(
          <button
            className="btn btn-secondary btn-sm"
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
          >
            <RefreshCw size={15} aria-hidden="true" />
            {isFetching ? t('releaseOperations.refreshing') : t('common.refresh')}
          </button>
        )}
      />

      {error && readiness && (
        <div className="alert alert-warning" role="status">
          {t('releaseOperations.staleDataWarning')}
        </div>
      )}

      {isLoading ? (
        <div className="release-operations-page__loading" aria-label={t('common.loading')}>
          <SkeletonCard height={112} />
          <SkeletonCard height={320} />
          <SkeletonCard height={240} />
        </div>
      ) : error && !readiness ? (
        <section className="release-operations-unavailable" role="alert">
          <h2>{t('releaseOperations.unavailableTitle')}</h2>
          <p>{t('releaseOperations.unavailableDescription')}</p>
          <div className="release-operations-unavailable__actions">
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => void refetch()}
              disabled={isFetching}
            >
              {isFetching ? t('releaseOperations.refreshing') : t('releaseOperations.retry')}
            </button>
            <details className="release-operations-unavailable__technical">
              <summary>{t('releaseOperations.technicalError')}</summary>
              <code>{error}</code>
            </details>
          </div>
        </section>
      ) : (
        <Tabs
          tabs={tabs}
          value={activeView}
          onChange={handleViewChange}
          ariaLabel={t('releaseOperations.views.label')}
        />
      )}
    </div>
  )
}

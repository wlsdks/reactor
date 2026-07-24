import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { EmptyState, LoadingSpinner, PageHeader } from '../../shared/ui'
import { useFeatureAvailability } from './context'
import { getRouteRequirements } from './requirements'
import { useRoleVisibility } from '../workspace'

interface FeatureRouteProps {
  routePath: string
  titleKey: string
  allowWhenUnavailable?: boolean
  children: ReactNode
}

export function FeatureRoute({
  routePath,
  titleKey,
  allowWhenUnavailable = false,
  children,
}: FeatureRouteProps) {
  const { t } = useTranslation()
  const { isLoading, isRouteAvailable, mode } = useFeatureAvailability()
  const { isRouteVisible } = useRoleVisibility()

  if (isLoading) {
    return (
      <div className="page-loading">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  // BX audit blind spot #6: when an ADMIN_MANAGER (or any role lacking
  // visibility) navigates directly to a dev-only URL, the previous behaviour
  // was a silent `Navigate to="/"` — they landed on the dashboard with no
  // explanation. Now we render a brand-consistent permission-denied page so
  // they understand *why* they can't see the requested route. Server-side
  // 403 enforcement remains the security boundary; this is UX only.
  if (!isRouteVisible(routePath)) {
    return (
      <div className="page" data-testid="permission-denied-page">
        <PageHeader title={t(titleKey)} />
        <EmptyState
          forbidden
          message={t('error.permissionDenied')}
          forbiddenContext={t('error.permissionDeniedHint')}
        />
        <div className="permission-denied-actions">
          <Link to="/" className="btn btn-secondary btn-sm">
            {t('error.permissionDeniedAction')}
          </Link>
        </div>
      </div>
    )
  }

  if (!isRouteAvailable(routePath)) {
    if (allowWhenUnavailable) {
      return <>{children}</>
    }

    const isDev = import.meta.env.DEV
    const requirements = isDev ? getRouteRequirements(routePath) : []
    const detectionMode = mode === 'manifest'
      ? t('common.featureUnavailableDetectionManifest')
      : t('common.featureUnavailableDetectionUnavailable')

    return (
      <div className="page feature-route-unavailable" data-testid="feature-unavailable-page">
        <PageHeader title={t(titleKey)} />

        <section className="feature-route-unavailable__notice" aria-live="polite">
          <h2>{t('common.featureUnavailableTitle')}</h2>
          <p>{t('common.featureUnavailableDescription', { feature: t(titleKey) })}</p>
          <Link className="feature-route-unavailable__status-link" to="/health">
            {t('common.openStatusPage')}
          </Link>
          {isDev && (
            <details className="feature-route-unavailable__technical">
              <summary>{t('common.featureUnavailableTechnical')}</summary>
              <dl>
                <div>
                  <dt>{t('common.featureUnavailableDetection')}</dt>
                  <dd>{detectionMode}</dd>
                </div>
                <div>
                  <dt>{t('common.featureUnavailableRequirements')}</dt>
                  <dd>
                    {requirements.length > 0 ? (
                      <ul>
                        {requirements.map((requirement) => <li key={requirement}><code>{requirement}</code></li>)}
                      </ul>
                    ) : t('common.featureUnavailableNoRequirements')}
                  </dd>
                </div>
              </dl>
            </details>
          )}
        </section>
      </div>
    )
  }

  return <>{children}</>
}

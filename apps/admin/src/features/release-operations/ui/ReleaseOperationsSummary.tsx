import { ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import { RELEASE_WORKFLOW_PATHS_BY_ID } from '../../../shared/releaseWorkflow'
import type { DashboardReleaseReadinessSummary } from '../../dashboard/types'

export function ReleaseOperationsSummary({
  readiness,
}: {
  readiness?: DashboardReleaseReadinessSummary | null
}) {
  const { t } = useTranslation()
  const status = readiness?.status ?? 'missing'
  const blockers = readiness?.blockingReports?.length ?? 0
  const warnings = readiness?.warningReports?.length ?? 0
  const passed = readiness?.summary?.passed
    ?? readiness?.tagRecommendation?.passedReports?.length
    ?? 0
  const total = readiness?.summary?.total
    ?? readiness?.requiredReports?.length
    ?? passed
  const recommendedTag = readiness?.tagRecommendation?.recommendedTag
    ?? readiness?.recommendedTag
    ?? t('dashboard.release.noTag')

  return (
    <section className="release-operations-summary" aria-labelledby="release-operations-summary-title">
      <header className="release-operations-summary__header">
        <div>
          <h2 id="release-operations-summary-title">
            {t('releaseOperations.dashboardSummary.title')}
          </h2>
          <p>{t('releaseOperations.dashboardSummary.description')}</p>
        </div>
        <div className="release-operations-summary__decision">
          <span className={`release-operations-summary__status is-${status}`}>
            <span aria-hidden="true" />
            {t(`dashboard.release.status.${status}`)}
          </span>
          <Link className="release-operations-summary__link" to={RELEASE_WORKFLOW_PATHS_BY_ID.cockpit}>
            {t('releaseOperations.dashboardSummary.open')}
            <ArrowRight size={15} aria-hidden="true" />
          </Link>
        </div>
      </header>
      <dl className="release-operations-summary__metrics">
        <div>
          <dt>{t('releaseOperations.dashboardSummary.gates')}</dt>
          <dd>{formatLocaleNumber(passed)}/{formatLocaleNumber(total)}</dd>
        </div>
        <div>
          <dt>{t('releaseOperations.dashboardSummary.blockers')}</dt>
          <dd>{formatLocaleNumber(blockers)}</dd>
        </div>
        <div>
          <dt>{t('releaseOperations.dashboardSummary.warnings')}</dt>
          <dd>{formatLocaleNumber(warnings)}</dd>
        </div>
        <div>
          <dt>{t('dashboard.release.recommendedTag')}</dt>
          <dd>{recommendedTag}</dd>
        </div>
      </dl>
    </section>
  )
}

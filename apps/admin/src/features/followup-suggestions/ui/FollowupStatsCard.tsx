import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { formatPercent } from '../../../shared/lib/formatters'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { SkeletonText } from '../../../shared/ui/Skeleton'
import { fetchFollowupStats } from '../api'

// Slack follow-up button CTR card.
// - Defaults to a 24-hour aggregation window with category top 5.
// - Backend: GET /api/admin/followup-suggestions/stats.
export function FollowupStatsCard() {
  const { t } = useTranslation()
  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.followupSuggestions.stats(24),
    queryFn: () => fetchFollowupStats(24),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  })

  if (isLoading) {
    return (
      <div className="followup-stats followup-stats--loading" aria-busy="true" aria-label={t('followupSuggestions.loadingCtr')}>
        <span className="sr-only">{t('followupSuggestions.loadingCtr')}</span>
        <SkeletonText lines={3} lastLineWidth="60%" />
      </div>
    )
  }
  if (isError || !data) return null

  const ctrLabel = formatPercent(data.ctr)
  const top5 = data.byCategory.slice(0, 5)

  return (
    <section className="followup-stats">
      <div className="followup-stats__head">
        <h3>{t('followupSuggestions.title')}</h3>
        <span>{t('followupSuggestions.recentWindow', { hours: data.windowHours })}</span>
      </div>
      <dl className="followup-stats__summary">
        <div><dt>{t('followupSuggestions.impressions')}</dt><dd>{data.totalImpressions}</dd></div>
        <div><dt>{t('followupSuggestions.clicks')}</dt><dd>{data.totalClicks}</dd></div>
        <div><dt>{t('followupSuggestions.ctr')}</dt><dd>{ctrLabel}</dd></div>
      </dl>
      {top5.length > 0 && (
        <div className="followup-stats__categories">
          <h4>
            {t('followupSuggestions.topCategories')}
          </h4>
          <ul>
            {top5.map((c) => (
              <li key={c.category}>
                <code>{c.category}</code>
                <span>
                  {c.clicks} / {c.impressions} ({formatPercent(c.ctr)})
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

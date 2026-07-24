import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ArrowDown, ArrowUp, Minus } from 'lucide-react'
import {
  SkeletonCard,
  CollapsibleSection,
  Tooltip,
} from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { formatPercent } from '../../../shared/lib/formatters'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import * as feedbackApi from '../api'
import type { NegativeBucket } from '../types'
import { FollowupStatsCard } from '../../followup-suggestions/ui/FollowupStatsCard'

interface Props {
  from?: string
  to?: string
}

/**
 * Stats overview — CISO/PM reporting panel.
 *
 * UX rationale:
 * - 6 KPI cards: total / positive / negative / rate / inbox / change vs prev.
 * - "Change vs previous period" arrow red if increase, green if decrease.
 * - Top-N negative by domain/intent/tool in a 3-column grid with Wilson LB sort.
 * - sampleWarning badge when sample size < 30 (Wilson LB still shown but marked).
 * - Collapsed by default so the main list isn't pushed down.
 */
export function FeedbackStatsPanel({ from, to }: Props) {
  const { t } = useTranslation()
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.feedback.stats(from, to),
    queryFn: () => feedbackApi.fetchFeedbackStats(from, to),
  })

  if (isLoading) {
    // Stats panel is collapsed by default, so we render a small skeleton
    // that matches the collapsed header bar + 6-card grid without pushing
    // the page down when it expands.
    return (
      <div className="detail-panel detail-panel--compact fb-stats-surface" aria-busy="true">
        <div className="stat-grid fb-stats-grid">
          <SkeletonCard count={6} height={72} />
        </div>
      </div>
    )
  }
  if (error || !data) return null

  const rateLabel = formatPercent(data.positiveRate)
  const prevRateLabel = formatPercent(data.previousPeriodRate)
  const negativeDelta = data.negativeChange
  const deltaClass = negativeDelta > 0 ? 'fb-change--up' : negativeDelta < 0 ? 'fb-change--down' : ''
  const DeltaIcon = negativeDelta > 0 ? ArrowUp : negativeDelta < 0 ? ArrowDown : Minus

  return (
    <CollapsibleSection
      title={t('feedbackPage.stats.title')}
      defaultOpen={false}
    >
      <div className="detail-panel detail-panel--compact fb-stats-surface">
        <dl className="feedback-stats-summary">
          <div><dt>{t('feedbackPage.stats.total')}</dt><dd>{formatLocaleNumber(data.total)}</dd></div>
          <div><dt>{t('feedbackPage.stats.positive')}</dt><dd>{formatLocaleNumber(data.positive)}</dd></div>
          <div><dt>{t('feedbackPage.stats.negative')}</dt><dd>{formatLocaleNumber(data.negative)}</dd></div>
          <div><dt>{t('feedbackPage.stats.positiveRate')}</dt><dd>{rateLabel}</dd></div>
          <div><dt>{t('feedbackPage.stats.inbox')}</dt><dd>{formatLocaleNumber(data.inboxCount)}</dd></div>
          <div>
            <dt>{t('feedbackPage.stats.vsPrevious')}</dt>
            <dd>
              <span className={`fb-change ${deltaClass}`}>
                <DeltaIcon className="fb-change__icon" aria-hidden="true" size={14} strokeWidth={1.8} />
                {formatLocaleNumber(Math.abs(negativeDelta))}
              </span>
              <span className="feedback-stats-summary__previous">({prevRateLabel})</span>
            </dd>
          </div>
        </dl>

        <h3 className="detail-section-title fb-stats-subtitle">
          {t('feedbackPage.stats.topNegativesTitle')}
        </h3>
        <div className="fb-top-grid">
          <TopNegativePanel
            title={t('feedbackPage.stats.topDomains')}
            buckets={data.topNegativeDomains}
          />
          <TopNegativePanel
            title={t('feedbackPage.stats.topIntents')}
            buckets={data.topNegativeIntents}
          />
          <TopNegativePanel
            title={t('feedbackPage.stats.topTools')}
            buckets={data.topNegativeTools}
          />
        </div>
        <FollowupStatsCard />
      </div>
    </CollapsibleSection>
  )
}

function TopNegativePanel({
  title,
  buckets,
}: {
  title: string
  buckets: NegativeBucket[]
}) {
  const { t } = useTranslation()
  return (
    <div className="fb-top-panel">
      <h3 className="fb-top-panel__title">{title}</h3>
      {buckets.length === 0 ? (
        <div className="fb-top-row__sample">{t('common.noData')}</div>
      ) : (
        buckets.map((b) => (
          <Tooltip key={b.key} content={t('feedbackPage.stats.wilsonLowerBound', { value: formatPercent(b.wilsonLowerBound) })}>
            <div className="fb-top-row">
              <span className="fb-top-row__key">
                {b.key}
                {b.sampleWarning && (
                  <span className="fb-top-row__warning">
                    · {t('feedbackPage.stats.smallSample')}
                  </span>
                )}
              </span>
              <span className="fb-top-row__rate">{formatPercent(b.negativeRate)}</span>
              <span className="fb-top-row__sample">
                {b.negativeCount}/{b.totalCount}
              </span>
            </div>
          </Tooltip>
        ))
      )}
    </div>
  )
}

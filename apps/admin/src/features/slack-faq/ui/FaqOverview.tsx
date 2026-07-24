import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { queryKeys } from '../../../shared/lib/queryKeys'
import { SkeletonText } from '../../../shared/ui/Skeleton'
import { getFaqChannel, getFaqChannelStats } from '../api'

interface Props {
  channelId: string
  onRequestEdit: () => void
}

/**
 * Read-only summary of a FAQ channel's configuration plus high-level stats.
 * Edit button defers to parent (which opens the form modal in edit mode).
 */
export function FaqOverview({ channelId, onRequestEdit }: Props) {
  const { t } = useTranslation()

  const channelQuery = useQuery({
    queryKey: queryKeys.slackFaq.channel(channelId),
    queryFn: () => getFaqChannel(channelId),
  })
  const statsQuery = useQuery({
    queryKey: queryKeys.slackFaq.channelStats(channelId),
    queryFn: () => getFaqChannelStats(channelId),
  })

  if (channelQuery.isLoading) {
    return (
      <div className="faq-overview" data-testid="faq-overview">
        <SkeletonText lines={4} />
      </div>
    )
  }

  if (channelQuery.error || !channelQuery.data) {
    return (
      <div className="faq-overview" data-testid="faq-overview" role="alert">
        {t('slackFaq.overview.loadError')}
      </div>
    )
  }

  const channel = channelQuery.data
  const stats = statsQuery.data

  return (
    <div className="faq-overview" data-testid="faq-overview">
      <header className="faq-overview__header">
        <div><h3>{t('slackFaq.overview.title')}</h3><p>{t('slackFaq.overview.description')}</p></div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRequestEdit} data-testid="faq-overview-edit-btn">{t('common.edit')}</button>
      </header>
      <dl className="faq-overview__list">
        <div>
          <dt>{t('slackFaq.form.channelId')}</dt>
          <dd className="mono">{channel.channelId}</dd>
        </div>
        <div>
          <dt>{t('slackFaq.form.channelName')}</dt>
          <dd>{channel.channelName ?? '—'}</dd>
        </div>
        <div>
          <dt>{t('slackFaq.form.enabled')}</dt>
          <dd>
            <span className={`faq-plain-status ${channel.enabled ? 'is-active' : ''}`}><span aria-hidden="true" />{channel.enabled ? t('slackFaq.list.statusEnabled') : t('slackFaq.list.statusDisabled')}</span>
          </dd>
        </div>
        <div>
          <dt>{t('slackFaq.form.autoReplyMode')}</dt>
          <dd>{t(`slackFaq.form.modeLabels.${channel.autoReplyMode}`)}</dd>
        </div>
        <div>
          <dt>{t('slackFaq.form.confidenceThreshold')}</dt>
          <dd>{Math.round(channel.confidenceThreshold * 100)}%</dd>
        </div>
        <div>
          <dt>{t('slackFaq.form.daysBack')}</dt>
          <dd className="mono">{channel.daysBack}</dd>
        </div>
        <div>
          <dt>{t('slackFaq.form.reIngestIntervalHours')}</dt>
          <dd className="mono">{channel.reIngestIntervalHours}</dd>
        </div>
        {stats && (
          <>
            <div>
              <dt>{t('slackFaq.overview.totalQueries')}</dt>
              <dd className="mono">{stats.totalQueries}</dd>
            </div>
            <div>
              <dt>{t('slackFaq.overview.hitRate')}</dt>
              <dd className="mono">{Math.round(stats.hitRate * 100)}%</dd>
            </div>
            <div>
              <dt>{t('slackFaq.overview.avgConfidence')}</dt>
              <dd>{Math.round(stats.avgConfidence * 100)}%</dd>
            </div>
          </>
        )}
      </dl>
    </div>
  )
}

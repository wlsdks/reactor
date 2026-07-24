import { useQueries, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { queryKeys } from '../../../shared/lib/queryKeys'
import { EmptyState } from '../../../shared/ui/EmptyState'
import { SkeletonText } from '../../../shared/ui/Skeleton'
import { getFaqChannelStats, listFaqChannels } from '../api'
import type { FaqChannel, FaqChannelStats } from '../types'

interface Props {
  selectedId: string | null
  onSelect: (channelId: string | null) => void
}

/**
 * Left rail of the FAQ tab — lists FAQ-enabled Slack channels with inline
 * KPIs (24h queries, hit rate, enabled status). Selecting a row drives the
 * detail pane.
 */
export function FaqChannelList({ selectedId, onSelect }: Props) {
  const { t } = useTranslation()

  const { data: channels = [], isLoading, error, refetch } = useQuery({
    queryKey: queryKeys.slackFaq.channels(),
    queryFn: listFaqChannels,
  })

  const statsQueries = useQueries({
    queries: channels.map((channel) => ({
      queryKey: queryKeys.slackFaq.channelStats(channel.channelId),
      queryFn: () => getFaqChannelStats(channel.channelId),
      enabled: channels.length > 0,
    })),
  })

  const statsByChannel: Record<string, FaqChannelStats | undefined> = {}
  channels.forEach((channel, idx) => {
    statsByChannel[channel.channelId] = statsQueries[idx]?.data
  })

  const handleKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, id: string) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelect(id)
    }
  }

  return (
    <aside className="faq-channel-list" aria-label={t('slackFaq.list.aria')}>
      <div className="faq-channel-list__heading">
        <h3>{t('slackFaq.list.title')}</h3>
        <span>{channels.length}</span>
      </div>

      {isLoading ? (
        <div className="faq-channel-list__loading">
          <SkeletonText lines={3} />
        </div>
      ) : error ? (
        <div className="faq-channel-list__unavailable" role="alert">
          <strong>{t('slackFaq.list.loadErrorTitle')}</strong>
          <p>{t('slackFaq.list.loadErrorDescription')}</p>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => refetch()}>
            {t('common.retry')}
          </button>
        </div>
      ) : channels.length === 0 ? (
        <EmptyState
          message={t('slackFaq.list.emptyTitle')}
          description={t('slackFaq.list.emptyHint')}
        />
      ) : (
        <ul className="faq-channel-list__items">
          {channels.map((channel) => (
            <li key={channel.channelId}>
              <FaqChannelRow
                channel={channel}
                stats={statsByChannel[channel.channelId]}
                selected={selectedId === channel.channelId}
                onSelect={onSelect}
                onKeyDown={handleKeyDown}
              />
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}

function FaqChannelRow({
  channel,
  stats,
  selected,
  onSelect,
  onKeyDown,
}: {
  channel: FaqChannel
  stats: FaqChannelStats | undefined
  selected: boolean
  onSelect: (id: string) => void
  onKeyDown: (e: React.KeyboardEvent<HTMLButtonElement>, id: string) => void
}) {
  const { t } = useTranslation()
  const queries = stats?.totalQueries ?? null
  const hitRate = stats ? Math.round(stats.hitRate * 100) : null

  return (
    <button
      type="button"
      className={`faq-channel-row ${selected ? 'is-selected' : ''}`}
      aria-pressed={selected}
      onClick={() => onSelect(channel.channelId)}
      onKeyDown={(e) => onKeyDown(e, channel.channelId)}
      data-testid={`faq-channel-row-${channel.channelId}`}
    >
      <span
        className={`faq-channel-row__dot ${channel.enabled ? 'enabled' : 'disabled'}`}
        aria-label={
          channel.enabled
            ? t('slackFaq.list.statusEnabled')
            : t('slackFaq.list.statusDisabled')
        }
        title={
          channel.enabled
            ? t('slackFaq.list.statusEnabled')
            : t('slackFaq.list.statusDisabled')
        }
      />
      <span className="faq-channel-row__name">
        {channel.channelName ?? channel.channelId}
        <small>{channel.channelId}</small>
      </span>
      <span className="faq-channel-row__kpis">
        <span>
          {t('slackFaq.list.kpiQueries', {
            count: queries ?? 0,
          })}
        </span>
        <span>
          {hitRate == null
            ? t('slackFaq.list.kpiHitRateUnknown')
            : t('slackFaq.list.kpiHitRate', { rate: hitRate })}
        </span>
      </span>
    </button>
  )
}

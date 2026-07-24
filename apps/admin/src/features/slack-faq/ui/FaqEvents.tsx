import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { queryKeys } from '../../../shared/lib/queryKeys'
import { DataTable } from '../../../shared/ui/DataTable'
import { EmptyState } from '../../../shared/ui/EmptyState'
import { SkeletonTable } from '../../../shared/ui/Skeleton'
import type { Column } from '../../../shared/ui/DataTable'
import { getFaqChannelEvents } from '../api'
import type { FaqEvent } from '../types'

interface Props {
  channelId: string
}

function formatTimestamp(ts: number): string {
  if (!Number.isFinite(ts) || ts <= 0) return '—'
  return new Intl.DateTimeFormat('ko-KR', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(new Date(ts))
}

export function FaqEvents({ channelId }: Props) {
  const { t } = useTranslation()
  const { data: events = [], isLoading, error } = useQuery({
    queryKey: queryKeys.slackFaq.events(channelId),
    queryFn: () => getFaqChannelEvents(channelId),
  })

  if (isLoading) return <SkeletonTable rows={5} columns={6} />
  if (error)
    return (
      <div role="alert" className="form-error">
        {t('slackFaq.events.loadError')}
      </div>
    )
  if (events.length === 0) {
    return <EmptyState message={t('slackFaq.events.empty')} />
  }

  const columns: Column<FaqEvent>[] = [
    {
      key: 'ts',
      header: t('slackFaq.events.col.ts'),
      sortable: true,
      responsivePriority: 1,
      render: (row) => <span className="mono">{formatTimestamp(row.ts)}</span>,
      exportAccessor: (row) => formatTimestamp(row.ts),
    },
    {
      key: 'userId',
      header: t('slackFaq.events.col.userId'),
      sortable: true,
      responsivePriority: 3,
      render: (row) => <span className="mono">{row.userId ?? '—'}</span>,
      exportAccessor: (row) => row.userId ?? '',
    },
    {
      key: 'query',
      header: t('slackFaq.events.col.query'),
      sortable: true,
      responsivePriority: 1,
      render: (row) => row.query,
    },
    {
      key: 'matchedFaqId',
      header: t('slackFaq.events.col.matched'),
      sortable: true,
      responsivePriority: 3,
      render: (row) => <span className="mono">{row.matchedFaqId ?? '—'}</span>,
      exportAccessor: (row) => row.matchedFaqId ?? '',
    },
    {
      key: 'confidence',
      header: t('slackFaq.events.col.confidence'),
      sortable: true,
      responsivePriority: 2,
      render: (row) =>
        row.confidence == null ? '—' : <span className="mono">{row.confidence.toFixed(2)}</span>,
      exportAccessor: (row) => (row.confidence == null ? '' : row.confidence.toFixed(2)),
    },
    {
      key: 'outcome',
      header: t('slackFaq.events.col.outcome'),
      sortable: true,
      responsivePriority: 1,
      render: (row) => <span className={`faq-outcome faq-outcome--${row.outcome.toLowerCase()}`}>{t(`slackFaq.events.outcome.${row.outcome}`)}</span>,
      exportAccessor: (row) => row.outcome,
    },
  ]

  return (
    <div data-testid="faq-events">
      <h3>{t('slackFaq.events.title', { count: events.length })}</h3>
      <DataTable
        columns={columns}
        data={events}
        keyFn={(row) => row.id}
        urlStateKey="faq-events"
        exportable={{ filename: 'faq-events' }}
      />
    </div>
  )
}

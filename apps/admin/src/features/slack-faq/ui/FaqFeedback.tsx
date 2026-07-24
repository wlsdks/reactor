import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { DataTable } from '../../../shared/ui/DataTable'
import { EmptyState } from '../../../shared/ui/EmptyState'
import { SkeletonTable } from '../../../shared/ui/Skeleton'
import type { Column } from '../../../shared/ui/DataTable'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getFaqChannelFeedback } from '../api'
import type { FaqFeedback as FaqFeedbackRow } from '../types'

interface Props {
  channelId: string
}

function formatTimestamp(ts: number): string {
  if (!Number.isFinite(ts) || ts <= 0) return '—'
  const d = new Date(ts)
  return d.toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, 'Z')
}

export function FaqFeedback({ channelId }: Props) {
  const { t } = useTranslation()
  const { data: feedback = [], isLoading, error } = useQuery({
    queryKey: queryKeys.slackFaq.feedback(channelId),
    queryFn: () => getFaqChannelFeedback(channelId),
  })

  if (isLoading) return <SkeletonTable rows={5} columns={4} />
  if (error)
    return (
      <div role="alert" className="form-error">
        {t('slackFaq.feedback.loadError')}
      </div>
    )
  if (feedback.length === 0) {
    return <EmptyState message={t('slackFaq.feedback.empty')} />
  }

  const columns: Column<FaqFeedbackRow>[] = [
    {
      key: 'rating',
      header: t('slackFaq.feedback.col.rating'),
      sortable: true,
      // Render with a textual label alongside the icon so colorblind users
      // and screen readers don't depend on glyph alone.
      render: (row) => (
        <span aria-label={row.rating}>
          {row.rating === 'UP'
            ? t('slackFaq.feedback.ratingUp')
            : t('slackFaq.feedback.ratingDown')}
        </span>
      ),
      exportAccessor: (row) => row.rating,
    },
    {
      key: 'comment',
      header: t('slackFaq.feedback.col.comment'),
      render: (row) => row.comment ?? '—',
    },
    {
      key: 'eventId',
      header: t('slackFaq.feedback.col.eventId'),
      sortable: true,
      render: (row) => <span className="mono">{row.eventId}</span>,
    },
    {
      key: 'ts',
      header: t('slackFaq.feedback.col.ts'),
      sortable: true,
      render: (row) => <span className="mono">{formatTimestamp(row.ts)}</span>,
      exportAccessor: (row) => formatTimestamp(row.ts),
    },
  ]

  return (
    <div data-testid="faq-feedback">
      <h3>{t('slackFaq.feedback.title', { count: feedback.length })}</h3>
      <DataTable
        columns={columns}
        data={feedback}
        keyFn={(row) => row.id}
        urlStateKey="faq-feedback"
        exportable={{ filename: 'faq-feedback' }}
      />
    </div>
  )
}

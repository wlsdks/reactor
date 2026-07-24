import { useTranslation } from 'react-i18next'
import type { ConversationOverview } from '../../types'

interface OverviewSummaryProps {
  data: ConversationOverview
}

const HEALTHY_STATUSES = new Set(['completed', 'succeeded', 'passed'])

export function OverviewSummary({ data }: OverviewSummaryProps) {
  const { t } = useTranslation()
  const completed = data.statusCounts.completed ?? data.statusCounts.succeeded ?? 0
  const needsAttention = Object.entries(data.statusCounts)
    .filter(([status]) => !HEALTHY_STATUSES.has(status.toLowerCase()))
    .reduce((sum, [, count]) => sum + count, 0)

  return (
    <dl className="sessions-overview-summary" aria-label={t('conversations.overview.summaryLabel')}>
      <div>
        <dt>{t('conversations.overview.totalSessions')}</dt>
        <dd>{data.totalSessions}</dd>
      </div>
      <div>
        <dt>{t('conversations.overview.activeUsers')}</dt>
        <dd>{data.activeUsers}</dd>
      </div>
      <div>
        <dt>{t('conversations.overview.completed')}</dt>
        <dd>{completed}</dd>
      </div>
      <div>
        <dt>{t('conversations.overview.needsAttention')}</dt>
        <dd>{needsAttention}</dd>
      </div>
    </dl>
  )
}

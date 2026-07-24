import '../sessions.css'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../../../../shared/lib/queryKeys'
import { usePageHelp } from '../../../../shared/lib/usePageHelp'
import { WorkspaceUnavailable } from '../../../../shared/ui'
import { EmptyState } from '../../../../shared/ui/EmptyState'
import { getErrorMessage } from '../../../../shared/lib/getErrorMessage'
import { getConversationOverview } from '../../api'
import { OverviewSummary } from './OverviewSummary'
import { SessionsRevalidation } from '../shared/SessionsRevalidation'

type Period = '7d' | '30d' | '90d'

function OverviewSkeleton() {
  return (
    <div className="overview-skeleton-container">
      <div className="overview-skeleton sessions-overview-summary">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="overview-skeleton overview-skeleton-card" />
        ))}
      </div>
      <div className="overview-skeleton overview-skeleton-shortcuts" />
    </div>
  )
}

export function ConversationOverview() {
  const { t } = useTranslation()
  usePageHelp({ helpKey: 'sessionsPage.help' })
  const navigate = useNavigate()
  const [period, setPeriod] = useState<Period>('7d')

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: queryKeys.sessions.overview(period),
    queryFn: () => getConversationOverview(period),
  })

  const handleViewAllSessions = () => {
    void navigate('/sessions/feed')
  }

  const handleViewAllUsers = () => {
    void navigate('/sessions/users')
  }

  const retryOverview = () => refetch()
  const hasUnavailableSnapshot = Boolean(error && !data)
  const hasRevalidationError = Boolean(error && data)

  return (
    <div className="conversation-overview">
      {!hasUnavailableSnapshot && (
        <div className="conversation-overview-header">
          <span>{t('conversations.overview.periodLabel')}</span>
          <select
            className="overview-period-select"
            value={period}
            onChange={(e) => setPeriod(e.target.value as Period)}
          >
            <option value="7d">{t('conversations.period.7d')}</option>
            <option value="30d">{t('conversations.period.30d')}</option>
            <option value="90d">{t('conversations.period.90d')}</option>
          </select>
        </div>
      )}

      {isLoading && !data && <OverviewSkeleton />}

      {hasUnavailableSnapshot && (
        <WorkspaceUnavailable
          title={t('conversations.overview.loadErrorTitle')}
          description={t('conversations.overview.loadErrorDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.loading')}
          onRetry={retryOverview}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{ title: t('conversations.recovery.title'), steps: [t('conversations.recovery.account'), t('conversations.recovery.connection')], technicalLabel: t('common.technicalDetails'), technicalDetail: getErrorMessage(error) }}
        />
      )}

      {hasRevalidationError && <SessionsRevalidation onRetry={retryOverview} isRetrying={isFetching} />}

      {data && !isLoading && (
        <>
          <OverviewSummary data={data} />

          <div
            className="sessions-overview-shortcuts"
            aria-label={t('conversations.overview.shortcutsLabel')}
          >
            <button type="button" onClick={handleViewAllSessions}>
              <span>{t('conversations.overview.viewSessions')}</span>
              <span aria-hidden="true">→</span>
            </button>
            <button type="button" onClick={handleViewAllUsers}>
              <span>{t('conversations.overview.viewUsers')}</span>
              <span aria-hidden="true">→</span>
            </button>
          </div>

          {data.totalSessions === 0 && (
            <EmptyState
              message={t('conversations.overview.noData')}
              description={t('conversations.overview.noDataDescription')}
            />
          )}
        </>
      )}
    </div>
  )
}

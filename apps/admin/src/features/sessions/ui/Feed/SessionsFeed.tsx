import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { queryKeys } from '../../../../shared/lib/queryKeys'
import { usePageHelp } from '../../../../shared/lib/usePageHelp'
import { formatDateTime } from '../../../../shared/lib/formatters'
import { getErrorMessage } from '../../../../shared/lib/getErrorMessage'
import { DataTable, EmptyState, SkeletonTable, WorkspaceUnavailable } from '../../../../shared/ui'
import type { Column } from '../../../../shared/ui'
import { listSessionsFeed } from '../../api'
import type { SessionRow } from '../../types'
import { SessionSearchBar } from './SessionSearchBar'
import { SessionsRevalidation } from '../shared/SessionsRevalidation'
import { formatSessionUser } from '../shared/formatSessionUser'

const PAGE_SIZE = 30

function statusLabel(t: (key: string) => string, status: string | undefined): string {
  if (!status) return t('conversations.status.unknown')
  const normalized = status.trim().toLowerCase()
  const supported = ['completed', 'running', 'pending', 'failed', 'cancelled']
  return supported.includes(normalized)
    ? t(`conversations.status.${normalized}`)
    : t('conversations.status.unknown')
}

export function SessionsFeed() {
  const { t } = useTranslation()
  usePageHelp({ helpKey: 'sessionsFeedPage.help' })
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [page, setPage] = useState(1)
  const query = searchParams.get('q') ?? ''
  const offset = (page - 1) * PAGE_SIZE

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: queryKeys.sessions.feed({ q: query || undefined, offset }),
    queryFn: () => listSessionsFeed({ q: query || undefined }, offset, PAGE_SIZE),
  })

  const sessions = data?.items ?? []
  const total = data?.total ?? 0

  const columns: Column<SessionRow>[] = [
    {
      key: 'preview',
      header: t('conversations.feed.columns.preview'),
      width: '45%',
      render: (session) => (
        <span className="sessions-feed-preview" title={session.preview}>
          {session.preview || t('common.noData')}
        </span>
      ),
    },
    {
      key: 'userId',
      header: t('conversations.feed.columns.user'),
      width: '12%',
      responsivePriority: 3,
      render: (session) => <span>{formatSessionUser(t, session.userId)}</span>,
    },
    {
      key: 'status',
      header: t('conversations.feed.columns.status'),
      width: '11%',
      render: (session) => <span className="session-status-text">{statusLabel(t, session.status)}</span>,
    },
    {
      key: 'updatedAt',
      header: t('conversations.feed.columns.updatedAt'),
      width: '16%',
      responsivePriority: 3,
      render: (session) => (
        <span className="data-mono">
          {session.updatedAt != null ? formatDateTime(session.updatedAt) : '—'}
        </span>
      ),
    },
  ]

  function handleSearch(nextQuery: string) {
    setPage(1)
    setSearchParams(nextQuery ? { q: nextQuery } : {}, { replace: true })
  }

  function handleSessionClick(session: SessionRow) {
    void navigate(`/sessions/${session.sessionId}`)
  }

  function retryFeed() {
    return refetch()
  }

  const hasUnavailableSnapshot = Boolean(error && !data)
  const hasRevalidationError = Boolean(error && data)

  return (
    <div className="sessions-feed-workspace">
      {!hasUnavailableSnapshot && (
        <div className="sessions-feed-toolbar">
          <SessionSearchBar value={query} onChange={handleSearch} />
          {data ? <span className="sessions-feed-count">
            {t('conversations.feed.totalCount', { count: total })}
          </span> : null}
        </div>
      )}

      {isLoading && !data && <SkeletonTable rows={8} columns={6} />}

      {hasUnavailableSnapshot && (
        <WorkspaceUnavailable
          title={t('conversations.feed.loadErrorTitle')}
          description={t('conversations.feed.loadErrorDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.loading')}
          onRetry={retryFeed}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{ title: t('conversations.recovery.title'), steps: [t('conversations.recovery.account'), t('conversations.recovery.connection')], technicalLabel: t('common.technicalDetails'), technicalDetail: getErrorMessage(error) }}
        />
      )}

      {hasRevalidationError && <SessionsRevalidation onRetry={retryFeed} isRetrying={isFetching} />}

      {!isLoading && data && sessions.length === 0 && (
        <EmptyState
          message={query ? t('conversations.feed.noResults') : t('conversations.feed.noData')}
          filtered={Boolean(query)}
          filterSummary={query ? `${t('conversations.feed.search')}: ${query}` : undefined}
          onClearFilters={query ? () => handleSearch('') : undefined}
        />
      )}

      {!isLoading && data && sessions.length > 0 && (
        <DataTable
          columns={columns}
          data={sessions}
          keyFn={(session) => session.sessionId}
          onRowClick={handleSessionClick}
          page={page}
          pageSize={PAGE_SIZE}
          totalCount={total}
          onPageChange={setPage}
          tableId="sessions-feed"
          exportable={{ filename: 'sessions' }}
        />
      )}
    </div>
  )
}

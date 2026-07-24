import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { queryKeys } from '../../../../shared/lib/queryKeys'
import { useUrlState } from '../../../../shared/lib/useUrlState'
import { formatDateTime } from '../../../../shared/lib/formatters'
import { getErrorMessage } from '../../../../shared/lib/getErrorMessage'
import { DataTable, EmptyState, SkeletonTable, WorkspaceUnavailable } from '../../../../shared/ui'
import type { Column } from '../../../../shared/ui'
import { listUsers } from '../../api'
import { SessionSearchBar } from '../Feed/SessionSearchBar'
import type { UserSummary } from '../../types'
import { SessionsRevalidation } from '../shared/SessionsRevalidation'
import { formatSessionUser } from '../shared/formatSessionUser'

const PAGE_SIZE = 30

export function UsersList() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [urlState, setUrlState] = useUrlState(
    { q: '' as string, p: 1 },
    { prefix: 'users' },
  )
  const query = urlState.q ?? ''
  const page = urlState.p ?? 1
  const offset = (page - 1) * PAGE_SIZE

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: queryKeys.sessions.users({ q: query, offset }),
    queryFn: () => listUsers({ q: query || undefined, offset, limit: PAGE_SIZE }),
  })

  const users = data?.items ?? []
  const total = data?.total ?? 0

  const columns: Column<UserSummary>[] = [
    {
      key: 'userId',
      header: t('conversations.users.columns.user'),
      width: '32%',
      render: (user) => <span>{formatSessionUser(t, user.userId)}</span>,
    },
    {
      key: 'sessionCount',
      header: t('conversations.users.columns.sessions'),
      width: '18%',
      render: (user) => <span className="data-mono">{user.sessionCount}</span>,
    },
    {
      key: 'lastActiveAt',
      header: t('conversations.users.columns.lastActive'),
      width: '28%',
      render: (user) => (
        <span className="data-mono">
          {user.lastActiveAt != null
            ? formatDateTime(user.lastActiveAt)
            : user.lastActive != null
              ? formatDateTime(user.lastActive)
              : '—'}
        </span>
      ),
    },
  ]

  function handleSearch(nextQuery: string) {
    setUrlState({ q: nextQuery || undefined, p: 1 })
  }

  function handleUserClick(user: UserSummary) {
    void navigate(`/sessions/users/${user.userId}`)
  }

  function retryUsers() {
    return refetch()
  }

  const hasUnavailableSnapshot = Boolean(error && !data)
  const hasRevalidationError = Boolean(error && data)

  return (
    <div className="session-users-workspace">
      {!hasUnavailableSnapshot && (
        <div className="session-users-toolbar">
          <SessionSearchBar
            value={query}
            onChange={handleSearch}
            placeholder={t('conversations.users.search')}
          />
          {data ? <span className="session-users-count">
            {t('conversations.users.userCount', { count: total })}
          </span> : null}
        </div>
      )}

      {isLoading && !data && <SkeletonTable rows={8} columns={4} />}

      {hasUnavailableSnapshot && (
        <WorkspaceUnavailable
          title={t('conversations.users.loadErrorTitle')}
          description={t('conversations.users.loadErrorDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.loading')}
          onRetry={retryUsers}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{ title: t('conversations.recovery.title'), steps: [t('conversations.recovery.account'), t('conversations.recovery.connection')], technicalLabel: t('common.technicalDetails'), technicalDetail: getErrorMessage(error) }}
        />
      )}

      {hasRevalidationError && <SessionsRevalidation onRetry={retryUsers} isRetrying={isFetching} />}

      {!isLoading && data && users.length === 0 && (
        <EmptyState
          message={query ? undefined : t('conversations.users.noUsers')}
          filtered={Boolean(query)}
          filterSummary={query ? `${t('conversations.users.search')}: ${query}` : undefined}
          onClearFilters={query ? () => handleSearch('') : undefined}
        />
      )}

      {!isLoading && data && users.length > 0 && (
        <DataTable
          columns={columns}
          data={users}
          keyFn={(user) => user.userId}
          onRowClick={handleUserClick}
          page={page}
          pageSize={PAGE_SIZE}
          totalCount={total}
          onPageChange={(nextPage) => setUrlState({ p: nextPage })}
          tableId="session-users"
          exportable={{ filename: 'session-users' }}
        />
      )}
    </div>
  )
}

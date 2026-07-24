import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { formatDateTime } from '../../../../shared/lib/formatters'
import { getErrorMessage } from '../../../../shared/lib/getErrorMessage'
import { queryKeys } from '../../../../shared/lib/queryKeys'
import { Breadcrumb, DataTable, EmptyState, PageHeader, SkeletonTable, Tabs, WorkspaceUnavailable } from '../../../../shared/ui'
import type { Column } from '../../../../shared/ui'
import type { TabDefinition } from '../../../../shared/ui/Tabs'
import { listUserSessions, listUsers } from '../../api'
import type { SessionRow } from '../../types'
import { SessionSearchBar } from '../Feed/SessionSearchBar'
import { UserMemoryTab } from '../../../user-memory'
import { SessionsRevalidation } from '../shared/SessionsRevalidation'
import { formatSessionUser } from '../shared/formatSessionUser'

const PAGE_SIZE = 30

function statusLabel(t: (key: string, options?: { defaultValue?: string }) => string, status: string | undefined): string {
  if (!status) return t('conversations.status.unknown')
  const normalized = status.toLowerCase()
  const supported = ['completed', 'running', 'pending', 'failed', 'cancelled']
  return supported.includes(normalized) ? t(`conversations.status.${normalized}`) : t('conversations.status.unknown')
}

export function UserSessionsList() {
  const { t } = useTranslation()
  const { userId = '' } = useParams<{ userId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') === 'memory' ? 'memory' : 'sessions'
  const query = searchParams.get('q') ?? ''
  const page = Math.max(1, Number(searchParams.get('page')) || 1)
  const offset = (page - 1) * PAGE_SIZE

  const userQuery = useQuery({
    queryKey: queryKeys.sessions.users({ q: userId }),
    queryFn: () => listUsers({ q: userId, limit: 1 }),
    enabled: Boolean(userId),
  })
  const user = userQuery.data?.items.find((item) => item.userId === userId)
  const userLabel = user ? formatSessionUser(t, userId) : t('conversations.users.userRecordTitle')

  const sessionsQuery = useQuery({
    queryKey: queryKeys.sessions.userSessions(userId, { q: query || undefined, offset }),
    queryFn: () => listUserSessions(userId, { q: query || undefined }, offset, PAGE_SIZE),
    enabled: Boolean(userId) && activeTab === 'sessions',
  })

  const columns: Column<SessionRow>[] = [
    {
      key: 'preview', header: t('conversations.feed.columns.preview'), width: '58%',
      render: (session) => <span className="sessions-feed-preview">{session.preview || t('common.noData')}</span>,
    },
    {
      key: 'status', header: t('conversations.feed.columns.status'), width: '14%',
      render: (session) => <span className="session-status-text">{statusLabel(t, session.status)}</span>,
    },
    {
      key: 'updatedAt', header: t('conversations.feed.columns.updatedAt'), width: '16%',
      render: (session) => <span className="data-mono">{session.updatedAt != null ? formatDateTime(session.updatedAt) : '—'}</span>,
    },
  ]

  function updateParams(next: Record<string, string | undefined>) {
    setSearchParams((previous) => {
      const params = new URLSearchParams(previous)
      for (const [key, value] of Object.entries(next)) {
        if (!value || value === '1' || (key === 'tab' && value === 'sessions')) params.delete(key)
        else params.set(key, value)
      }
      return params
    }, { replace: true })
  }

  const sessions = sessionsQuery.data?.items ?? []
  const total = sessionsQuery.data?.total ?? 0
  const hasUnavailableSnapshot = Boolean(sessionsQuery.error && !sessionsQuery.data)
  const hasRevalidationError = Boolean(sessionsQuery.error && sessionsQuery.data)
  const tabs: TabDefinition[] = [
    {
      value: 'sessions',
      label: t('conversations.users.tabSessions'),
      panel: (
        <section className="user-session-ledger" aria-label={t('conversations.users.sessionsLedger')}>
          {!hasUnavailableSnapshot && (
            <div className="session-users-toolbar">
              <SessionSearchBar value={query} onChange={(value) => updateParams({ q: value || undefined, page: undefined })} placeholder={t('conversations.feed.search')} />
              {sessionsQuery.data ? <span className="session-users-count">{t('conversations.feed.totalCount', { count: total })}</span> : null}
            </div>
          )}

          {sessionsQuery.isLoading && !sessionsQuery.data && <SkeletonTable rows={6} columns={5} />}
          {hasUnavailableSnapshot && <WorkspaceUnavailable title={t('conversations.feed.loadErrorTitle')} description={t('conversations.feed.loadErrorDescription')} retryLabel={t('common.retry')} retryingLabel={t('common.loading')} onRetry={() => sessionsQuery.refetch()} secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }} guide={{ title: t('conversations.recovery.title'), steps: [t('conversations.recovery.account'), t('conversations.recovery.connection')], technicalLabel: t('common.technicalDetails'), technicalDetail: getErrorMessage(sessionsQuery.error) }} />}
          {hasRevalidationError && <SessionsRevalidation onRetry={() => sessionsQuery.refetch()} isRetrying={sessionsQuery.isFetching} />}
          {!sessionsQuery.isLoading && sessionsQuery.data && sessions.length === 0 && (
            <EmptyState message={query ? t('conversations.feed.noResults') : t('conversations.feed.noData')} filtered={Boolean(query)} onClearFilters={query ? () => updateParams({ q: undefined, page: undefined }) : undefined} />
          )}
          {!sessionsQuery.isLoading && sessionsQuery.data && sessions.length > 0 && (
            <DataTable columns={columns} data={sessions} keyFn={(session) => session.sessionId} onRowClick={(session) => void navigate(`/sessions/${session.sessionId}`)} page={page} pageSize={PAGE_SIZE} totalCount={total} onPageChange={(next) => updateParams({ page: String(next) })} tableId="user-session-ledger" exportable={{ filename: `sessions-${userId}` }} />
          )}
        </section>
      ),
    },
    { value: 'memory', label: t('userMemoryTab.tabTitle'), panel: <UserMemoryTab userId={userId} /> },
  ]

  return (
    <div className="page user-session-detail">
      <Breadcrumb items={[
        { label: t('conversations.title'), href: '/sessions' },
        { label: t('conversations.users.title'), href: '/sessions/users' },
        { label: userLabel },
      ]} />

      <PageHeader
        title={userLabel}
        description={user
          ? t('conversations.users.detailSummary', { count: user.sessionCount, date: user.lastActiveAt != null ? formatDateTime(user.lastActiveAt) : '—' })
          : t('conversations.users.detailDescription')}
      />

      <Tabs tabs={tabs} value={activeTab} onChange={(tab) => updateParams({ tab, q: undefined, page: undefined })} ariaLabel={t('conversations.users.tablistLabel')} />
    </div>
  )
}

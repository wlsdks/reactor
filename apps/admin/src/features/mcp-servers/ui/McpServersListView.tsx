import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Search, X } from 'lucide-react'
import {
  DataTable,
  ConfirmDialog,
  RefreshButton,
  TableSkeleton,
  EmptyState,
  OperationButton,
  PageHeader,
  HelpHint,
  WorkspaceUnavailable,
} from '../../../shared/ui'
import type { Column } from '../../../shared/ui'
import { isForbiddenError } from '../../../shared/lib/isForbiddenError'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useMcpServersList } from '../useMcpServersList'
import type { ServerRowData } from '../useMcpServersList'
import {
  displayMcpServerDescription,
  displayMcpServerName,
  localizeMcpConnectionStatus,
  localizeMcpTransport,
} from '../mcpDisplay'
import { RegisterServerModal } from './RegisterServerModal'
import { GlobalSettingsModal } from './GlobalSettingsModal'
import './McpServersListView.css'

// ── Component ──────────────────────────────────────────────────────────────

export function McpServersListView() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  // Modal open state — owned by the list view since both modals are
  // launched from the page header / empty state CTA.
  const [registerModalOpen, setRegisterModalOpen] = useState(false)
  const [globalSettingsOpen, setGlobalSettingsOpen] = useState(false)

  const {
    servers,
    filteredRows,
    isLoading,
    isFetching,
    serversError,
    policyError,
    totalCount,
    connectedCount,
    failedCount,
    blockedCount,
    searchInput,
    setSearchInput,
    statusFilter,
    setStatusFilterParam,
    tagFilter,
    setTagFilterParam,
    blockedOnly,
    setBlockedFilterParam,
    allTags,
    anyServerHasTags,
    page,
    setPage,
    PAGE_SIZE,
    sortKey,
    sortDirection,
    handleSort,
    confirmAction,
    setConfirmAction,
    handleConnectAllDisconnected,
    handleEmergencyBlockAll,
    handleRefresh,
  } = useMcpServersList()

  // ── Columns ──────────────────────────────────────────────────────────────

  const columns: Column<ServerRowData>[] = [
    {
      key: 'name',
      header: t('mcpServers.list.columnServer'),
      width: '22%',
      sortable: true,
      responsivePriority: 1,
      render: (row) => (
        <div>
          <div className="mcp-server-name">{displayMcpServerName(row.name)}</div>
          {row.description && (
            <div className="mcp-server-desc">
              {displayMcpServerDescription(row.name, row.description)}
            </div>
          )}
        </div>
      ),
      exportAccessor: (row) => displayMcpServerName(row.name),
    },
    {
      key: 'status',
      header: t('mcpServers.list.columnStatus'),
      width: '12%',
      sortable: true,
      responsivePriority: 1,
      render: (row) => (
        <span className={`mcp-connection-state mcp-connection-state--${row.status.toLowerCase()}`}>
          <span aria-hidden="true" />
          {localizeMcpConnectionStatus(row.status, t)}
        </span>
      ),
      exportAccessor: (row) => row.status,
    },
    {
      key: 'transport',
      header: (
        <span className="text-with-hint">
          {t('mcpServers.list.columnTransport')}
          <HelpHint label={t('mcpServersPage.help.transport')} />
        </span>
      ),
      width: '10%',
      responsivePriority: 3,
      render: (row) => (
        <span className="mcp-transport-label">
          {localizeMcpTransport(row.transportType, t)}
        </span>
      ),
      exportAccessor: (row) => row.transportType,
    },
    {
      key: 'allowed',
      header: t('mcpServers.list.columnAiUse'),
      width: '8%',
      responsivePriority: 3,
      render: (row) => (
        <span className="mcp-allowance-state" data-allowed={row.isAllowed}>
          <span aria-hidden="true" />
          {row.isAllowed ? t('mcpServers.list.allowedForAi') : t('mcpServers.list.blockedForAi')}
        </span>
      ),
      exportAccessor: (row) => row.isAllowed,
    },
    ...(anyServerHasTags ? [{
      key: 'tags' as const,
      header: t('mcpServers.list.columnTags'),
      width: '16%',
      responsivePriority: 3,
      render: (row: ServerRowData) =>
        row.serverTags.length > 0 ? (
          <span className="mcp-tags-text">{row.serverTags.join(', ')}</span>
        ) : null,
      exportAccessor: (row: ServerRowData) => row.serverTags.join(', '),
    }] : []),
  ]

  // ── Render ───────────────────────────────────────────────────────────────

  // 403 on the servers list query: render a forbidden EmptyState rather than
  // the regular page chrome — an empty table would otherwise
  // suggest the workspace simply has no servers, which is misleading.
  const workspaceError = serversError ?? policyError

  if (isForbiddenError(workspaceError)) {
    return (
      <div className="page">
        <PageHeader
          title={t('mcpServers.list.title')}
          description={t('mcpServers.list.subtitle')}
        />
        <EmptyState
          forbidden
          forbiddenContext={t('common.emptyState.forbiddenContext.mcpServers')}
        />
      </div>
    )
  }

  if (workspaceError && !isLoading) {
    return (
      <div className="page mcp-fleet-workspace">
        <PageHeader
          title={t('mcpServers.list.title')}
          description={t('mcpServers.list.subtitle')}
        />
        <WorkspaceUnavailable
          title={t('mcpServers.list.loadErrorTitle')}
          description={t('mcpServers.list.loadErrorDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.loading')}
          onRetry={handleRefresh}
          isRetrying={isFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('mcpServers.list.recoveryTitle'),
            steps: [
              t('mcpServers.list.recoveryConnection'),
              t('mcpServers.list.recoveryPermission'),
            ],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: getErrorMessage(workspaceError),
          }}
        />
      </div>
    )
  }

  return (
    <div className="page mcp-fleet-workspace">
      <PageHeader
        title={t('mcpServers.list.title')}
        description={t('mcpServers.list.subtitle')}
        actions={
          <>
            <RefreshButton onRefresh={handleRefresh} isFetching={isFetching} />
            {totalCount > 0 && (
              <OperationButton onClick={() => setRegisterModalOpen(true)}>
                {t('mcpServers.list.registerServer')}
              </OperationButton>
            )}
          </>
        }
      />
      {isLoading ? (
        <TableSkeleton rows={5} columns={4} />
      ) : totalCount === 0 ? (
        <section className="mcp-fleet-empty" aria-labelledby="mcp-fleet-empty-title">
          <div>
            <h2 id="mcp-fleet-empty-title">{t('mcpServers.empty')}</h2>
            <p>{t('nav.help.mcpServers')}</p>
          </div>
          <OperationButton onClick={() => setRegisterModalOpen(true)}>
            {t('mcpServers.registerButton')}
          </OperationButton>
        </section>
      ) : (
        <>
      <nav className="mcp-fleet-summary" aria-label={t('mcpServers.list.summaryLabel')}>
        <button type="button" aria-pressed={!statusFilter && !blockedOnly} onClick={() => setStatusFilterParam('')}>
          <span>{t('mcpServers.list.totalServers')}</span><strong>{totalCount}</strong>
        </button>
        <button type="button" aria-pressed={statusFilter === 'CONNECTED'} onClick={() => setStatusFilterParam('CONNECTED')}>
          <span>{t('mcpServers.list.connected')}</span><strong>{connectedCount}</strong>
        </button>
        <button type="button" aria-pressed={statusFilter === 'FAILED'} onClick={() => setStatusFilterParam('FAILED')}>
          <span>{t('mcpServers.list.failed')}</span><strong>{failedCount}</strong>
        </button>
        <button type="button" aria-pressed={blockedOnly} onClick={() => setBlockedFilterParam(!blockedOnly)}>
          <span>{t('mcpServers.list.blocked')}</span><strong>{blockedCount}</strong>
        </button>
      </nav>

      {/* Search + filter bar */}
      <div className="mcp-filter-bar">
        <div className="mcp-search-field">
          <Search size={16} aria-hidden="true" />
          <input
            type="text"
            placeholder={t('mcpServers.list.searchPlaceholder')}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            aria-label={t('mcpServers.list.searchPlaceholder')}
          />
          {searchInput ? (
            <button type="button" onClick={() => setSearchInput('')} aria-label={t('common.aria.clearSearch')}>
              <X size={16} aria-hidden="true" />
            </button>
          ) : null}
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilterParam(e.target.value as '' | 'CONNECTED' | 'DISCONNECTED' | 'FAILED' | 'ERROR' | 'PENDING')}
          aria-label={t('mcpServers.list.allStatus')}
        >
          <option value="">{t('mcpServers.list.allStatus')}</option>
          <option value="CONNECTED">{t('common.statuses.CONNECTED')}</option>
          <option value="DISCONNECTED">{t('common.statuses.DISCONNECTED')}</option>
          <option value="FAILED">{t('common.statuses.FAILED')}</option>
          <option value="ERROR">{t('common.statuses.ERROR')}</option>
          <option value="PENDING">{t('common.statuses.PENDING')}</option>
        </select>
        {allTags.length > 0 && (
          <select
            value={tagFilter}
            onChange={(e) => setTagFilterParam(e.target.value)}
            aria-label={t('mcpServers.list.allTags')}
          >
            <option value="">{t('mcpServers.list.allTags')}</option>
            {allTags.map((tag) => (
              <option key={tag} value={tag}>
                {tag}
              </option>
            ))}
          </select>
        )}
      </div>

      {filteredRows.length === 0 ? (
        <section className="mcp-fleet-empty mcp-fleet-empty--filtered" aria-labelledby="mcp-fleet-filtered-title">
          <div>
            <h2 id="mcp-fleet-filtered-title">{t('common.noResults')}</h2>
            <p>{t('mcpServers.list.noResultsDescription')}</p>
          </div>
        </section>
      ) : (
        <>
          <div className="detail-note" style={{ marginBottom: 'var(--space-2)' }}>
            {t('common.showingCount', { shown: filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).length, total: filteredRows.length })}
          </div>
          <DataTable
            columns={columns}
            data={filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)}
            keyFn={(row) => row.id}
            onRowClick={(row) => void navigate(`/mcp-servers/${encodeURIComponent(row.name)}`)}
            rowClassName={(row) => (!row.isAllowed ? 'mcp-blocked-row' : undefined)}
            sortKey={sortKey}
            sortDirection={sortDirection}
            onSort={handleSort}
            page={page}
            pageSize={PAGE_SIZE}
            totalCount={filteredRows.length}
            onPageChange={setPage}
            tableId="mcp-servers"
            urlStateKey="mcp-servers"
            exportable={{ filename: 'mcp-servers' }}
          />
        </>
      )}

      <details className="mcp-fleet-maintenance">
        <summary>{t('mcpServers.list.connectionActions')}</summary>
        <div className="mcp-fleet-maintenance__body">
          <p>{t('mcpServers.list.connectionActionsDescription')}</p>
          <div className="mcp-fleet-maintenance__actions">
            <OperationButton variant="secondary" onClick={() => setGlobalSettingsOpen(true)}>
              {t('mcpServers.list.globalSettings')}
            </OperationButton>
            <OperationButton
              variant="secondary"
              disabled={servers.filter((server) => server.status === 'DISCONNECTED' || server.status === 'FAILED').length === 0}
              onClick={() => setConfirmAction('connectAll')}
            >
              {t('mcpServers.list.connectAllDisconnected')}
            </OperationButton>
            <OperationButton
              variant="danger"
              disabled={servers.filter((server) => server.status === 'CONNECTED').length === 0}
              onClick={() => setConfirmAction('emergencyBlock')}
            >
              {t('mcpServers.list.emergencyBlockAll')}
            </OperationButton>
          </div>
        </div>
      </details>
        </>
      )}

      {/* Confirm dialogs */}
      {confirmAction === 'connectAll' && (
        <ConfirmDialog
          title={t('mcpServers.list.connectAllDisconnected')}
          message={t('mcpServers.confirm.connectAll')}
          onConfirm={() => {
            setConfirmAction(null)
            void handleConnectAllDisconnected()
          }}
          onCancel={() => setConfirmAction(null)}
        />
      )}
      {confirmAction === 'emergencyBlock' && (
        <ConfirmDialog
          title={t('mcpServers.list.emergencyBlockAll')}
          message={t('mcpServers.confirm.emergencyBlock')}
          onConfirm={() => {
            setConfirmAction(null)
            void handleEmergencyBlockAll()
          }}
          onCancel={() => setConfirmAction(null)}
          danger
        />
      )}

      {/* Modals */}
      <RegisterServerModal
        open={registerModalOpen}
        onClose={() => setRegisterModalOpen(false)}
      />
      <GlobalSettingsModal
        open={globalSettingsOpen}
        onClose={() => setGlobalSettingsOpen(false)}
        serverNames={servers.map((s) => s.name)}
      />
    </div>
  )
}

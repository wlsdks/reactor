import { useEffect, useRef, useState, type FormEvent } from 'react'
import { keepPreviousData, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  DataTable,
  EmptyState,
  PageHeader,
  RefreshButton,
  TableSkeleton,
  TimestampWithZone,
  Tooltip,
} from '../../../shared/ui'
import { WorkspaceUnavailable } from '../../../shared/ui/WorkspaceUnavailable'
import type { Column } from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useEscapeKey } from '../../../shared/lib/useEscapeKey'
import { usePageHelp } from '../../../shared/lib/usePageHelp'
import { AuditDetailPanel } from './AuditDetailPanel'
import { AuditRollbackModal } from './AuditRollbackModal'
import { deriveAuditEntryInsight } from '../auditOps'
import { useAuditLabelLocalizers } from './auditLabels'
import * as auditApi from '../api'
import type { AuditLogEntry, AuditPaginatedResponse } from '../types'
import './audit.css'

const PAGE_SIZE = 25
const AUDIT_CATEGORIES = [
  'platform_user',
  'approval',
  'mcp_server',
  'mcp_security',
  'tool_policy',
  'output_guard',
  'session',
] as const
const AUDIT_ACTIONS = ['CREATE', 'UPDATE', 'DELETE', 'APPROVE', 'REJECT', 'DISABLE', 'ROLE_UPDATE'] as const

function AuditRecoveryState({ ready, label }: { ready: boolean; label: string }) {
  return (
    <span className={`audit-recovery-state is-${ready ? 'ready' : 'review'}`}>
      <span className="audit-recovery-state__dot" aria-hidden="true" />
      {label}
    </span>
  )
}

function isAuditPage(value: unknown): value is AuditPaginatedResponse {
  return typeof value === 'object' && value !== null
    && Array.isArray((value as AuditPaginatedResponse).items)
    && typeof (value as AuditPaginatedResponse).total === 'number'
}

function getLastVerifiedAuditSnapshot(queryClient: QueryClient): { page: AuditPaginatedResponse; updatedAt: number } | null {
  let latest: { page: AuditPaginatedResponse; updatedAt: number } | null = null

  for (const query of queryClient.getQueryCache().findAll({ queryKey: queryKeys.audit.all() })) {
    if (!isAuditPage(query.state.data) || query.state.dataUpdatedAt === 0) continue
    if (latest === null || query.state.dataUpdatedAt > latest.updatedAt) {
      latest = { page: query.state.data, updatedAt: query.state.dataUpdatedAt }
    }
  }

  return latest
}

export function AuditLogManager() {
  const { t } = useTranslation()
  usePageHelp({ helpKey: 'auditPage.helpOverlay' })
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const { localizeCategory, localizeAction, localizeRollbackReadiness, localizeResource } = useAuditLabelLocalizers()
  const category = searchParams.get('category') ?? ''
  const action = searchParams.get('action') ?? ''
  const page = Math.max(1, Number(searchParams.get('page')) || 1)
  const offset = (page - 1) * PAGE_SIZE
  const [categoryInput, setCategoryInput] = useState(category)
  const [actionInput, setActionInput] = useState(action)
  const [selected, setSelected] = useState<AuditLogEntry | null>(null)
  const [rollbackTarget, setRollbackTarget] = useState<AuditLogEntry | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)

  const auditQuery = useQuery({
    queryKey: [...queryKeys.audit.list(category || undefined, action || undefined), offset, PAGE_SIZE],
    queryFn: () => auditApi.listAuditPage({
      category: category || undefined,
      action: action || undefined,
      offset,
      limit: PAGE_SIZE,
    }),
    placeholderData: keepPreviousData,
  })

  const lastVerifiedSnapshot = getLastVerifiedAuditSnapshot(queryClient)
  const visiblePage = auditQuery.data ?? (auditQuery.error ? lastVerifiedSnapshot?.page ?? null : null)
  const rows = visiblePage?.items ?? []
  const total = visiblePage?.total ?? 0
  const hasError = Boolean(auditQuery.error)
  const hasUnavailableSnapshot = hasError && visiblePage === null
  const isInitialLoading = auditQuery.isLoading && visiblePage === null
  const lastLoadedAt = auditQuery.dataUpdatedAt > 0 ? auditQuery.dataUpdatedAt : lastVerifiedSnapshot?.updatedAt ?? null
  const effectiveSelected = selected && rows.some((row) => row.id === selected.id) ? selected : null
  useEscapeKey(Boolean(effectiveSelected), () => setSelected(null))

  useEffect(() => {
    if (!effectiveSelected || typeof window.matchMedia !== 'function' || !window.matchMedia('(max-width: 900px)').matches) return

    detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [effectiveSelected])

  function applyFilters(event: FormEvent) {
    event.preventDefault()
    const next = new URLSearchParams(searchParams)
    const nextCategory = categoryInput.trim()
    const nextAction = actionInput.trim()
    if (nextCategory) next.set('category', nextCategory)
    else next.delete('category')
    if (nextAction) next.set('action', nextAction)
    else next.delete('action')
    next.delete('page')
    setSearchParams(next, { replace: true })
    setSelected(null)
  }

  function clearFilters() {
    setCategoryInput('')
    setActionInput('')
    setSearchParams({}, { replace: true })
    setSelected(null)
  }

  function changePage(nextPage: number) {
    const next = new URLSearchParams(searchParams)
    if (nextPage === 1) next.delete('page')
    else next.set('page', String(nextPage))
    setSearchParams(next, { replace: true })
    setSelected(null)
  }

  function refreshAudit() {
    return auditQuery.refetch()
  }

  const ledgerColumns: Column<AuditLogEntry>[] = [
    {
      key: 'category', header: t('auditPage.category'), width: effectiveSelected ? '34%' : '18%', responsivePriority: 1,
      render: (row) => <Tooltip content={row.category}><span>{localizeCategory(row.category)}</span></Tooltip>,
    },
    {
      key: 'action', header: t('auditPage.action'), width: effectiveSelected ? '28%' : '14%', responsivePriority: 1,
      render: (row) => <Tooltip content={row.action}><span>{localizeAction(row.action)}</span></Tooltip>,
    },
    {
      key: 'actor', header: t('auditPage.actor'), width: '18%', responsivePriority: 3,
      render: (row) => <Tooltip content={row.actorEmail ?? row.actor}><span className="text-truncate">{row.actorEmail ?? row.actor}</span></Tooltip>,
    },
    {
      key: 'resource', header: t('auditPage.resource'), width: '25%', responsivePriority: 3,
      render: (row) => <Tooltip content={[row.resourceType, row.resourceId].filter(Boolean).join(' · ')}><span className="text-truncate">{localizeResource(row)}</span></Tooltip>,
    },
    {
      key: 'rollback', header: t('auditPage.rollbackReady'), width: '12%', responsivePriority: 3,
      render: (row) => {
        const ready = deriveAuditEntryInsight(row).rollbackReady
        return <AuditRecoveryState ready={ready} label={localizeRollbackReadiness(ready ? 'READY' : 'WARN')} />
      },
    },
    {
      key: 'createdAt', header: t('auditPage.created'), width: effectiveSelected ? '38%' : '13%', responsivePriority: 3,
      render: (row) => <span className="data-mono">{formatDateTime(row.createdAt)}</span>,
    },
  ]
  const columns = effectiveSelected
    ? ledgerColumns.filter((column) => ['category', 'action', 'createdAt'].includes(String(column.key)))
    : ledgerColumns

  return (
    <div className="page audit-workspace">
      <PageHeader
        title={t('nav.audit')}
        description={t('nav.help.audit')}
        actions={!hasError ? <RefreshButton onRefresh={() => void refreshAudit()} isFetching={auditQuery.isFetching} /> : undefined}
      />

      {hasUnavailableSnapshot ? (
        <WorkspaceUnavailable
          title={t('auditPage.unavailableTitle')}
          description={t('auditPage.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refreshAudit}
          isRetrying={auditQuery.isFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('auditPage.recoveryGuideTitle'),
            steps: [
              t('auditPage.recoveryCheckAccount'),
              t('auditPage.recoveryCheckConnection'),
              t('auditPage.recoveryRetry'),
            ],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: getErrorMessage(auditQuery.error),
          }}
        />
      ) : isInitialLoading ? (
        <TableSkeleton />
      ) : (
        <>
          <div className="audit-sync-line">
            <span>{t('auditPage.showingRows', { shown: rows.length, total })}</span>
            <span>{lastLoadedAt ? <>{t('auditPage.lastSyncLabel')}: <TimestampWithZone value={lastLoadedAt} /></> : t('auditPage.lastSyncUnknown')}</span>
          </div>

          <form className="audit-filter-bar" onSubmit={applyFilters}>
            <label>
              <span>{t('auditPage.category')}</span>
              <select value={categoryInput} onChange={(event) => setCategoryInput(event.target.value)}>
                <option value="">{t('auditPage.categoryAll')}</option>
                {!AUDIT_CATEGORIES.includes(categoryInput as typeof AUDIT_CATEGORIES[number]) && categoryInput && (
                  <option value={categoryInput}>{localizeCategory(categoryInput)}</option>
                )}
                {AUDIT_CATEGORIES.map((value) => <option key={value} value={value}>{localizeCategory(value)}</option>)}
              </select>
            </label>
            <label>
              <span>{t('auditPage.action')}</span>
              <select value={actionInput} onChange={(event) => setActionInput(event.target.value)}>
                <option value="">{t('auditPage.actionAll')}</option>
                {!AUDIT_ACTIONS.includes(actionInput as typeof AUDIT_ACTIONS[number]) && actionInput && (
                  <option value={actionInput}>{localizeAction(actionInput)}</option>
                )}
                {AUDIT_ACTIONS.map((value) => <option key={value} value={value}>{localizeAction(value)}</option>)}
              </select>
            </label>
            <button type="submit" className="btn btn-primary">{t('common.apply')}</button>
            {(category || action) && <button type="button" className="btn btn-secondary" onClick={clearFilters}>{t('common.reset')}</button>}
          </form>

          {hasError ? (
            <div className="audit-revalidation" role="status">
              <div><strong>{t('auditPage.revalidationTitle')}</strong><span>{t('auditPage.revalidationDescription')}</span></div>
              <button className="btn btn-secondary btn-sm" type="button" onClick={() => void refreshAudit()} disabled={auditQuery.isFetching}>
                {auditQuery.isFetching ? t('common.retrying') : t('common.retry')}
              </button>
            </div>
          ) : null}

          <div className={`audit-ledger-layout${effectiveSelected ? ' audit-ledger-layout--detail' : ''}`}>
            <section className="audit-ledger" aria-label={t('auditPage.historyTitle')}>
              {!hasError && rows.length === 0 && (
                <EmptyState message={category || action ? t('auditPage.filteredEmpty') : t('auditPage.empty')} filtered={Boolean(category || action)} filterSummary={[category, action].filter(Boolean).join(' · ')} onClearFilters={category || action ? clearFilters : undefined} />
              )}
              {rows.length > 0 && (
                <DataTable columns={columns} data={rows} keyFn={(row) => row.id} onRowClick={setSelected} selectedKey={effectiveSelected?.id ?? null} page={page} pageSize={PAGE_SIZE} totalCount={total} onPageChange={changePage} tableId="audit-log" exportable={{ filename: 'audit-log' }} />
              )}
            </section>

            {effectiveSelected && (
              <div ref={detailRef} tabIndex={-1}>
                <AuditDetailPanel effectiveSelected={effectiveSelected} onClose={() => setSelected(null)} onRollbackTarget={setRollbackTarget} />
              </div>
            )}
          </div>
        </>
      )}

      <AuditRollbackModal open={Boolean(rollbackTarget)} entry={rollbackTarget} onClose={() => setRollbackTarget(null)} onSuccess={() => void queryClient.invalidateQueries({ queryKey: queryKeys.audit.all() })} />
    </div>
  )
}

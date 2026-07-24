import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import {
  DataTable,
  EmptyState,
  TableSkeleton,
  Tooltip,
  type BulkAction,
  type Column,
  type RowAction,
} from '../../../shared/ui'
import { copyToClipboard } from '../../../shared/lib/clipboard'
import { downloadFile } from '../../../shared/lib/downloadFile'
import { formatISODate } from '../../../shared/lib/formatters'
import type { FeedbackEntry, FeedbackReviewStatus } from '../types'
import { useLabelLocalizers } from './feedbackLabels'
import {
  feedbackCanClose,
  feedbackEvalLifecycleStage,
  type FeedbackEvalLifecycleStage,
} from '../feedbackEvalLifecycle'

function evalStageLabel(stage: FeedbackEvalLifecycleStage, t: TFunction): string {
  if (stage === 'blocked') return t('feedbackPage.evalLifecycle.stage.blocked')
  if (stage === 'ready') return t('feedbackPage.evalLifecycle.stage.ready')
  if (stage === 'sync_pending') return t('feedbackPage.evalLifecycle.stage.sync_pending')
  if (stage === 'closed') return t('feedbackPage.evalLifecycle.stage.closed')
  return t('feedbackPage.evalLifecycle.stage.not_required')
}

function useIsNarrowFeedbackTable(): boolean {
  const [isNarrow, setIsNarrow] = useState(() => typeof window !== 'undefined' && window.innerWidth <= 700)

  useEffect(() => {
    const update = () => setIsNarrow(window.innerWidth <= 700)
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])

  return isNarrow
}

export interface FeedbackTableSectionProps {
  isLoading: boolean
  items: FeedbackEntry[]
  pagedItems: FeedbackEntry[]
  sortedItemsLength: number
  selectedId: string | null
  onSelect: (id: string) => void
  onDelete: (entry: FeedbackEntry) => void
  page: number
  pageSize: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
  sortKey: string | null
  sortDirection: 'asc' | 'desc' | null
  onSort: (key: string, dir: 'asc' | 'desc' | null) => void
  // Filter state — used to render the empty state with a "Clear filters" CTA.
  ratingFilter: string
  statusFilter: string
  hasCommentFilter: '' | 'yes' | 'no'
  qFilter: string
  fromFilter: string
  toFilter: string
  onClearFilters: () => void
  // Bulk mutations are wired by the parent so this section stays presentational.
  onBulkUpdateReview: (ids: string[], status: FeedbackReviewStatus) => Promise<void>
  onBulkDelete: (ids: string[]) => Promise<void>
}

export function FeedbackTableSection({
  isLoading,
  items,
  pagedItems,
  sortedItemsLength,
  selectedId,
  onSelect,
  onDelete,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  sortKey,
  sortDirection,
  onSort,
  ratingFilter,
  statusFilter,
  hasCommentFilter,
  qFilter,
  fromFilter,
  toFilter,
  onClearFilters,
  onBulkUpdateReview,
  onBulkDelete,
}: FeedbackTableSectionProps) {
  const { t } = useTranslation()
  const { localizeRating, localizeStatus, localizeSystemTag, localizeDomain, localizeIntent } = useLabelLocalizers()
  const isNarrowTable = useIsNarrowFeedbackTable()

  const lifecycleStateClass = (stage: FeedbackEvalLifecycleStage): string => {
    if (stage === 'blocked') return 'is-error'
    if (stage === 'ready' || stage === 'sync_pending') return 'is-warning'
    if (stage === 'closed') return 'is-success'
    return 'is-neutral'
  }

  if (isLoading) {
    return <TableSkeleton />
  }

  if (items.length === 0) {
    // Detect any active filter so the empty state can offer "Clear filters"
    // rather than the generic "no data" message.
    const filterParts: string[] = []
    if (ratingFilter) filterParts.push(`${t('feedbackPage.columns.rating')}: ${ratingFilter}`)
    if (statusFilter) filterParts.push(`${t('feedbackPage.columns.status')}: ${statusFilter}`)
    if (hasCommentFilter) {
      filterParts.push(`${t('feedbackPage.filters.hasComment')}: ${hasCommentFilter === 'yes' ? t('feedbackPage.filters.commentYes') : t('feedbackPage.filters.commentNo')}`)
    }
    if (qFilter.trim()) filterParts.push(`${t('feedbackPage.filters.search')}: ${qFilter.trim()}`)
    if (fromFilter) filterParts.push(`${t('feedbackPage.filters.from')}: ${fromFilter}`)
    if (toFilter) filterParts.push(`${t('feedbackPage.filters.to')}: ${toFilter}`)
    const isFiltered = filterParts.length > 0
    return (
      <div className="detail-panel detail-panel--compact detail-panel-empty">
        {isFiltered ? (
          <EmptyState
            filtered
            filterSummary={filterParts.join(' · ')}
            onClearFilters={onClearFilters}
          />
        ) : (
          <section className="fb-empty" aria-label={t('feedbackPage.emptyTitle')}>
            <h2>{t('feedbackPage.emptyTitle')}</h2>
            <p>{t('feedbackPage.emptyDesc')}</p>
          </section>
        )}
      </div>
    )
  }

  const columns: Column<FeedbackEntry>[] = [
    {
      key: 'rating',
      header: t('feedbackPage.columns.rating'),
      width: '9%',
      sortable: true,
      responsivePriority: 2,
      render: (row) => (
        <span className={`feedback-table__state ${row.rating === 'thumbs_up' ? 'is-success' : 'is-error'}`}>
          <span aria-hidden="true" />
          {localizeRating(row.rating)}
        </span>
      ),
    },
    {
      key: 'reviewStatus',
      header: t('feedbackPage.columns.status'),
      width: '9%',
      sortable: true,
      responsivePriority: 2,
      render: (row) => (
        <span className={`feedback-table__state ${row.reviewStatus === 'done' ? 'is-success' : 'is-warning'}`}>
          <span aria-hidden="true" />
          {localizeStatus(row.reviewStatus)}
        </span>
      ),
    },
    {
      key: 'evalLifecycle',
      header: t('feedbackPage.evalLifecycle.column'),
      width: '12%',
      responsivePriority: 2,
      render: (row) => {
        const stage = feedbackEvalLifecycleStage(row)
        if (stage === 'not_required') return <span className="text-dim">-</span>
        return <span className={`feedback-table__state ${lifecycleStateClass(stage)}`}><span aria-hidden="true" />{evalStageLabel(stage, t)}</span>
      },
    },
    {
      key: 'query',
      header: t('feedbackPage.columns.query'),
      width: isNarrowTable ? '100%' : '24%',
      responsivePriority: 1,
      render: (row) => {
        const stage = feedbackEvalLifecycleStage(row)
        return row.query ? (
          <Tooltip content={row.query}>
            <span className="feedback-table__query">
              <span className="text-truncate">{row.query}</span>
              <span className="feedback-table__mobile-meta">
                {localizeRating(row.rating)} · {localizeStatus(row.reviewStatus)}
                {stage !== 'not_required' ? ` · ${evalStageLabel(stage, t)}` : ''}
              </span>
            </span>
          </Tooltip>
        ) : (
          <span className="text-truncate">{row.query}</span>
        )
      },
    },
    {
      key: 'domain',
      header: t('feedbackPage.columns.domain'),
      width: '10%',
      responsivePriority: 3,
      render: (row) => row.domain ? <span>{localizeDomain(row.domain)}</span> : <span className="text-dim">-</span>,
    },
    {
      key: 'intent',
      header: t('feedbackPage.columns.intent'),
      width: '10%',
      responsivePriority: 3,
      render: (row) => row.intent ? <span>{localizeIntent(row.intent)}</span> : <span className="text-dim">-</span>,
    },
    {
      key: 'reviewTags',
      header: t('feedbackPage.columns.tags'),
      width: '14%',
      responsivePriority: 3,
      render: (row) => row.reviewTags.length > 0 ? (
        <span className="feedback-table__tags">
          {row.reviewTags.map(localizeSystemTag).join(', ')}
        </span>
      ) : <span className="text-dim">-</span>,
    },
    {
      key: 'createdAt',
      header: t('feedbackPage.columns.created'),
      width: '14%',
      sortable: true,
      responsivePriority: 2,
      render: (row) => <span className="text-dim">{formatISODate(row.timestamp)}</span>,
    },
  ]
  const visibleColumns = isNarrowTable
    ? columns.filter((column) => column.key === 'query')
    : columns

  const rowActions: RowAction<FeedbackEntry>[] = [
    {
      id: 'copy-id',
      label: t('common.rowActions.copyId'),
      perform: (row) => {
        void copyToClipboard(row.feedbackId, { label: 'ID' })
      },
    },
    {
      id: 'open-detail',
      label: t('common.rowActions.openDetail'),
      perform: (row) => onSelect(row.feedbackId),
    },
    {
      id: 'delete',
      label: t('common.rowActions.delete'),
      destructive: true,
      disabled: (row) => !feedbackCanClose(row),
      perform: (row) => onDelete(row),
    },
  ]

  const bulkActions: BulkAction<FeedbackEntry>[] = [
    {
      id: 'mark-done',
      label: t('feedbackPage.bulk.markDone'),
      variant: 'primary',
      hidden: (rows) => rows.some((row) => !feedbackCanClose(row)),
      perform: async (rows) => {
        await onBulkUpdateReview(rows.map(r => r.feedbackId), 'done')
      },
    },
    {
      id: 'mark-done-blocked',
      label: t('feedbackPage.evalLifecycle.bulkCloseBlocked'),
      variant: 'secondary',
      hidden: (rows) => rows.every(feedbackCanClose),
      disabled: () => true,
      perform: () => {},
    },
    {
      id: 'mark-inbox',
      label: t('feedbackPage.bulk.markInbox'),
      variant: 'secondary',
      perform: async (rows) => {
        await onBulkUpdateReview(rows.map(r => r.feedbackId), 'inbox')
      },
    },
    {
      id: 'export-csv',
      label: t('feedbackPage.bulk.exportCsv'),
      variant: 'secondary',
      perform: (rows) => {
        const header = ['feedbackId', 'rating', 'reviewStatus', 'query', 'response', 'comment', 'timestamp']
        const escape = (v: unknown) =>
          v == null ? '' : `"${String(v).replace(/"/g, '""')}"`
        const csv = [
          header.join(','),
          ...rows.map(r => [
            r.feedbackId,
            r.rating,
            r.reviewStatus,
            r.query,
            r.response,
            r.comment ?? '',
            r.timestamp,
          ].map(escape).join(',')),
        ].join('\n')
        downloadFile(
          csv,
          `feedback-bulk-${new Date().toISOString().slice(0, 10)}.csv`,
        )
      },
    },
    {
      id: 'mark-delete',
      label: t('feedbackPage.bulk.markDelete'),
      variant: 'danger',
      hidden: (rows) => rows.some((row) => !feedbackCanClose(row)),
      confirmMessage: (rows) =>
        t('feedbackPage.bulk.deleteConfirm', { count: rows.length }),
      perform: async (rows) => {
        await onBulkDelete(rows.map(r => r.feedbackId))
      },
    },
    {
      id: 'mark-delete-blocked',
      label: t('feedbackPage.evalLifecycle.bulkDeleteBlocked'),
      variant: 'secondary',
      hidden: (rows) => rows.every(feedbackCanClose),
      disabled: () => true,
      perform: () => {},
    },
  ]

  return (
    <div className="feedback-table">
      <DataTable<FeedbackEntry>
        columns={visibleColumns}
        data={pagedItems}
        keyFn={(row) => row.feedbackId}
        onRowClick={(row) => onSelect(row.feedbackId)}
        selectedKey={selectedId}
        page={page}
        pageSize={pageSize}
        totalCount={sortedItemsLength}
        onPageChange={onPageChange}
        sortKey={sortKey}
        sortDirection={sortDirection}
        onSort={onSort}
        pageSizeOptions={[10, 25, 50, 100]}
        defaultPageSize={25}
        onPageSizeChange={onPageSizeChange}
        tableId="feedback"
        urlStateKey="feedback"
        exportable={{
          filename: 'feedback',
          columns: [
            { key: 'feedbackId', header: 'feedbackId', accessor: r => r.feedbackId },
            { key: 'rating', header: 'rating', accessor: r => r.rating },
            { key: 'reviewStatus', header: 'reviewStatus', accessor: r => r.reviewStatus },
            { key: 'query', header: 'query', accessor: r => r.query },
            { key: 'response', header: 'response', accessor: r => r.response },
            { key: 'comment', header: 'comment', accessor: r => r.comment ?? null },
            { key: 'domain', header: 'domain', accessor: r => r.domain ?? null },
            { key: 'intent', header: 'intent', accessor: r => r.intent ?? null },
            { key: 'reviewTags', header: 'reviewTags', accessor: r => r.reviewTags.join('|') },
            { key: 'timestamp', header: 'timestamp', accessor: r => r.timestamp ?? null },
          ],
        }}
        rowActions={rowActions}
        selectable
        bulkActions={bulkActions}
      />
    </div>
  )
}

import './feedback.css'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  ConfirmDialog,
  LoadingSpinner,
  PageHeader,
  SavedViewsControl,
} from '../../../shared/ui'
import { applyScopedParams, extractScopedParams } from '../../../shared/lib/useUrlState'
import { downloadFile } from '../../../shared/lib/downloadFile'
import { useEscapeKey } from '../../../shared/lib/useEscapeKey'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { usePageHelp } from '../../../shared/lib/usePageHelp'
import * as feedbackApi from '../api'
import type {
  FeedbackEntry,
  FeedbackRating,
  FeedbackReviewStatus,
} from '../types'
import { FeedbackStatsPanel } from './FeedbackStatsPanel'
import { FeedbackToolbar } from './FeedbackToolbar'
import { FeedbackTableSection } from './FeedbackTableSection'
import { FeedbackDetailDrawer } from './FeedbackDetailDrawer'
import { FeedbackEvalPromotionPanel } from './FeedbackEvalPromotionPanel'
import { filterFeedbackItems } from '../feedbackFilters'

export function FeedbackManager() {
  const { t } = useTranslation()
  void t('feedbackPage.helpOverlay', { returnObjects: true })
  usePageHelp({ helpKey: 'feedbackPage.helpOverlay' })
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const [searchParams, setSearchParams] = useSearchParams()

  // ── Filter state ──
  const [ratingFilter, setRatingFilter] = useState<'' | FeedbackRating>('')
  const [statusFilter, setStatusFilter] = useState<'' | FeedbackReviewStatus>('')
  const [tagFilter] = useState('')
  const [qFilter, setQFilter] = useState('')
  const [hasCommentFilter, setHasCommentFilter] = useState<'' | 'yes' | 'no'>('')
  const [fromFilter, setFromFilter] = useState('')
  const [toFilter, setToFilter] = useState('')

  // ── Selection/detail ──
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<FeedbackEntry | null>(null)
  const [exporting, setExporting] = useState(false)

  // ── Pagination / sort (URL-synced via DataTable's `urlStateKey`) ──
  // Page size is operator-controllable via the DataTable selector; the
  // initial 25 matches the previous hardcoded constant and is overridden by
  // any URL `feedback_ps` or localStorage value at mount.
  const [pageSize, setPageSize] = useState(25)
  const [page, setPage] = useState(1)
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc' | null>(null)

  const filterParams = {
    rating: ratingFilter || undefined,
    status: statusFilter || undefined,
    tag: tagFilter || undefined,
    q: qFilter.trim().length >= 2 ? qFilter.trim() : undefined,
    hasComment: hasCommentFilter === 'yes' ? true : hasCommentFilter === 'no' ? false : undefined,
    from: fromFilter ? `${fromFilter}T00:00:00Z` : undefined,
    to: toFilter ? `${toFilter}T23:59:59Z` : undefined,
    limit: 50,
  }

  const listQuery = useQuery({
    queryKey: queryKeys.feedback.list(filterParams),
    queryFn: () => feedbackApi.listFeedback(filterParams),
  })

  const unreviewedQuery = useQuery({
    queryKey: queryKeys.feedback.unreviewedCount(),
    queryFn: feedbackApi.fetchUnreviewedCount,
  })

  const detailQuery = useQuery({
    queryKey: queryKeys.feedback.detail(selectedId ?? ''),
    queryFn: () => feedbackApi.getFeedback(selectedId!),
    enabled: !!selectedId,
  })

  const selected = detailQuery.data ?? null
  const sourceItems = listQuery.data?.items ?? []
  const items = filterFeedbackItems(sourceItems, {
    q: filterParams.q,
    hasComment: filterParams.hasComment,
    from: filterParams.from,
    to: filterParams.to,
  })
  const hasClientFilters = Boolean(
    filterParams.q
    || filterParams.hasComment !== undefined
    || filterParams.from
    || filterParams.to,
  )
  const total = hasClientFilters ? items.length : (listQuery.data?.approximateTotal ?? 0)
  const errorMsg = listQuery.error ? getErrorMessage(listQuery.error) : null

  // Client-side sort + page slice. The sort runs over the current page from
  // the server (limit: 50) — sufficient for a quick scan and shareable URL
  // state, while heavier server-side ordering can be layered on later.
  // Column-key → data-field map: keeps URL keys stable when a column header's
  // underlying property name diverges (e.g. `createdAt` URL key → `timestamp`).
  const SORT_FIELD: Record<string, keyof FeedbackEntry> = {
    rating: 'rating',
    reviewStatus: 'reviewStatus',
    createdAt: 'timestamp',
  }
  const sortedItems = sortKey && sortDirection && SORT_FIELD[sortKey]
    ? [...items].sort((a, b) => {
        const field = SORT_FIELD[sortKey]
        const aVal = a[field] ?? ''
        const bVal = b[field] ?? ''
        if (aVal === bVal) return 0
        const cmp = String(aVal) > String(bVal) ? 1 : -1
        return sortDirection === 'asc' ? cmp : -cmp
      })
    : items
  const pagedItems = sortedItems.slice((page - 1) * pageSize, page * pageSize)

  // ── Mutations ──
  const deleteMutation = useMutation({
    mutationFn: (id: string) => feedbackApi.deleteFeedback(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.feedback.all() })
      if (selectedId === deleteTarget?.feedbackId) setSelectedId(null)
      addToast({ type: 'success', message: t('common.toast.deleted') })
      setDeleteTarget(null)
    },
    onError: (err) => {
      addToast({ type: 'error', message: getErrorMessage(err) })
      setDeleteTarget(null)
    },
  })

  const bulkMutation = useMutation({
    mutationFn: ({
      ids,
      status,
    }: { ids: string[]; status: FeedbackReviewStatus }) =>
      feedbackApi.bulkUpdateReview({ ids, status, tagMode: 'add' }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.feedback.all() })
      addToast({
        type: 'success',
        message: t('feedbackPage.bulk.result', {
          updated: result.updated.length,
          failed: result.failed.length,
        }),
      })
    },
    onError: (err) => addToast({ type: 'error', message: getErrorMessage(err) }),
  })

  const bulkDeleteMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      // No backend bulk-delete endpoint — surface the action via the existing
      // single-delete primitive in parallel. Failures are aggregated below.
      const results = await Promise.allSettled(ids.map(id => feedbackApi.deleteFeedback(id)))
      const failed = results.filter(r => r.status === 'rejected').length
      return { ok: results.length - failed, failed }
    },
    onSuccess: (result) => {
      // `feedback.all()` covers list/detail/stats/unreviewedCount via the
      // `['feedback']` prefix (TanStack Query partialMatchKey). Also poke
      // unreviewedCount explicitly so a later narrowing of `feedback.all()`
      // (e.g. scoping it to just the list cache) cannot silently leave the
      // header counter and stats panel stale after a bulk delete.
      queryClient.invalidateQueries({ queryKey: queryKeys.feedback.all() })
      queryClient.invalidateQueries({ queryKey: queryKeys.feedback.unreviewedCount() })
      addToast({
        type: result.failed === 0 ? 'success' : 'warning',
        message: t('feedbackPage.bulk.result', {
          updated: result.ok,
          failed: result.failed,
        }),
      })
    },
    onError: (err) => addToast({ type: 'error', message: getErrorMessage(err) }),
  })

  useEscapeKey(!!selectedId && !deleteTarget, () => setSelectedId(null))

  async function handleExport() {
    setExporting(true)
    try {
      const data = await feedbackApi.exportFeedback()
      const filename = `feedback-export-${new Date().toISOString().replace(/[:.]/g, '-')}.json`
      downloadFile(JSON.stringify(data, null, 2), filename)
    } catch (e) {
      addToast({ type: 'error', message: getErrorMessage(e) })
    } finally {
      setExporting(false)
    }
  }

  async function handleBulkUpdateReview(ids: string[], status: FeedbackReviewStatus) {
    await bulkMutation.mutateAsync({ ids, status })
  }

  async function handleBulkDelete(ids: string[]) {
    await bulkDeleteMutation.mutateAsync(ids)
  }

  function handleClearFilters() {
    setRatingFilter('')
    setStatusFilter('')
    setHasCommentFilter('')
    setQFilter('')
    setFromFilter('')
    setToFilter('')
    setPage(1)
  }

  return (
    <div className="page">
      <PageHeader
        title={t('nav.feedback')}
        description={
          <p className="page-subtitle">
            {t('nav.help.feedback')}
            {unreviewedQuery.data && unreviewedQuery.data.count > 0 && (
              <> · <span className="feedback-page__unreviewed">
                {t('feedbackPage.unreviewedBadge', { count: unreviewedQuery.data.count })}
              </span></>
            )}
          </p>
        }
        actions={
          <>
            <SavedViewsControl
              scope="feedback"
              currentParams={extractScopedParams(searchParams, 'feedback')}
              onApply={(params) => setSearchParams(applyScopedParams(searchParams, 'feedback', params), { replace: true })}
            />
            <button
              className="btn btn-secondary"
              onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.feedback.all() })}
            >
              {t('common.refresh')}
            </button>
            <button className="btn btn-secondary" onClick={handleExport} disabled={exporting}>
              {exporting ? <LoadingSpinner size="sm" /> : t('feedbackPage.export')}
            </button>
          </>
        }
      />

      <FeedbackStatsPanel from={filterParams.from} to={filterParams.to} />

      <FeedbackToolbar
        qFilter={qFilter}
        onQFilterChange={setQFilter}
        ratingFilter={ratingFilter}
        onRatingFilterChange={setRatingFilter}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        hasCommentFilter={hasCommentFilter}
        onHasCommentFilterChange={setHasCommentFilter}
        fromFilter={fromFilter}
        onFromFilterChange={setFromFilter}
        toFilter={toFilter}
        onToFilterChange={setToFilter}
        shown={items.length}
        total={total}
      />

      {errorMsg && (
        <div className="alert alert-error">{errorMsg}</div>
      )}

      {!errorMsg && <div className={`split-layout ${selectedId ? '' : 'split-layout--collapsed'}`}>
        <div className="split-left">
          <FeedbackTableSection
            isLoading={listQuery.isLoading}
            items={items}
            pagedItems={pagedItems}
            sortedItemsLength={sortedItems.length}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onDelete={setDeleteTarget}
            page={page}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
            sortKey={sortKey}
            sortDirection={sortDirection}
            onSort={(key, dir) => { setSortKey(dir ? key : null); setSortDirection(dir) }}
            ratingFilter={ratingFilter}
            statusFilter={statusFilter}
            hasCommentFilter={hasCommentFilter}
            qFilter={qFilter}
            fromFilter={fromFilter}
            toFilter={toFilter}
            onClearFilters={handleClearFilters}
            onBulkUpdateReview={handleBulkUpdateReview}
            onBulkDelete={handleBulkDelete}
          />
        </div>

        {selectedId && (
          <div className="split-right">
            <FeedbackDetailDrawer
              isLoading={detailQuery.isLoading}
              selected={selected}
              onClose={() => setSelectedId(null)}
              onDelete={setDeleteTarget}
            />
          </div>
        )}
      </div>}

      <FeedbackEvalPromotionPanel from={filterParams.from} to={filterParams.to} />

      {deleteTarget && (
        <ConfirmDialog
          title={t('feedbackPage.deleteTitle')}
          message={t('feedbackPage.deleteMessage', { id: deleteTarget.feedbackId })}
          onConfirm={() => deleteMutation.mutate(deleteTarget.feedbackId)}
          onCancel={() => setDeleteTarget(null)}
          danger
        />
      )}
    </div>
  )
}

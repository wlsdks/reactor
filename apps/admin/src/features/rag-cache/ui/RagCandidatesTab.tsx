import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog, SkeletonTable, useAnnouncer } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useUrlState } from '../../../shared/lib/useUrlState'
import { useTableExport } from '../../../shared/lib/useTableExport'
import { useToastStore } from '../../../shared/store/toast.store'
import * as ragCacheApi from '../api'
import type { BulkCandidateActionResult } from '../api'
import type { RagCandidate } from '../types'
import { RagCandidateDetailDrawer } from './RagCandidateDetailDrawer'
import { RagCandidatesBulkBar, type BulkAction } from './RagCandidatesBulkBar'
import { RagCandidatesTable } from './RagCandidatesTable'
import { RagCandidatesToolbar } from './RagCandidatesToolbar'
import type { StatusFilter } from './ragCandidatesUtils'
import { useRagCandidatesSelection } from './useRagCandidatesSelection'

export function RagCandidatesTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { announce } = useAnnouncer()
  // Mirror the status filter to the URL under the `rag-candidates` scope so
  // saved views can capture it. `s` keeps URL keys terse and consistent with
  // DataTable-managed slices on neighbouring pages.
  const [urlState, setUrlState] = useUrlState(
    { s: 'ALL' as string },
    { prefix: 'rag-candidates' },
  )
  const statusFilter = (urlState.s as StatusFilter) ?? 'ALL'
  function setStatusFilter(next: StatusFilter) {
    setUrlState({ s: next === 'ALL' ? undefined : next })
  }
  const [selected, setSelected] = useState<RagCandidate | null>(null)
  const [confirmAction, setConfirmAction] = useState<'approve' | 'reject' | null>(null)
  const [bulkConfirm, setBulkConfirm] = useState<BulkAction | null>(null)

  const filters = statusFilter === 'ALL' ? {} : { status: statusFilter }

  const { data = [], isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.ragCache.candidates(filters),
    queryFn: () => ragCacheApi.listRagCandidates(filters),
  })

  const selection = useRagCandidatesSelection(data)
  const { selectedIds, clearSelection } = selection
  const selectedCount = selectedIds.size

  const approveMutation = useMutation({
    mutationFn: (id: string) => ragCacheApi.approveRagCandidate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ragCache.candidatesRoot() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      setSelected(null)
    },
    onError: (err: Error) => {
      useToastStore.getState().addToast({ type: 'error', message: err.message })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: (id: string) => ragCacheApi.rejectRagCandidate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ragCache.candidatesRoot() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      setSelected(null)
    },
    onError: (err: Error) => {
      useToastStore.getState().addToast({ type: 'error', message: err.message })
    },
  })

  const bulkMutation = useMutation({
    mutationFn: async ({
      action,
      ids,
    }: {
      action: BulkAction
      ids: string[]
    }): Promise<BulkCandidateActionResult> => {
      if (action === 'approve') {
        return ragCacheApi.bulkApproveRagCandidates(ids)
      }
      return ragCacheApi.bulkRejectRagCandidates(ids)
    },
    onSuccess: (result, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ragCache.candidatesRoot() })
      const total = variables.ids.length
      const successCount = result.succeeded.length
      const failCount = result.failed.length
      const toast = useToastStore.getState()
      const resultKey = variables.action === 'approve'
        ? 'common.a11y.bulkApproveResult'
        : 'common.a11y.bulkRejectResult'
      if (failCount === 0) {
        toast.addToast({
          type: 'success',
          message: t('ragCachePage.candidates.bulkSuccess', {
            count: successCount,
            action: t(`ragCachePage.candidates.${variables.action}`),
          }),
        })
        announce(t(resultKey, { succeeded: successCount, total }))
      } else if (successCount === 0) {
        toast.addToast({
          type: 'error',
          message: t('ragCachePage.candidates.bulkAllFailed', { count: failCount }),
        })
        announce(
          t('common.a11y.bulkPartialFailure', { succeeded: 0, failed: failCount }),
          { priority: 'assertive' },
        )
      } else {
        toast.addToast({
          type: 'warning',
          message: t('ragCachePage.candidates.bulkPartial', {
            success: successCount,
            failed: failCount,
            total,
          }),
        })
        announce(
          t('common.a11y.bulkPartialFailure', { succeeded: successCount, failed: failCount }),
          { priority: 'assertive' },
        )
      }
      clearSelection()
    },
    onError: (err: Error) => {
      useToastStore.getState().addToast({ type: 'error', message: err.message })
    },
  })

  function handleApprove() {
    if (selected) approveMutation.mutate(selected.id)
    setConfirmAction(null)
  }

  function handleReject() {
    if (selected) rejectMutation.mutate(selected.id)
    setConfirmAction(null)
  }

  function handleBulkConfirm() {
    if (bulkConfirm == null) return
    const ids = Array.from(selectedIds)
    if (ids.length === 0) {
      setBulkConfirm(null)
      return
    }
    useToastStore.getState().addToast({
      type: 'info',
      message: t('ragCachePage.candidates.bulkStarted', {
        count: ids.length,
        action: t(`ragCachePage.candidates.${bulkConfirm}`),
      }),
    })
    bulkMutation.mutate({ action: bulkConfirm, ids })
    setBulkConfirm(null)
  }

  const bulkBusy = bulkMutation.isPending

  const { exportAs, isReady: canExport } = useTableExport<RagCandidate>({
    filename: 'rag-candidates',
    rows: data,
    columns: [
      { key: 'id', header: 'id', accessor: r => r.id },
      { key: 'channel', header: 'channel', accessor: r => r.channel },
      { key: 'query', header: 'query', accessor: r => r.query },
      { key: 'response', header: 'response', accessor: r => r.response },
      { key: 'status', header: 'status', accessor: r => r.status },
      { key: 'capturedAt', header: 'capturedAt', accessor: r => r.capturedAt },
    ],
  })

  return (
    <div>
      <RagCandidatesToolbar
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        onExport={exportAs}
        canExport={canExport}
      />

      <RagCandidatesBulkBar
        selectedCount={selectedCount}
        bulkBusy={bulkBusy}
        onRequestBulk={setBulkConfirm}
        onClear={clearSelection}
      />

      {isLoading ? (
        <SkeletonTable rows={8} columns={6} />
      ) : isError ? (
        <div className="rag-inline-state" role="alert">
          <div>
            <strong>{t('ragCachePage.candidates.loadError')}</strong>
            <p>{t('ragCachePage.candidates.loadErrorDesc')}</p>
          </div>
          <button className="btn btn-secondary btn-sm" type="button" onClick={() => void refetch()}>
            {t('common.retry')}
          </button>
        </div>
      ) : data.length === 0 ? (
        <div className="rag-inline-state">
          <div>
            <strong>{statusFilter === 'ALL'
              ? t('ragCachePage.candidates.empty')
              : t('ragCachePage.candidates.emptyFiltered')}</strong>
            <p>{statusFilter === 'ALL'
              ? t('ragCachePage.candidates.emptyDesc')
              : t('ragCachePage.candidates.emptyFilteredDesc')}</p>
          </div>
          {statusFilter !== 'ALL' && (
            <button className="btn btn-secondary btn-sm" type="button" onClick={() => setStatusFilter('ALL')}>
              {t('ragCachePage.candidates.clearFilter')}
            </button>
          )}
        </div>
      ) : (
        <RagCandidatesTable
          data={data}
          selection={selection}
          bulkBusy={bulkBusy}
          selectedRow={selected}
          onSelectRow={setSelected}
        />
      )}

      <RagCandidateDetailDrawer
        candidate={selected}
        onClose={() => setSelected(null)}
        onRequestApprove={() => setConfirmAction('approve')}
        onRequestReject={() => setConfirmAction('reject')}
        approvePending={approveMutation.isPending}
        rejectPending={rejectMutation.isPending}
      />

      {confirmAction === 'approve' && (
        <ConfirmDialog
          title={t('ragCachePage.candidates.approve')}
          message={t('ragCachePage.candidates.approveConfirm')}
          onConfirm={handleApprove}
          onCancel={() => setConfirmAction(null)}
        />
      )}
      {confirmAction === 'reject' && (
        <ConfirmDialog
          title={t('ragCachePage.candidates.reject')}
          message={t('ragCachePage.candidates.rejectConfirm')}
          onConfirm={handleReject}
          onCancel={() => setConfirmAction(null)}
          danger
        />
      )}

      {bulkConfirm === 'approve' && (
        <ConfirmDialog
          title={t('ragCachePage.candidates.bulkApprove')}
          message={t('ragCachePage.candidates.bulkApproveConfirm', { count: selectedCount })}
          onConfirm={handleBulkConfirm}
          onCancel={() => setBulkConfirm(null)}
        />
      )}
      {bulkConfirm === 'reject' && (
        <ConfirmDialog
          title={t('ragCachePage.candidates.bulkReject')}
          message={t('ragCachePage.candidates.bulkRejectConfirm', { count: selectedCount })}
          onConfirm={handleBulkConfirm}
          onCancel={() => setBulkConfirm(null)}
          danger
        />
      )}
    </div>
  )
}

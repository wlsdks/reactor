import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { queryKeys } from '../../shared/lib/queryKeys'
import { getErrorMessage } from '../../shared/lib/getErrorMessage'
import { useToastStore } from '../../shared/store/toast.store'
import { useAnnouncer } from '../../shared/ui'
import * as approvalApi from './api'
import {
  filterApprovals,
  summarizeApprovalOps,
  type ApprovalQuickFilter,
} from './approvalOps'
import type { ApprovalSummary } from './types'

// ── Hook ──────────────────────────────────────────────────────────────────

export function useApprovalsData() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { announce } = useAnnouncer()

  const [searchParams, setSearchParams] = useSearchParams()
  const statusFilter = searchParams.get('status') ?? ''
  const quickParam = searchParams.get('queue')
  const quickFilter: ApprovalQuickFilter = (
    quickParam === 'attention'
    || quickParam === 'timedOut'
    || quickParam === 'stalePending'
    || quickParam === 'pendingReview'
  ) ? quickParam : 'all'
  const [selected, setSelected] = useState<ApprovalSummary | null>(null)

  const PAGE_SIZE = 50
  const [page, setPage] = useState(1)
  const [actionResult, setActionResult] = useState<string | null>(null)
  const [rejectTarget, setRejectTarget] = useState<ApprovalSummary | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [approveTarget, setApproveTarget] = useState<ApprovalSummary | null>(null)
  const [actioning, setActioning] = useState<string | null>(null)
  const processingIds = useRef(new Set<string>())

  function setStatusFilter(value: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set('status', value)
      else next.delete('status')
      return next
    }, { replace: true })
  }

  function setQuickFilter(value: ApprovalQuickFilter) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value === 'all') next.delete('queue')
      else next.set('queue', value)
      return next
    }, { replace: true })
  }

  const { data: approvals = [], isLoading, isFetching, error, dataUpdatedAt, refetch } = useQuery({
    queryKey: queryKeys.approvals.list(statusFilter || undefined),
    queryFn: () => approvalApi.listAllApprovals(statusFilter || undefined),
  })

  const lastLoadedAt = dataUpdatedAt > 0 ? dataUpdatedAt : null
  const loadFailure = error ? getErrorMessage(error) : null

  const approveMutation = useMutation({
    mutationFn: ({ id }: { id: string }) => approvalApi.approveToolCall(id),
    onSuccess: (response, { id }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.approvals.all() })
      setActionResult(response.message || t('approvals.approvedResult'))
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      announce(t('common.a11y.bulkApproveResult', { succeeded: 1, total: 1 }))
      setApproveTarget(null)
      if (selected?.id === id) setSelected(null)
    },
    onError: () => {
      useToastStore.getState().addToast({ type: 'error', message: t('approvals.approveError') })
      announce(t('common.a11y.bulkPartialFailure', { succeeded: 0, failed: 1 }), { priority: 'assertive' })
    },
    onSettled: (_data, _error, variables) => {
      setActioning(null)
      if (variables) processingIds.current.delete(variables.id)
    },
  })

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) => approvalApi.rejectToolCall(id, reason),
    onSuccess: (response, { id }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.approvals.all() })
      setActionResult(response.message || t('approvals.rejectedResult'))
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      announce(t('common.a11y.bulkRejectResult', { succeeded: 1, total: 1 }))
      setRejectTarget(null)
      setRejectReason('')
      if (selected?.id === id) setSelected(null)
    },
    onError: () => {
      announce(t('common.a11y.bulkPartialFailure', { succeeded: 0, failed: 1 }), { priority: 'assertive' })
      setRejectTarget(null)
    },
    onSettled: (_data, _error, variables) => {
      setActioning(null)
      if (variables) processingIds.current.delete(variables.id)
    },
  })

  function openApproveModal(approval: ApprovalSummary) {
    setApproveTarget(approval)
  }

  function handleConfirmApprove() {
    if (!approveTarget) return
    if (processingIds.current.has(approveTarget.id)) return
    processingIds.current.add(approveTarget.id)
    setActioning(approveTarget.id)
    setActionResult(null)

    approveMutation.mutate({ id: approveTarget.id })
  }

  function handleReject() {
    if (!rejectTarget) return
    if (processingIds.current.has(rejectTarget.id)) return
    processingIds.current.add(rejectTarget.id)
    setActioning(rejectTarget.id)
    setActionResult(null)
    rejectMutation.mutate({ id: rejectTarget.id, reason: rejectReason || undefined })
  }

  // ── Derived data ────────────────────────────────────────────────────────

  const opsSummary = summarizeApprovalOps(approvals, loadFailure)
  const filteredApprovals = filterApprovals(approvals, opsSummary.attentionItems, quickFilter)
  // Sort: PENDING items first (oldest requestedAt on top), then rest by oldest first
  const visibleApprovals = [...filteredApprovals].sort((a, b) => {
    if (a.status === 'PENDING' && b.status !== 'PENDING') return -1
    if (a.status !== 'PENDING' && b.status === 'PENDING') return 1
    return new Date(a.requestedAt).getTime() - new Date(b.requestedAt).getTime()
  })
  // Deselect if no longer in visible list
  const effectiveSelected = selected && visibleApprovals.some((a) => a.id === selected.id) ? selected : null
  const selectedAttention = effectiveSelected
    ? opsSummary.attentionItems.find((item) => item.approval.id === effectiveSelected.id) ?? null
    : null
  const unavailableState = loadFailure != null && approvals.length === 0
  const loadAlert = loadFailure == null
    ? null
    : approvals.length > 0
      ? t('approvals.snapshotWarning', { message: loadFailure })
      : t('approvals.channelUnavailable', { message: loadFailure })

  async function handleRefresh() {
    const result = await refetch()
    if (!result.error) {
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.refreshed') })
    }
  }

  return {
    // Query data
    approvals,
    isLoading,
    isFetching,
    lastLoadedAt,
    loadFailure,
    loadAlert,
    unavailableState,

    // Ops summary
    opsSummary,
    visibleApprovals,
    effectiveSelected,
    selectedAttention,

    // Filters
    statusFilter,
    setStatusFilter,
    quickFilter,
    setQuickFilter,

    // Selection
    selected,
    setSelected,

    // Pagination
    page,
    setPage,
    PAGE_SIZE,

    // Action state
    actionResult,
    actioning,

    // Approve modal
    approveTarget,
    setApproveTarget,
    openApproveModal,
    handleConfirmApprove,

    // Reject modal
    rejectTarget,
    setRejectTarget,
    rejectReason,
    setRejectReason,
    handleReject,

    // Actions
    handleRefresh,
  }
}

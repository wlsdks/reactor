import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import './approvals.css'
import { DataTable, EmptyState, OperationButton, PageHeader, RefreshButton, TableSkeleton, TimestampWithZone, WorkspaceUnavailable } from '../../../shared/ui'
import { useEscapeKey } from '../../../shared/lib/useEscapeKey'
import { useBodyOverflowLock } from '../../../shared/lib/useBodyOverflowLock'
import {
  APPROVAL_SEVERITY_ORDER,
  type ApprovalAttentionItem,
  type ApprovalQuickFilter,
  type ApprovalSignal,
} from '../approvalOps'
import type { ApprovalSummary } from '../types'
import { formatISODate } from '../../../shared/lib/formatters'
import { humanizeToolName } from '../../../shared/lib/humanizeToolName'
import { useApprovalsData } from '../useApprovalsData'

const approvalQuickFilters: ApprovalQuickFilter[] = ['all', 'attention', 'timedOut', 'stalePending', 'pendingReview']

function approvalStatusClass(status: ApprovalSummary['status']): string {
  return status.toLowerCase().replace('_', '-')
}

function approvalStatusLabel(status: ApprovalSummary['status'], t: (key: string) => string): string {
  return t(`approvals.statusLabels.${status.toLowerCase()}`)
}

function formatApprovalAge(value: number | null, t: (key: string, options?: Record<string, number>) => string): string {
  if (value == null) return t('approvals.ageUnknown')
  if (value < 60) return t('approvals.ageMinutes', { count: value })

  const hours = Math.floor(value / 60)
  if (hours < 24) return t('approvals.ageHours', { count: hours })

  return t('approvals.ageDays', { count: Math.floor(hours / 24) })
}

function riskLabel(value: string | null, t: (key: string, options?: Record<string, string>) => string): string {
  if (!value) return t('approvals.riskLevels.unknown')
  return t(`approvals.riskLevels.${value.toLowerCase()}`, { defaultValue: t('approvals.riskLevels.unknown') })
}

export function ApprovalsManager() {
  const { t } = useTranslation()
  const detailRef = useRef<HTMLDivElement>(null)

  const {
    approvals,
    isLoading,
    isFetching,
    lastLoadedAt,
    loadFailure,
    loadAlert,
    unavailableState,
    opsSummary,
    visibleApprovals,
    effectiveSelected,
    selectedAttention,
    statusFilter,
    setStatusFilter,
    quickFilter,
    setQuickFilter,
    selected,
    setSelected,
    page,
    setPage,
    PAGE_SIZE,
    actionResult,
    actioning,
    approveTarget,
    setApproveTarget,
    openApproveModal,
    handleConfirmApprove,
    rejectTarget,
    setRejectTarget,
    rejectReason,
    setRejectReason,
    handleReject,
    handleRefresh,
  } = useApprovalsData()

  function describeSignal(signal: ApprovalSignal): string {
    return t(`approvals.signalDetails.${signal.detailId}`, {
      count: signal.meta?.count ?? 0,
      total: signal.meta?.total ?? 0,
    })
  }

  // Surface critical (FAIL) signals before warnings before healthy ones so the
  // operator sees the most actionable readiness check first. Stable sort
  // preserves the original signal order within the same severity bucket.
  const readinessChecks = opsSummary.signals
    .map((signal) => ({
      id: signal.id,
      label: t(`approvals.signals.${signal.id}`),
      status: signal.status,
      description: describeSignal(signal),
    }))
    .sort((left, right) => APPROVAL_SEVERITY_ORDER[left.status] - APPROVAL_SEVERITY_ORDER[right.status])
  const decidedCount = Math.max(opsSummary.totalApprovals - opsSummary.pendingCount, 0)

  function describeAttention(item: ApprovalAttentionItem): string {
    return t(`approvals.attentionDetails.${item.detailId}`, {
      age: formatApprovalAge(item.ageMinutes, t),
    })
  }

  useEscapeKey(!!selected && !rejectTarget && !approveTarget, () => setSelected(null))
  useBodyOverflowLock(!!rejectTarget || !!approveTarget)

  useEffect(() => {
    if (!effectiveSelected || typeof window.matchMedia !== 'function' || !window.matchMedia('(max-width: 1024px)').matches) return

    detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [effectiveSelected])

  const columns = [
    {
      key: 'toolName',
      header: t('approvals.tool'),
      width: '20%',
      render: (approval: ApprovalSummary) => <span title={approval.toolName}>{humanizeToolName(approval.toolName)}</span>,
    },
    {
      key: 'status',
      header: t('common.status'),
      width: '18%',
      render: (approval: ApprovalSummary) => (
        <span className={`approval-status approval-status--${approvalStatusClass(approval.status)}`}>
          <span aria-hidden="true" />
          {approvalStatusLabel(approval.status, t)}
        </span>
      ),
    },
    {
      key: 'requestedAt',
      header: t('approvals.requestedAt'),
      width: '24%',
      render: (approval: ApprovalSummary) => formatISODate(approval.requestedAt),
    },
  ]

  return (
    <div className="page">
      <PageHeader
        title={t('nav.approvals')}
        description={
          <>
            <p className="page-subtitle">{t('nav.help.approvals')}</p>
            {lastLoadedAt && (
              <p className="detail-note">
                {t('approvals.lastSyncLabel')}:{' '}
                <TimestampWithZone value={lastLoadedAt} />
              </p>
            )}
          </>
        }
        actions={unavailableState ? undefined : (
          <>
            {approvals.length > 0 && (
              <select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1) }}>
                <option value="">{t('approvals.allStatuses')}</option>
                <option value="PENDING">{t('common.statuses.PENDING')}</option>
                <option value="APPROVED">{t('common.statuses.APPROVED')}</option>
                <option value="REJECTED">{t('common.statuses.REJECTED')}</option>
                <option value="TIMED_OUT">{t('common.statuses.TIMED_OUT')}</option>
                <option value="CANCELLED">{t('common.statuses.CANCELLED')}</option>
              </select>
            )}
            <RefreshButton onRefresh={handleRefresh} isFetching={isFetching} />
          </>
        )}
      />

      {loadAlert && !unavailableState && (
        <div className={`alert ${approvals.length > 0 ? 'alert-warning' : 'alert-error'} alert-with-retry`}>
          <span className="alert-message">{loadAlert}</span>
          <button className="btn btn-sm btn-secondary" onClick={handleRefresh}>
            {t('common.retry')}
          </button>
        </div>
      )}
      {actionResult && <div className="alert alert-success">{actionResult}</div>}

      {unavailableState ? (
        <WorkspaceUnavailable
          title={t('approvals.unavailableTitle')}
          description={t('approvals.unavailableDescription')}
          retryLabel={t('approvals.retry')}
          retryingLabel={t('approvals.retrying')}
          onRetry={handleRefresh}
          isRetrying={isFetching}
          secondaryAction={{ label: t('approvals.openHealth'), to: '/health' }}
          guide={{
            title: t('approvals.recoveryGuideTitle'),
            steps: [
              t('approvals.recoveryGuide.checkAccount'),
              t('approvals.recoveryGuide.checkStatus'),
              t('approvals.recoveryGuide.retry'),
            ],
            technicalLabel: t('approvals.technicalError'),
            technicalDetail: loadFailure,
          }}
        />
      ) : (
      <>
      <section className={`approvals-readiness is-${opsSummary.status.toLowerCase()}`} aria-labelledby="approvals-readiness-title">
        <div className="approvals-readiness__summary">
          <span className="approvals-readiness__dot" aria-hidden="true" />
          <div>
            <h2 id="approvals-readiness-title">{t('approvals.opsTitle')}</h2>
            <p>{t('approvals.readinessSummary', {
              pending: opsSummary.pendingCount,
              timedOut: opsSummary.timedOutCount,
              covered: opsSummary.coveredCount,
              total: opsSummary.totalApprovals,
            })}</p>
          </div>
        </div>
        <dl className="approvals-readiness__metrics">
          <div><dt>{t('approvals.pendingRequestsCard')}</dt><dd>{opsSummary.pendingCount}</dd></div>
          <div><dt>{t('approvals.timeoutRequestsCard')}</dt><dd>{opsSummary.timedOutCount}</dd></div>
          <div><dt>{t('approvals.decidedRequestsCard')}</dt><dd>{decidedCount}</dd></div>
        </dl>
        {opsSummary.status !== 'PASS' && (
          <details className="approvals-readiness__details">
            <summary>{t('approvals.readinessDetails')}</summary>
            <p>{t('approvals.opsDescription')}</p>
            <ul className="approvals-readiness__checks">
              {readinessChecks.map((check) => (
                <li key={check.id} className={`is-${check.status.toLowerCase()}`}>
                  <span aria-hidden="true" />
                  <strong>{check.label}</strong>
                  <span>{check.description}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      {opsSummary.attentionItems.length > 0 && (
        <section className="approvals-attention" aria-labelledby="approvals-attention-title">
          <header>
            <div>
              <h2 id="approvals-attention-title">{t('approvals.attentionTitle')}</h2>
              <p>{t('approvals.attentionDescription')}</p>
            </div>
            <span>{opsSummary.attentionItems.length}</span>
          </header>
          <div className="approvals-attention__list">
            {opsSummary.attentionItems.map((item) => (
              <div className={`approvals-attention__row is-${item.status.toLowerCase()}`} key={item.id}>
                <span className="approvals-attention__dot" aria-hidden="true" />
                <div>
                  <strong title={item.approval.toolName}>{humanizeToolName(item.approval.toolName)}</strong>
                  <p>{describeAttention(item)}</p>
                  <span>{t('approvals.requestedAt')}: {formatISODate(item.approval.requestedAt)} · {t('approvals.age')}: {formatApprovalAge(item.ageMinutes, t)}</span>
                </div>
                <button className="btn btn-secondary btn-sm" onClick={() => setSelected(item.approval)}>
                  {t('approvals.openApprovalDetail')}
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className={`split-layout ${effectiveSelected ? '' : 'split-layout--collapsed'}`}>
        <div className="split-left">
          <section className="approvals-queue" aria-labelledby="approvals-queue-title">
            <header>
              <div>
                <h2 id="approvals-queue-title">{t('approvals.queueTitle')}</h2>
                {approvals.length > 0 && <p>{t('approvals.filterDescription')}</p>}
              </div>
              {approvals.length > 0 && <span>{t('approvals.showingRows', { shown: visibleApprovals.length, total: approvals.length })}</span>}
            </header>
            {approvals.length > 0 && (
              <div className="approvals-queue__filters" role="group" aria-label={t('approvals.filterTitle')}>
                {approvalQuickFilters.map((mode) => (
                  <button
                    key={mode}
                    className={quickFilter === mode ? 'is-active' : ''}
                    aria-pressed={quickFilter === mode}
                    onClick={() => { setQuickFilter(mode); setPage(1) }}
                  >
                    {t(`approvals.quickFilters.${mode}`)}
                  </button>
                ))}
              </div>
            )}

            {isLoading && approvals.length === 0 ? (
              <TableSkeleton />
            ) : approvals.length === 0 ? (
              unavailableState ? (
                  <EmptyState
                    message={t(`approvals.emptyState.${opsSummary.loadIssue ?? 'unknown'}`)}
                    description={t('approvals.emptyDescription')}
                    actionLabel={t('common.refresh')}
                    onAction={handleRefresh}
                  />
                ) : (
                  <EmptyState
                    message={t('approvals.empty')}
                    description={t('approvals.emptyHealthyDescription')}
                  />
                )
            ) : visibleApprovals.length === 0 ? (
                <EmptyState
                  message={t('approvals.filterEmpty')}
                  description={t('approvals.filterEmptyDescription')}
                />
            ) : (
              <>
                <div className="detail-note" style={{ marginBottom: 'var(--space-2)' }}>
                  {t('common.showingCount', { shown: visibleApprovals.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).length, total: visibleApprovals.length })}
                </div>
                <DataTable
                  columns={columns}
                  data={visibleApprovals.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)}
                  keyFn={(approval) => approval.id}
                  onRowClick={setSelected}
                  selectedKey={effectiveSelected?.id ?? null}
                  page={page}
                  pageSize={PAGE_SIZE}
                  totalCount={visibleApprovals.length}
                  onPageChange={setPage}
                />
              </>
            )}
          </section>
        </div>

        {effectiveSelected && (
        <div className="split-right" ref={detailRef} tabIndex={-1}>
          <aside className="approval-detail" aria-label={t('approvals.detailDescription')}>
              <div className="detail-panel-header">
                <div className="detail-header">
                  <h2 title={effectiveSelected.toolName}>{humanizeToolName(effectiveSelected.toolName)}</h2>
                  <span className={`approval-status approval-detail__status approval-status--${approvalStatusClass(effectiveSelected.status)}`}>
                    <span aria-hidden="true" />
                    {approvalStatusLabel(effectiveSelected.status, t)}
                  </span>
                </div>
                <button
                  className="detail-close-btn"
                  onClick={() => setSelected(null)}
                  aria-label={t('common.close')}
                >
                  <X aria-hidden="true" size="var(--icon-size-md)" />
                </button>
              </div>
              <p className="detail-description">{t('approvals.detailDescription')}</p>
              <dl className="approval-detail__facts">
                <div><dt>{t('approvals.requestedAt')}</dt><dd>{formatISODate(effectiveSelected.requestedAt)}</dd></div>
                <div><dt>{t('approvals.requestedBy')}</dt><dd>{effectiveSelected.requestedBy || '-'}</dd></div>
                <div><dt>{t('approvals.riskLevel')}</dt><dd>{riskLabel(effectiveSelected.riskLevel, t)}</dd></div>
              </dl>
              {selectedAttention && (
                <div className="detail-section">
                  <div className="detail-section-header">
                    <h3>{t('approvals.operatorNoteTitle')}</h3>
                  </div>
                  <p className="detail-note">{describeAttention(selectedAttention)}</p>
                  <p className="detail-note">{t('approvals.age')}: {formatApprovalAge(selectedAttention.ageMinutes, t)}</p>
                </div>
              )}
              <details className="approval-detail__technical">
                <summary>{t('approvals.technicalDetails')}</summary>
                <dl>
                  <div><dt>{t('approvals.runId')}</dt><dd>{effectiveSelected.runId}</dd></div>
                  <div><dt>{t('approvals.timeout')}</dt><dd>{effectiveSelected.timeoutMs == null ? '-' : `${effectiveSelected.timeoutMs.toLocaleString()} ms`}</dd></div>
                  <div><dt>{t('approvals.idempotencyKey')}</dt><dd>{effectiveSelected.idempotencyKey ?? '-'}</dd></div>
                </dl>
              </details>
              {effectiveSelected.status === 'PENDING' && (
                <div className="detail-actions">
                  <OperationButton
                    variant="primary"
                    isOperating={actioning === effectiveSelected.id}
                    onClick={() => { openApproveModal(effectiveSelected) }}
                  >
                    {t('approvals.approve')}
                  </OperationButton>
                  <OperationButton
                    variant="danger"
                    onClick={() => { setRejectTarget(effectiveSelected); setRejectReason('') }}
                  >
                    {t('approvals.reject')}
                  </OperationButton>
                </div>
              )}
          </aside>
        </div>
        )}
      </div>
      </>
      )}

      {rejectTarget && (
        <div className="modal-overlay" onClick={() => setRejectTarget(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="approvals-reject-modal-title"
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => { if (event.key === 'Escape') setRejectTarget(null) }}
          >
            <h3 id="approvals-reject-modal-title" className="modal-title">{t('approvals.rejectTitle')}</h3>
            <p>{t('approvals.rejectMessage', { tool: humanizeToolName(rejectTarget.toolName) })}</p>
            <div className="form-group">
              <label htmlFor="approval-reject-reason">{t('approvals.reason')}</label>
              <input
                id="approval-reject-reason"
                value={rejectReason}
                onChange={(event) => setRejectReason(event.target.value)}
                placeholder={t('approvals.reasonPlaceholder')}
              />
            </div>
            <div className="modal-actions">
              <OperationButton variant="secondary" onClick={() => setRejectTarget(null)}>{t('common.cancel')}</OperationButton>
              <OperationButton
                variant="danger"
                onClick={() => { handleReject() }}
                isOperating={actioning === rejectTarget.id}
              >
                {t('approvals.reject')}
              </OperationButton>
            </div>
          </div>
        </div>
      )}

      {approveTarget && (
        <div className="modal-overlay" onClick={() => setApproveTarget(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="approvals-approve-modal-title"
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => { if (event.key === 'Escape') setApproveTarget(null) }}
          >
            <h3 id="approvals-approve-modal-title" className="modal-title">{t('approvals.approveTitle')}</h3>
            <p>{t('approvals.approveMessage', { tool: humanizeToolName(approveTarget.toolName) })}</p>
            <div className="modal-actions">
              <OperationButton variant="secondary" onClick={() => setApproveTarget(null)}>{t('common.cancel')}</OperationButton>
              <OperationButton
                variant="primary"
                onClick={() => { handleConfirmApprove() }}
                isOperating={actioning === approveTarget.id}
              >
                {t('approvals.confirmApprove')}
              </OperationButton>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

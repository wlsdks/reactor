import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useFocusTrap } from '../../../shared/lib/useFocusTrap'
import { useEscapeKey } from '../../../shared/lib/useEscapeKey'
import { useBodyOverflowLock } from '../../../shared/lib/useBodyOverflowLock'
import { formatDateTime } from '../../../shared/lib/formatters'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { showApiErrorToast } from '../../../shared/lib/showApiErrorToast'
import { useToastStore } from '../../../shared/store/toast.store'
import { useAnnouncer } from '../../../shared/ui'
import { ApiError } from '../../../shared/api/errors'
import * as auditApi from '../api'
import type { AuditLogEntry, AuditRollbackPreview } from '../types'

interface AuditRollbackModalProps {
  open: boolean
  entry: AuditLogEntry | null
  onClose: () => void
  onSuccess: () => void
}

/**
 * Build the resource label that the operator must type in to confirm rollback.
 * Prefers the concrete resource handle (`type:id`) but falls back to the
 * action code + first 8 chars of the entry id so the type-to-confirm guard
 * still exists when the row lacks resource metadata.
 */
function buildResourceLabel(entry: AuditLogEntry): string {
  if (entry.resourceType && entry.resourceId) return `${entry.resourceType}:${entry.resourceId}`
  if (entry.resourceId) return entry.resourceId
  if (entry.resourceType) return entry.resourceType
  return `${entry.action}:${entry.id.slice(0, 8)}`
}

/**
 * Outer component. Remounts the inner body via `key` whenever the target
 * entry changes so all local state (typed-confirm input, preview query cache
 * binding) resets cleanly without needing an explicit useEffect-based reset.
 */
export function AuditRollbackModal(props: AuditRollbackModalProps) {
  if (!props.open || !props.entry) return null
  return <AuditRollbackModalInner key={props.entry.id} {...props} entry={props.entry} />
}

interface AuditRollbackModalInnerProps extends Omit<AuditRollbackModalProps, 'entry'> {
  entry: AuditLogEntry
}

function AuditRollbackModalInner({ entry, onClose, onSuccess }: AuditRollbackModalInnerProps) {
  const { t } = useTranslation()
  const { announce } = useAnnouncer()
  const queryClient = useQueryClient()
  const modalRef = useRef<HTMLDivElement>(null)
  const [typedConfirm, setTypedConfirm] = useState('')

  useFocusTrap(modalRef, true)
  useBodyOverflowLock(true)
  useEscapeKey(true, onClose)

  const previewQuery = useQuery<AuditRollbackPreview, unknown>({
    queryKey: queryKeys.audit.rollbackPreview(entry.id),
    queryFn: () => auditApi.previewAuditRollback(entry.id),
    retry: false,
    staleTime: 30_000,
  })

  const rollbackMutation = useMutation({
    mutationFn: () => auditApi.rollbackAuditEntry(entry.id),
    onSuccess: (result) => {
      // Invalidate every cached audit list/filter so the rolled-back entry's
      // status (and any new rollback-event row the BE writes) is reflected
      // before the parent's onSuccess handler runs its own refetch.
      void queryClient.invalidateQueries({ queryKey: queryKeys.audit.all() })
      useToastStore.getState().addToast({
        type: 'success',
        message: result?.message ?? t('auditPage.rollback.successToast'),
      })
      announce(t('auditPage.rollback.successToast'), { priority: 'polite' })
      onSuccess()
      onClose()
    },
    onError: (error) => {
      const resolved = showApiErrorToast(error, {
        onRetry: () => rollbackMutation.mutate(),
      })
      announce(
        t('auditPage.rollback.errorToast', { message: resolved.message }),
        { priority: 'assertive' },
      )
    },
  })

  const previewError = previewQuery.error
  const previewMissing = previewError instanceof ApiError && previewError.status === 404
  const preview = previewQuery.data

  // Warn once when the preview endpoint is not implemented so developers
  // investigating the network tab see the same signal they would in the UI.
  useEffect(() => {
    if (previewMissing) {
      console.warn(
        '[audit] rollback preview endpoint is not implemented; showing unavailable fallback.',
      )
    }
  }, [previewMissing])

  const resourceLabel = buildResourceLabel(entry)
  const typedConfirmMatches = typedConfirm.trim() === resourceLabel
  const isSubmitting = rollbackMutation.isPending

  return createPortal(
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal-lg"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="audit-rollback-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div
          className="modal-title"
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
        >
          <span id="audit-rollback-title">{t('auditPage.rollback.modalTitle')}</span>
          <button
            className="detail-close-btn"
            onClick={onClose}
            aria-label={t('common.aria.close')}
          >
            ×
          </button>
        </div>

        <div className="modal-body">
          <div className="alert alert-warning" style={{ marginBottom: 'var(--space-4)' }}>
            {t('auditPage.rollback.manualRecoveryBoundary')}
          </div>

          <div className="detail-panel detail-panel--compact" style={{ marginBottom: 'var(--space-4)' }}>
            <div className="detail-section-header">
              <h3>{t('auditPage.rollback.entryTitle')}</h3>
            </div>
            <div className="meta-grid" style={{ marginTop: 'var(--space-2)' }}>
              <span>{t('auditPage.category')}: <code>{entry.category}</code></span>
              <span>{t('auditPage.action')}: {entry.action}</span>
              <span>{t('auditPage.actor')}: {entry.actorEmail ?? entry.actor}</span>
              <span>
                {t('auditPage.resource')}: {entry.resourceType ?? '-'}:{entry.resourceId ?? '-'}
              </span>
              <span>{t('auditPage.created')}: {formatDateTime(entry.createdAt)}</span>
            </div>
          </div>

          <div className="detail-panel detail-panel--compact" style={{ marginBottom: 'var(--space-4)' }}>
            <div className="detail-section-header">
              <h3>{t('auditPage.rollback.impactPreview')}</h3>
            </div>
            {previewQuery.isLoading ? (
              <p className="detail-note">{t('common.loading')}</p>
            ) : previewMissing ? (
              <p className="detail-note" role="status">
                {t('auditPage.rollback.previewUnavailable')}
              </p>
            ) : previewError ? (
              <p className="detail-note" role="status">
                {t('auditPage.rollback.previewUnavailable')}
              </p>
            ) : preview ? (
              <div className="panel-stack" style={{ marginTop: 'var(--space-2)' }}>
                {preview.summary && (
                  <p className="detail-note">{preview.summary}</p>
                )}
                {preview.warnings && preview.warnings.length > 0 && (
                  <ul className="detail-note" style={{ paddingLeft: 'var(--space-4)' }}>
                    {preview.warnings.map((warning, index) => (
                      <li key={`${index}-${warning}`}>{warning}</li>
                    ))}
                  </ul>
                )}
                {preview.changes && preview.changes.length > 0 && (
                  <table className="data-table" style={{ marginTop: 'var(--space-2)' }}>
                    <thead>
                      <tr>
                        <th scope="col">{t('auditPage.rollback.previewField')}</th>
                        <th scope="col">{t('auditPage.rollback.previewFrom')}</th>
                        <th scope="col">{t('auditPage.rollback.previewTo')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.changes.map((change, index) => (
                        <tr key={`${index}-${change.field ?? ''}`}>
                          <td>{change.field ?? '-'}</td>
                          <td>{formatPreviewValue(change.from)}</td>
                          <td>{formatPreviewValue(change.to)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {(!preview.summary && !preview.changes?.length && !preview.warnings?.length) && (
                  <p className="detail-note">{t('auditPage.rollback.previewEmpty')}</p>
                )}
              </div>
            ) : (
              <p className="detail-note">{t('auditPage.rollback.previewUnavailable')}</p>
            )}
          </div>

          <div className="detail-panel detail-panel--compact">
            <label htmlFor="audit-rollback-confirm" style={{ display: 'block', marginBottom: 'var(--space-2)' }}>
              {t('auditPage.rollback.typeToConfirm', { name: resourceLabel })}
            </label>
            <input
              id="audit-rollback-confirm"
              type="text"
              value={typedConfirm}
              onChange={(event) => setTypedConfirm(event.target.value)}
              placeholder={resourceLabel}
              aria-describedby="audit-rollback-confirm-help"
              autoComplete="off"
            />
            <p id="audit-rollback-confirm-help" className="detail-note" style={{ marginTop: 'var(--space-2)' }}>
              {t('auditPage.rollback.typeToConfirmHelp')}
            </p>
          </div>
        </div>

        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose} disabled={isSubmitting}>
            {t('auditPage.rollback.cancel')}
          </button>
          <button
            className="btn btn-danger"
            onClick={() => rollbackMutation.mutate()}
            disabled={!typedConfirmMatches || isSubmitting}
          >
            {isSubmitting
              ? t('auditPage.rollback.submitting')
              : t('auditPage.rollback.confirm')}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

function formatPreviewValue(value: unknown): string {
  if (value == null) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return '[unserializable value]'
  }
}

import { useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useFocusTrap } from '../lib/useFocusTrap'
import { useEscapeClose } from '../lib/useEscapeClose'
import { useBodyOverflowLock } from '../lib/useBodyOverflowLock'
import { OverlayCloseButton } from './OverlayCloseButton'

interface ConfirmDialogProps {
  title: string
  message: string
  onConfirm: () => void
  onCancel: () => void
  danger?: boolean
  /**
   * Whether clicking the backdrop closes the dialog. Confirm dialogs default to
   * `false` so users must make an explicit choice (Cancel / Confirm / ✕ / Esc).
   * @default false
   */
  closeOnBackdrop?: boolean
  /**
   * When provided, the confirm button stays disabled until the user types this
   * exact string into the inline input. Used for irreversible actions where
   * misclick recovery is impossible (resource deletes, policy resets, cache
   * invalidations, governance bypasses).
   *
   * Comparison is performed against the trimmed input value — surrounding
   * whitespace is ignored but inner spacing must match exactly.
   */
  confirmText?: string
  /**
   * Label rendered above the type-to-confirm input. Defaults to
   * `t('common.typeToConfirm')`. Only consulted when `confirmText` is set.
   */
  confirmTextLabel?: string
}

export function ConfirmDialog({
  title,
  message,
  onConfirm,
  onCancel,
  danger = false,
  closeOnBackdrop = false,
  confirmText,
  confirmTextLabel,
}: ConfirmDialogProps) {
  const { t } = useTranslation()
  const modalRef = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const inputId = useId()
  const helpId = useId()
  const [typedValue, setTypedValue] = useState('')

  useFocusTrap(modalRef, true)
  useEscapeClose(onCancel, { active: true })
  useBodyOverflowLock(true)

  const requireType = typeof confirmText === 'string' && confirmText.length > 0
  const typedMatches = requireType ? typedValue.trim() === confirmText : true
  const confirmDisabled = requireType && !typedMatches

  function handleConfirm() {
    if (confirmDisabled) return
    onConfirm()
  }

  return createPortal(
    <div
      className="modal-overlay"
      onClick={closeOnBackdrop ? onCancel : undefined}
    >
      <div
        className="modal"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={e => e.stopPropagation()}
      >
        <h3 id={titleId} className="modal-title">{title}</h3>
        <OverlayCloseButton onClick={onCancel} label={t('common.modal.closeAriaLabel')} />
        <p className="modal-message">{message}</p>
        {requireType && (
          <div className="form-group" style={{ marginTop: 'var(--space-3)' }}>
            <label htmlFor={inputId}>
              {confirmTextLabel ?? t('common.typeToConfirm')}{' '}
              <code style={{ fontFamily: 'var(--font-mono)' }}>{confirmText}</code>
            </label>
            <input
              id={inputId}
              type="text"
              value={typedValue}
              onChange={e => setTypedValue(e.target.value)}
              placeholder={confirmText}
              autoComplete="off"
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              aria-required="true"
              aria-describedby={helpId}
              aria-invalid={!typedMatches}
              style={{ fontFamily: 'var(--font-mono)' }}
              onKeyDown={e => {
                if (e.key === 'Enter' && typedMatches) {
                  e.preventDefault()
                  handleConfirm()
                }
              }}
            />
            <p id={helpId} className="detail-note" style={{ marginTop: 'var(--space-2)' }}>
              {t('common.typeToConfirmHelp')}
            </p>
          </div>
        )}
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onCancel}>{t('common.cancel')}</button>
          <button
            className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            onClick={handleConfirm}
            disabled={confirmDisabled}
          >
            {t('common.confirm')}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

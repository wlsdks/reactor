import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useFocusTrap } from '../../../shared/lib/useFocusTrap'
import { useEscapeKey } from '../../../shared/lib/useEscapeKey'
import { useBodyOverflowLock } from '../../../shared/lib/useBodyOverflowLock'
import { LoadingSpinner } from '../../../shared/ui'
import type { useChangePassword } from '../useChangePassword'

type ChangePasswordState = ReturnType<typeof useChangePassword>

interface ChangePasswordModalProps {
  state: ChangePasswordState
}

export function ChangePasswordModal({ state }: ChangePasswordModalProps) {
  const { t } = useTranslation()
  const modalRef = useRef<HTMLDivElement>(null)
  useFocusTrap(modalRef, state.isOpen)
  useEscapeKey(state.isOpen, state.close)
  useBodyOverflowLock(state.isOpen)

  if (!state.isOpen) return null

  return (
    <div className="modal-overlay" onClick={state.close}>
      <div
        className="modal"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="password-dialog-title"
        onClick={e => e.stopPropagation()}
      >
        <h3 id="password-dialog-title" className="modal-title">
          {t('auth.changePassword')}
        </h3>
        <form onSubmit={(e) => { e.preventDefault(); void state.submit() }} noValidate>
          {state.error && <div id="password-error" className="alert alert-error" role="alert">{state.error}</div>}
          {state.success && <div className="alert alert-success" role="status">{state.success}</div>}
          <div className="form-group">
            <label htmlFor="current-password">{t('auth.currentPassword')}</label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              value={state.currentPassword}
              onChange={e => state.setCurrentPassword(e.target.value)}
              required
              aria-invalid={!!state.error}
              aria-describedby={state.error ? 'password-error' : undefined}
            />
          </div>
          <div className="form-group">
            <label htmlFor="new-password">{t('auth.newPassword')}</label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              value={state.newPassword}
              onChange={e => state.setNewPassword(e.target.value)}
              required
              aria-invalid={!!state.error}
              aria-describedby={state.error ? 'password-error' : undefined}
            />
          </div>
          <div className="form-group">
            <label htmlFor="confirm-password">{t('auth.confirmPassword')}</label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              value={state.confirmPassword}
              onChange={e => state.setConfirmPassword(e.target.value)}
              required
              aria-invalid={!!state.error}
              aria-describedby={state.error ? 'password-error' : undefined}
            />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={state.close}>
              {t('common.cancel')}
            </button>
            <button className="btn btn-primary" type="submit" disabled={state.isSubmitting}>
              {state.isSubmitting ? <LoadingSpinner size="sm" /> : t('auth.changePassword')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

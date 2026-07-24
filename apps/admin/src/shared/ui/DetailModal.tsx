import { useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useFocusTrap } from '../lib/useFocusTrap'
import { useEscapeClose } from '../lib/useEscapeClose'
import { useBodyOverflowLock } from '../lib/useBodyOverflowLock'
import { OverlayCloseButton } from './OverlayCloseButton'

interface DetailModalProps {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  /**
   * Whether clicking the backdrop closes the modal.
   * @default true
   */
  closeOnBackdrop?: boolean
  /** Visual width. Defaults to the existing large detail-dialog contract. */
  size?: 'default' | 'large'
}

export function DetailModal({
  open,
  title,
  onClose,
  children,
  closeOnBackdrop = true,
  size = 'large',
}: DetailModalProps) {
  const { t } = useTranslation()
  const modalRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  useFocusTrap(modalRef, open)
  useBodyOverflowLock(open)
  useEscapeClose(onClose, { active: open })

  if (!open) return null

  return createPortal(
    <div
      className="modal-overlay"
      onClick={closeOnBackdrop ? onClose : undefined}
    >
      <div
        className={`modal${size === 'large' ? ' modal-lg' : ''}`}
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-title">
          <span id={titleId}>{title}</span>
        </div>
        <OverlayCloseButton onClick={onClose} label={t('common.modal.closeAriaLabel')} />
        <div className="modal-body">
          {children}
        </div>
      </div>
    </div>,
    document.body,
  )
}

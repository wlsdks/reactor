import { useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useFocusTrap } from '../lib/useFocusTrap'
import { useEscapeClose } from '../lib/useEscapeClose'
import { useBodyOverflowLock } from '../lib/useBodyOverflowLock'
import { OverlayCloseButton } from './OverlayCloseButton'

interface SideDrawerProps {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  /**
   * Whether clicking the backdrop closes the drawer.
   * @default true
   */
  closeOnBackdrop?: boolean
  /** Width role for content that needs a wider reading or visualization area. */
  size?: 'default' | 'wide'
}

export function SideDrawer({
  open,
  title,
  onClose,
  children,
  closeOnBackdrop = true,
  size = 'default',
}: SideDrawerProps) {
  const { t } = useTranslation()
  const drawerRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  useFocusTrap(drawerRef, open)
  useBodyOverflowLock(open)
  useEscapeClose(onClose, { active: open })

  if (!open) return null

  return createPortal(
    <div
      className="drawer-overlay"
      onClick={closeOnBackdrop ? onClose : undefined}
    >
      <div
        className={`drawer${size === 'wide' ? ' drawer--wide' : ''}`}
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={e => e.stopPropagation()}
      >
        <div className="drawer-header">
          <h3 id={titleId} className="drawer-title">{title}</h3>
        </div>
        <OverlayCloseButton onClick={onClose} label={t('common.modal.closeAriaLabel')} />
        <div className="drawer-body">
          {children}
        </div>
      </div>
    </div>,
    document.body,
  )
}

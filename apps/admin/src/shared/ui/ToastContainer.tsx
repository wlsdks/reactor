import { useTranslation } from 'react-i18next'
import { useEscapeClose } from '../lib/useEscapeClose'
import {
  useToastStore,
  selectVisibleToasts,
  selectAllToastsSorted,
  selectOverflowCount,
} from '../store/toast.store'

const typeStyles: Record<string, { background: string; border: string }> = {
  success: { background: 'var(--bg-elevated)', border: '1px solid var(--green)' },
  error: { background: 'var(--bg-elevated)', border: '1px solid var(--red)' },
  info: { background: 'var(--bg-elevated)', border: '1px solid var(--blue)' },
  warning: { background: 'var(--bg-elevated)', border: '1px solid var(--yellow)' },
}

const typeColors: Record<string, string> = {
  success: 'var(--green)',
  error: 'var(--red)',
  info: 'var(--blue)',
  warning: 'var(--yellow)',
}

export function ToastContainer() {
  const { t } = useTranslation()
  // Subscribe only to primitive store fields to avoid creating new array
  // references on each render (which would re-trigger useSyncExternalStore).
  // Selector functions are then applied locally; the React Compiler memoizes
  // their results based on `toasts` identity.
  const toasts = useToastStore((s) => s.toasts)
  const expandQueue = useToastStore((s) => s.expandQueue)
  const setExpandQueue = useToastStore((s) => s.setExpandQueue)
  const removeToast = useToastStore((s) => s.removeToast)
  const pauseToast = useToastStore((s) => s.pauseToast)
  const resumeToast = useToastStore((s) => s.resumeToast)

  const visibleToasts = selectVisibleToasts({ toasts })
  const allToastsSorted = selectAllToastsSorted({ toasts })
  const overflowCount = selectOverflowCount({ toasts })

  // ESC collapses the expanded overflow view.
  useEscapeClose(() => setExpandQueue(false), { active: expandQueue })

  if (toasts.length === 0) return null

  const isExpanded = expandQueue && overflowCount > 0
  const renderedToasts = isExpanded ? allToastsSorted : visibleToasts
  const hasOverflow = overflowCount > 0
  const showStackHint = hasOverflow && !isExpanded

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      style={{
        position: 'fixed',
        top: 'var(--space-4)',
        right: 'var(--space-4)',
        zIndex: 'var(--z-toast)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
        width: 'clamp(320px, 40vw, 480px)',
        maxWidth: 'calc(100vw - var(--space-4) * 2)',
      }}
    >
      {renderedToasts.map((toast, index) => {
        const isLastVisible = showStackHint && index === renderedToasts.length - 1
        return (
          <div
            key={toast.id}
            className={isLastVisible ? 'toast-stack-anchor' : undefined}
            role="alert"
            onMouseEnter={() => pauseToast(toast.id)}
            onMouseLeave={() => resumeToast(toast.id)}
            style={{
              ...typeStyles[toast.type],
              borderRadius: 'var(--radius, 6px)',
              padding: 'var(--space-2) var(--space-3)',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-primary)',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 'var(--space-2)',
              boxShadow: 'var(--shadow-md)',
              animation: 'toast-slide-in var(--duration-base) var(--ease-standard)',
              position: 'relative',
            }}
          >
            {toast.type === 'success' && (
              <span className="toast-success-icon">
                <svg viewBox="0 0 24 24" width="20" height="20">
                  <path className="checkmark-path" d="M5 13l4 4L19 7" />
                </svg>
              </span>
            )}
            {toast.type === 'error' && (
              <span style={{ color: 'var(--red)', fontSize: 'var(--text-md)', fontWeight: 'var(--font-weight-strong)' }}>!</span>
            )}
            <span
              style={{
                color: typeColors[toast.type],
                fontWeight: 'var(--font-weight-strong)',
                fontSize: 'var(--text-xxs)',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                flexShrink: 0,
                marginTop: 1,
              }}
            >
              {t(`common.toast.types.${toast.type}`)}
            </span>
            <span
              style={{
                flex: 1,
                minWidth: 0,
                wordBreak: 'keep-all',
                overflowWrap: 'anywhere',
                whiteSpace: 'normal',
                lineHeight: 1.45,
              }}
            >
              {toast.message}
            </span>
            {toast.action && (
              <button
                type="button"
                onClick={() => {
                  toast.action?.onAction()
                  if (toast.action?.closeOnAction !== false) {
                    removeToast(toast.id)
                  }
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--accent)',
                  cursor: 'pointer',
                  padding: '0 var(--space-1)',
                  fontSize: 'var(--text-xs)',
                  // Test asserts the literal 510; tokenizing is blocked until
                  // the test gains access to resolved CSS variables.
                  fontWeight: 510,
                  lineHeight: 1.2,
                  flexShrink: 0,
                  whiteSpace: 'nowrap',
                }}
              >
                {toast.action.label || t('common.toast.action')}
              </button>
            )}
            <button
              type="button"
              onClick={() => removeToast(toast.id)}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--text-dim)',
                cursor: 'pointer',
                padding: '0 var(--space-1)',
                fontSize: 'var(--text-lg)',
                lineHeight: 1,
                flexShrink: 0,
              }}
              aria-label={t('common.toast.close')}
            >
              x
            </button>
            {isLastVisible && (
              <>
                <span aria-hidden="true" className="toast-stack-shadow toast-stack-shadow--1" />
                <span aria-hidden="true" className="toast-stack-shadow toast-stack-shadow--2" />
                <span aria-hidden="true" className="toast-stack-shadow toast-stack-shadow--3" />
              </>
            )}
          </div>
        )
      })}
      {hasOverflow && (
        <button
          type="button"
          className="toast-overflow-pill"
          onClick={() => setExpandQueue(!isExpanded)}
          aria-expanded={isExpanded}
          aria-label={isExpanded ? t('common.toast.overflowCollapse') : t('common.toast.overflowExpand')}
        >
          <span className="toast-overflow-pill__count">{overflowCount}</span>
          <span className="toast-overflow-pill__label">
            {isExpanded ? t('common.toast.overflowCollapse') : t('common.toast.overflowMore', { count: overflowCount })}
          </span>
        </button>
      )}
    </div>
  )
}

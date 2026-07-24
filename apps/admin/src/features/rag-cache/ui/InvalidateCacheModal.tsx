import { useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useFocusTrap } from '../../../shared/lib/useFocusTrap'
import { useEscapeKey } from '../../../shared/lib/useEscapeKey'
import { useBodyOverflowLock } from '../../../shared/lib/useBodyOverflowLock'
import { formatPercent } from '../../../shared/lib/formatters'
import { OperationButton } from '../../../shared/ui'
import type { CacheStats } from '../types'

const CONFIRM_TOKEN = 'INVALIDATE'

interface InvalidateCacheModalProps {
  cacheStats: CacheStats | null
  isOpen: boolean
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}

export function InvalidateCacheModal({
  cacheStats,
  isOpen,
  onConfirm,
  onCancel,
  isPending,
}: InvalidateCacheModalProps) {
  const { t } = useTranslation()
  const modalRef = useRef<HTMLDivElement>(null)
  const inputId = useId()
  const helpId = useId()
  const [typedValue, setTypedValue] = useState('')

  useFocusTrap(modalRef, isOpen)
  useEscapeKey(isOpen, () => {
    setTypedValue('')
    onCancel()
  })
  useBodyOverflowLock(isOpen)

  if (!isOpen) return null

  const typedMatches = typedValue.trim() === CONFIRM_TOKEN

  function handleCancel() {
    setTypedValue('')
    onCancel()
  }

  // Pre-format the hit-rate string so the JSX below stays a single span.
  // formatPercent(undefined) → "-" but the modal previously rendered "0.0%"
  // when stats were missing; preserve that fallback by passing 0.
  const hitRateLabel = formatPercent(cacheStats?.hitRate ?? 0)
  const totalHits = cacheStats
    ? cacheStats.totalExactHits + cacheStats.totalSemanticHits
    : 0

  return createPortal(
    <div className="modal-overlay" onClick={handleCancel}>
      <div
        className="modal"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="invalidate-cache-modal-title"
        onClick={e => e.stopPropagation()}
      >
        <div
          className="modal-title"
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
        >
          <span id="invalidate-cache-modal-title">{t('ragCachePage.invalidate.title')}</span>
          <button
            type="button"
            className="detail-close-btn"
            onClick={handleCancel}
            aria-label={t('common.close')}
          >
            ×
          </button>
        </div>

        <div className="detail-panel detail-panel--compact" style={{ marginBottom: 'var(--space-3)' }}>
          <table className="table">
            <tbody>
              <tr>
                <td className="table-label">{t('ragCachePage.invalidate.currentHitRate')}</td>
                <td>
                  <strong>{hitRateLabel}</strong>{' '}
                  <span className="text-muted">→ {t('ragCachePage.invalidate.willReset')}</span>
                </td>
              </tr>
              <tr>
                <td className="table-label">
                  {t('ragCachePage.invalidate.totalCachedResponses')}
                </td>
                <td>
                  <strong>{totalHits}</strong>
                </td>
              </tr>
              <tr>
                <td className="table-label">{t('ragCachePage.invalidate.expectedImpact')}</td>
                <td className="text-secondary">
                  {t('ragCachePage.invalidate.expectedImpactDesc')}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          className="detail-panel detail-panel--compact"
          role="alert"
          style={{
            marginBottom: 'var(--space-3)',
            borderColor: 'var(--red)',
            color: 'var(--red)',
          }}
        >
          {t('ragCachePage.invalidate.irreversible')}
        </div>

        <div
          className="detail-panel detail-panel--compact"
          style={{ marginBottom: 'var(--space-3)', borderColor: 'var(--blue)' }}
        >
          <strong>{t('ragCachePage.invalidate.tipTitle')}</strong>
          <p className="text-secondary" style={{ margin: 'var(--space-1) 0 0 0' }}>
            {t('ragCachePage.invalidate.tipDesc')}
          </p>
        </div>

        <div className="form-group" style={{ marginBottom: 'var(--space-3)' }}>
          <label htmlFor={inputId}>
            {t('common.typeToConfirm')}{' '}
            <code style={{ fontFamily: 'var(--font-mono)' }}>{CONFIRM_TOKEN}</code>
          </label>
          <input
            id={inputId}
            type="text"
            value={typedValue}
            onChange={e => setTypedValue(e.target.value)}
            placeholder={CONFIRM_TOKEN}
            autoComplete="off"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            aria-required="true"
            aria-describedby={helpId}
            aria-invalid={!typedMatches}
            disabled={isPending}
            style={{ fontFamily: 'var(--font-mono)' }}
            onKeyDown={e => {
              if (e.key === 'Enter' && typedMatches && !isPending) {
                e.preventDefault()
                onConfirm()
              }
            }}
          />
          <p id={helpId} className="detail-note" style={{ marginTop: 'var(--space-2)' }}>
            {t('common.typeToConfirmHelp')}
          </p>
        </div>

        <div className="modal-actions">
          <OperationButton
            variant="secondary"
            onClick={handleCancel}
            disabled={isPending}
          >
            {t('ragCachePage.invalidate.cancel')}
          </OperationButton>
          <OperationButton
            variant="danger"
            onClick={onConfirm}
            isOperating={isPending}
            disabled={!typedMatches}
          >
            {t('ragCachePage.invalidate.execute')}
          </OperationButton>
        </div>
      </div>
    </div>,
    document.body,
  )
}

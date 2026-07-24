import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { DetailModal, OperationButton } from '../../../shared/ui'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useToastStore } from '../../../shared/store/toast.store'
import * as inputGuardApi from '../api'

interface Props {
  open: boolean
  initialOrder: string[]
  onClose: () => void
}

/**
 * Pipeline stage reorder modal — ↑↓ buttons instead of drag-n-drop for
 * keyboard accessibility and simpler behaviour.
 */
export function PipelineReorderModal({ open, initialOrder, onClose }: Props) {
  const { t } = useTranslation()
  const addToast = useToastStore((s) => s.addToast)
  const [order, setOrder] = useState<string[]>(initialOrder)

  const mutation = useMutation({
    mutationFn: () => inputGuardApi.reorderPipeline({ order }),
    onSuccess: (res) => {
      addToast({ type: 'success', message: res.note })
      onClose()
    },
    onError: (err: Error) =>
      addToast({ type: 'error', message: getErrorMessage(err) }),
  })

  function move(index: number, delta: number) {
    const target = index + delta
    if (target < 0 || target >= order.length) return
    const next = [...order]
    const tmp = next[index]
    next[index] = next[target]
    next[target] = tmp
    setOrder(next)
  }

  const changed = order.some((name, i) => name !== initialOrder[i])

  return (
    <DetailModal
      open={open}
      title={t('inputGuard.reorder.title')}
      onClose={onClose}
    >
      <p className="modal-message">{t('inputGuard.reorder.note')}</p>

      <div className="ig-reorder-list">
        {order.map((name, idx) => (
          <div key={name} className="ig-reorder-row">
            <span className="ig-reorder-row__index">{idx + 1}</span>
            <code className="ig-reorder-row__name">{name}</code>
            <div className="ig-reorder-row__move">
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={() => move(idx, -1)}
                disabled={idx === 0}
                aria-label={t('inputGuard.reorder.moveUp')}
              >
                ↑
              </button>
              <button
                type="button"
                className="btn btn-sm btn-secondary"
                onClick={() => move(idx, 1)}
                disabled={idx === order.length - 1}
                aria-label={t('inputGuard.reorder.moveDown')}
              >
                ↓
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="modal-actions">
        <OperationButton
          variant="secondary"
          onClick={onClose}
          disabled={mutation.isPending}
        >
          {t('common.cancel')}
        </OperationButton>
        <OperationButton
          variant="primary"
          onClick={() => mutation.mutate()}
          disabled={!changed}
          isOperating={mutation.isPending}
        >
          {t('common.save')}
        </OperationButton>
      </div>
    </DetailModal>
  )
}

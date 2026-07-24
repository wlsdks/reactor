import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LoadingSpinner } from '../../../shared/ui'
import type { AnalyzeFeedbackRequest } from '../types'

interface AnalyzeFeedbackDialogProps {
  onSubmit: (request: AnalyzeFeedbackRequest) => Promise<void>
  onClose: () => void
  onError: (message: string) => void
}

export function AnalyzeFeedbackDialog({ onSubmit, onClose, onError }: AnalyzeFeedbackDialogProps) {
  const { t } = useTranslation()
  const [templateId, setTemplateId] = useState('')
  const [maxSamples, setMaxSamples] = useState('50')
  const [analyzing, setAnalyzing] = useState(false)

  async function handleSubmit() {
    if (!templateId.trim()) {
      onError(t('promptLabPage.validation.templateRequired'))
      return
    }
    setAnalyzing(true)
    try {
      await onSubmit({
        templateId: templateId.trim(),
        maxSamples: Number(maxSamples) || undefined,
      })
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <dialog
      className="dialog-modal"
      open
      onClose={onClose}
    >
      <h3 className="modal-title">{t('promptLabPage.analyzeFeedback')}</h3>
      <div className="form-group">
        <label htmlFor="analyze-template-id">{t('promptLabPage.templateId')}</label>
        <input id="analyze-template-id" value={templateId} onChange={e => setTemplateId(e.target.value)} />
      </div>
      <div className="form-group">
        <label htmlFor="analyze-max-samples">{t('promptLabPage.maxSamples')}</label>
        <input
          id="analyze-max-samples"
          type="number"
          min={1}
          value={maxSamples}
          onChange={e => setMaxSamples(e.target.value)}
        />
      </div>
      <div className="modal-actions">
        <button className="btn btn-secondary" onClick={onClose}>
          {t('common.cancel')}
        </button>
        <button className="btn btn-primary" onClick={handleSubmit} disabled={analyzing}>
          {analyzing ? <LoadingSpinner size="sm" /> : t('promptLabPage.analyzeFeedback')}
        </button>
      </div>
    </dialog>
  )
}

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LoadingSpinner } from '../../../shared/ui'
import type { AutoOptimizeRequest } from '../types'

interface AutoOptimizeDialogProps {
  onSubmit: (request: AutoOptimizeRequest) => Promise<void>
  onClose: () => void
  onError: (message: string) => void
}

export function AutoOptimizeDialog({ onSubmit, onClose, onError }: AutoOptimizeDialogProps) {
  const { t } = useTranslation()
  const [templateId, setTemplateId] = useState('')
  const [candidateCount, setCandidateCount] = useState('3')
  const [judgeModel, setJudgeModel] = useState('')
  const [running, setRunning] = useState(false)

  async function handleSubmit() {
    if (!templateId.trim()) {
      onError(t('promptLabPage.validation.templateRequired'))
      return
    }
    setRunning(true)
    try {
      await onSubmit({
        templateId: templateId.trim(),
        candidateCount: Number(candidateCount) || undefined,
        judgeModel: judgeModel.trim() || undefined,
      })
    } finally {
      setRunning(false)
    }
  }

  return (
    <dialog
      className="dialog-modal"
      open
      onClose={onClose}
    >
      <h3 className="modal-title">{t('promptLabPage.autoOptimize')}</h3>
      <div className="form-group">
        <label htmlFor="optimize-template-id">{t('promptLabPage.templateId')}</label>
        <input id="optimize-template-id" value={templateId} onChange={e => setTemplateId(e.target.value)} />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="optimize-candidate-count">{t('promptLabPage.candidateCount')}</label>
          <input
            id="optimize-candidate-count"
            type="number"
            min={1}
            max={20}
            value={candidateCount}
            onChange={e => setCandidateCount(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label htmlFor="optimize-judge-model">{t('promptLabPage.judgeModel')}</label>
          <input id="optimize-judge-model" value={judgeModel} onChange={e => setJudgeModel(e.target.value)} />
        </div>
      </div>
      <div className="modal-actions">
        <button className="btn btn-secondary" onClick={onClose}>
          {t('common.cancel')}
        </button>
        <button className="btn btn-primary" onClick={handleSubmit} disabled={running}>
          {running ? <LoadingSpinner size="sm" /> : t('promptLabPage.autoOptimize')}
        </button>
      </div>
    </dialog>
  )
}

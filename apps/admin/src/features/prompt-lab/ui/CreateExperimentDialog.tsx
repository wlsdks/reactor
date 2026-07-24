import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DetailModal, HelpHint, LoadingSpinner } from '../../../shared/ui'
import type { PromptLabTestQueryRequest, CreatePromptExperimentRequest } from '../types'

interface CreateExperimentFormState {
  name: string
  description: string
  templateId: string
  baselineVersionId: string
  candidateVersionIdsRaw: string
  testQueriesRaw: string
  model: string
  judgeModel: string
  temperature: string
  repetitions: string
}

const emptyCreateForm: CreateExperimentFormState = {
  name: '',
  description: '',
  templateId: '',
  baselineVersionId: '',
  candidateVersionIdsRaw: '',
  testQueriesRaw: '[\n  {\n    "query": "How do I reset my password?"\n  }\n]',
  model: '',
  judgeModel: '',
  temperature: '0.3',
  repetitions: '1',
}

function parseCsv(raw: string): string[] {
  return raw
    .split(',')
    .map(item => item.trim())
    .filter(Boolean)
}

interface CreateExperimentDialogProps {
  open: boolean
  isPending: boolean
  onSubmit: (request: CreatePromptExperimentRequest) => void
  onClose: () => void
  onError: (message: string) => void
}

export function CreateExperimentDialog({ open, isPending, onSubmit, onClose, onError }: CreateExperimentDialogProps) {
  const { t } = useTranslation()
  const [form, setForm] = useState<CreateExperimentFormState>(emptyCreateForm)

  function handleSubmit() {
    if (!form.name.trim() || !form.templateId.trim() || !form.baselineVersionId.trim()) {
      onError(t('promptLabPage.validation.requiredBasics'))
      return
    }

    let testQueries: PromptLabTestQueryRequest[] = []
    try {
      const parsed = JSON.parse(form.testQueriesRaw) as unknown
      if (!Array.isArray(parsed) || parsed.length === 0) {
        throw new Error('testQueries must be a non-empty JSON array')
      }
      testQueries = parsed.map((row, index) => {
        if (!row || typeof row !== 'object') {
          throw new Error(`testQueries[${index}] must be an object`)
        }
        const candidate = row as PromptLabTestQueryRequest
        if (!candidate.query || !candidate.query.trim()) {
          throw new Error(`testQueries[${index}].query is required`)
        }
        return candidate
      })
    } catch {
      onError(t('promptLabPage.validation.testQueries'))
      return
    }

    const candidateVersionIds = parseCsv(form.candidateVersionIdsRaw)
    if (candidateVersionIds.length === 0) {
      onError(t('promptLabPage.validation.candidateVersions'))
      return
    }

    onSubmit({
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      templateId: form.templateId.trim(),
      baselineVersionId: form.baselineVersionId.trim(),
      candidateVersionIds,
      testQueries,
      model: form.model.trim() || undefined,
      judgeModel: form.judgeModel.trim() || undefined,
      temperature: Number(form.temperature),
      repetitions: Number(form.repetitions),
    })
  }

  return (
    <DetailModal
      open={open}
      title={t('promptLabPage.createExperiment')}
      onClose={onClose}
    >
      <div className="form-group">
        <label htmlFor="experiment-name">{t('common.name')}</label>
        <input id="experiment-name" value={form.name} onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))} />
      </div>
      <div className="form-group">
        <label htmlFor="experiment-description">{t('common.description')}</label>
        <textarea
          id="experiment-description"
          rows={2}
          value={form.description}
          onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
        />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="experiment-template-id">{t('promptLabPage.templateId')}</label>
          <input
            id="experiment-template-id"
            value={form.templateId}
            onChange={e => setForm(prev => ({ ...prev, templateId: e.target.value }))}
          />
        </div>
        <div className="form-group">
          <label htmlFor="experiment-baseline-version">{t('promptLabPage.baselineVersionId')}</label>
          <input
            id="experiment-baseline-version"
            value={form.baselineVersionId}
            onChange={e => setForm(prev => ({ ...prev, baselineVersionId: e.target.value }))}
          />
        </div>
      </div>
      <div className="form-group">
        <label htmlFor="experiment-candidate-ids">{t('promptLabPage.candidateVersionIds')}</label>
        <input
          id="experiment-candidate-ids"
          value={form.candidateVersionIdsRaw}
          onChange={e => setForm(prev => ({ ...prev, candidateVersionIdsRaw: e.target.value }))}
          placeholder={t('promptLabPage.candidateVersionIdsPlaceholder')}
        />
      </div>
      <div className="form-group">
        <label className="prompt-lab-form-label" htmlFor="experiment-test-queries">
          {t('promptLabPage.testQueriesJson')}
          <HelpHint label={t('promptLabPage.testQueriesJsonHelp')} />
        </label>
        <textarea
          id="experiment-test-queries"
          rows={8}
          value={form.testQueriesRaw}
          onChange={e => setForm(prev => ({ ...prev, testQueriesRaw: e.target.value }))}
        />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="experiment-model">{t('promptLabPage.modelOptional')}</label>
          <input id="experiment-model" value={form.model} onChange={e => setForm(prev => ({ ...prev, model: e.target.value }))} />
        </div>
        <div className="form-group">
          <label htmlFor="experiment-judge-model">{t('promptLabPage.judgeModelOptional')}</label>
          <input id="experiment-judge-model" value={form.judgeModel} onChange={e => setForm(prev => ({ ...prev, judgeModel: e.target.value }))} />
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="experiment-temperature">{t('promptLabPage.temperature')}</label>
          <input
            id="experiment-temperature"
            type="number"
            step="0.1"
            value={form.temperature}
            onChange={e => setForm(prev => ({ ...prev, temperature: e.target.value }))}
          />
        </div>
        <div className="form-group">
          <label htmlFor="experiment-repetitions">{t('promptLabPage.repetitions')}</label>
          <input
            id="experiment-repetitions"
            type="number"
            min={1}
            value={form.repetitions}
            onChange={e => setForm(prev => ({ ...prev, repetitions: e.target.value }))}
          />
        </div>
      </div>
      <div className="modal-actions">
        <button className="btn btn-secondary" onClick={onClose}>{t('common.cancel')}</button>
        <button className="btn btn-primary" onClick={handleSubmit} disabled={isPending}>
          {isPending ? <LoadingSpinner size="sm" /> : t('common.save')}
        </button>
      </div>
    </DetailModal>
  )
}

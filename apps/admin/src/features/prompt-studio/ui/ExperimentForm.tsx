import { useForm, Controller, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { LoadingSpinner, FieldStatusIndicator } from '../../../shared/ui'
import { useFieldStatus } from '../../../shared/lib/useFieldStatus'
import { experimentSchema, type ExperimentFormValues } from '../schema'
import type { VersionResponse, CreatePromptExperimentRequest } from '../types'

interface ExperimentFormProps {
  templateId: string
  templateName: string
  versions: VersionResponse[]
  onSubmit: (data: CreatePromptExperimentRequest) => void
  onCancel: () => void
  saving?: boolean
}

export function ExperimentForm({
  templateId,
  templateName,
  versions,
  onSubmit,
  onCancel,
  saving = false,
}: ExperimentFormProps) {
  const { t } = useTranslation()

  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isValid, isSubmitting, isValidating, dirtyFields },
  } = useForm<ExperimentFormValues>({
    resolver: zodResolver(experimentSchema),
    mode: 'onChange',
    defaultValues: {
      name: '',
      baselineVersionId: '',
      candidateVersionIds: [],
      testQueries: '',
      temperature: 0.7,
      repetitions: 3,
      evaluationConfig: {
        structuralEnabled: true,
        rulesEnabled: true,
        llmJudgeEnabled: true,
      },
    },
  })

  // useWatch instead of watch() — react-compiler-safe (watch returns a non-memoizable function ref).
  const nameVal = useWatch({ control, name: 'name' })
  const testQueriesVal = useWatch({ control, name: 'testQueries' })

  const nameStatus = useFieldStatus({
    value: nameVal,
    hasError: !!errors.name,
    isDirty: !!dirtyFields.name,
  })
  const testQueriesStatus = useFieldStatus({
    value: testQueriesVal,
    hasError: !!errors.testQueries,
    isDirty: !!dirtyFields.testQueries,
  })

  function handleFormSubmit(values: ExperimentFormValues) {
    const testQueries = values.testQueries
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0)
      .map((query) => ({ query }))

    const request: CreatePromptExperimentRequest = {
      name: values.name,
      templateId,
      baselineVersionId: values.baselineVersionId,
      candidateVersionIds: values.candidateVersionIds,
      testQueries,
      model: values.model === '' ? undefined : values.model,
      judgeModel: values.judgeModel === '' ? undefined : values.judgeModel,
      temperature: values.temperature,
      repetitions: values.repetitions,
      evaluationConfig: values.evaluationConfig,
    }

    onSubmit(request)
  }

  // Helper: only render hint when key resolves to something other than itself.
  const hint = (key: string): string | null => {
    const translated = t(key)
    return translated && translated !== key ? translated : null
  }

  const submitDisabled = !isValid || isValidating || saving || isSubmitting
  const versionState = (status: VersionResponse['status']) => {
    if (status === 'ACTIVE') return t('promptStudio.versionStatus.active')
    if (status === 'DRAFT') return t('promptStudio.versionStatus.draft')
    if (status === 'ARCHIVED') return t('promptStudio.versionStatus.archived')
    return t('promptStudio.versionStatus.unknown')
  }

  return (
    <form onSubmit={(event) => void handleSubmit(handleFormSubmit)(event)} className="experiment-form" noValidate>
      <div className="form-group">
        <label htmlFor="studio-experiment-name">
          {t('promptStudio.experimentName')}
          <span className="form-label-required" aria-hidden="true">*</span>
          <FieldStatusIndicator status={nameStatus} />
        </label>
        <input
          id="studio-experiment-name"
          aria-required="true"
          {...register('name')}
          placeholder={t('promptStudio.experimentNamePlaceholder')}
          aria-invalid={!!errors.name}
          aria-describedby={errors.name ? 'experiment-name-error' : 'experiment-name-hint'}
        />
        {hint('promptStudio.hint.experimentName') && (
          <p id="experiment-name-hint" className="form-hint">{hint('promptStudio.hint.experimentName')}</p>
        )}
        {errors.name && <p id="experiment-name-error" className="form-error" role="alert">{errors.name.message}</p>}
      </div>

      <div className="form-group">
        <label htmlFor="studio-experiment-template">{t('promptStudio.template')}</label>
        <input id="studio-experiment-template" value={templateName} readOnly className="input-readonly" />
      </div>

      <div className="form-group">
        <label>{t('promptStudio.selectVersions')}</label>
        <p className="detail-note">{t('promptStudio.selectVersionsGuide')}</p>

        <Controller
          name="baselineVersionId"
          control={control}
          render={({ field: baselineField }) => (
            <Controller
              name="candidateVersionIds"
              control={control}
              render={({ field: candidateField }) => (
                <div className="version-select-list">
                  {versions.map((version) => {
                    const isBaseline = baselineField.value === version.id
                    const isCandidate = candidateField.value.includes(version.id)

                    return (
                      <div
                        key={version.id}
                        className={`version-select-card${isBaseline ? ' baseline' : ''}${isCandidate ? ' candidate' : ''}`}
                      >
                        <div className="version-select-card-header">
                          <span className="version-number">{t('promptStudio.versionLabel', { version: version.version })}</span>
                          <span className="version-choice-state">{versionState(version.status)}</span>
                        </div>
                        <div className="version-preview">
                          {version.content.slice(0, 120)}
                          {version.content.length > 120 ? '...' : ''}
                        </div>
                        <div className="version-select-actions">
                          <label className="radio-label">
                            <input
                              type="radio"
                              name="baseline"
                              value={version.id}
                              checked={isBaseline}
                              onChange={() => {
                                baselineField.onChange(version.id)
                                // Remove from candidates if selected as baseline
                                if (isCandidate) {
                                  candidateField.onChange(
                                    candidateField.value.filter((id: string) => id !== version.id)
                                  )
                                }
                              }}
                            />
                            {t('promptStudio.baseline')}
                          </label>
                          <label className="checkbox-label">
                            <input
                              type="checkbox"
                              value={version.id}
                              checked={isCandidate}
                              disabled={isBaseline}
                              onChange={(e) => {
                                if (e.target.checked) {
                                  candidateField.onChange([...candidateField.value, version.id])
                                } else {
                                  candidateField.onChange(
                                    candidateField.value.filter((id: string) => id !== version.id)
                                  )
                                }
                              }}
                            />
                            {t('promptStudio.candidate')}
                          </label>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            />
          )}
        />
        {errors.baselineVersionId && (
          <p id="experiment-baselineVersionId-error" className="form-error" role="alert">{errors.baselineVersionId.message}</p>
        )}
        {errors.candidateVersionIds && (
          <p id="experiment-candidateVersionIds-error" className="form-error" role="alert">{errors.candidateVersionIds.message}</p>
        )}
      </div>

      <div className="form-group">
        <label htmlFor="studio-experiment-queries">
          {t('promptStudio.testQueries')}
          <span className="form-label-required" aria-hidden="true">*</span>
          <FieldStatusIndicator status={testQueriesStatus} />
        </label>
        <p className="detail-note">{t('promptStudio.testQueriesGuide')}</p>
        <textarea
          id="studio-experiment-queries"
          aria-required="true"
          {...register('testQueries')}
          rows={6}
          placeholder={t('promptStudio.testQueriesPlaceholder')}
          aria-invalid={!!errors.testQueries}
          aria-describedby={errors.testQueries ? 'experiment-testQueries-error' : 'experiment-testQueries-hint'}
        />
        {hint('promptStudio.hint.testQueries') && (
          <p id="experiment-testQueries-hint" className="form-hint">{hint('promptStudio.hint.testQueries')}</p>
        )}
        {errors.testQueries && (
          <p id="experiment-testQueries-error" className="form-error" role="alert">{errors.testQueries.message}</p>
        )}
      </div>

      <div className="form-actions">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onCancel}
          disabled={saving || isSubmitting}
        >
          {t('common.cancel')}
        </button>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={submitDisabled}
        >
          {saving || isSubmitting ? <LoadingSpinner size="sm" /> : t('promptStudio.runExperiment')}
        </button>
      </div>
    </form>
  )
}

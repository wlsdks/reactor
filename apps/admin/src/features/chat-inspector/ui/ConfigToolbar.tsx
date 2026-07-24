import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { HelpHint } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useToastStore } from '../../../shared/store/toast.store'
import { resolveApiError } from '../../../shared/lib/getErrorMessage'
import { listPersonas } from '../../personas'
import { listModels } from '../../sessions'
import { listTemplates } from '../../prompts'
import { formatModelName } from '../modelName'
import './ConfigToolbar.css'

interface ConfigToolbarProps {
  personaId: string
  modelId: string
  templateId: string
  onPersonaChange: (id: string) => void
  onModelChange: (id: string) => void
  onTemplateChange: (id: string) => void
}

const STALE_TIME = 5 * 60 * 1000

export function ConfigToolbar({
  personaId,
  modelId,
  templateId,
  onPersonaChange,
  onModelChange,
  onTemplateChange,
}: ConfigToolbarProps) {
  const { t } = useTranslation()

  const personasQuery = useQuery({
    queryKey: queryKeys.personas.list(),
    queryFn: listPersonas,
    staleTime: STALE_TIME,
  })

  const modelsQuery = useQuery({
    queryKey: queryKeys.sessions.models(),
    queryFn: listModels,
    staleTime: STALE_TIME,
  })

  // Cap retries to 1 (default is 2) so a sustained backend outage on
  // `/api/prompt-templates` does not flood the console with repeated 5xx
  // errors. The recovery UI below handles the failed state gracefully.
  const templatesQuery = useQuery({
    queryKey: queryKeys.prompts.list(),
    queryFn: listTemplates,
    staleTime: STALE_TIME,
    retry: 1,
    retryDelay: 800,
  })

  const activePersonas = personasQuery.data?.filter((p) => p.isActive) ?? []
  const models = modelsQuery.data?.models ?? []
  const failedQueries = [personasQuery, modelsQuery, templatesQuery].filter((query) => query.isError)
  const resolvedFailures = failedQueries.map((query) => resolveApiError(query.error))
  // Permission is the most actionable shared cause when cached query errors
  // contain a mixture of transport failures and a fresh 403 response.
  const resolvedFailure = resolvedFailures.find((failure) => failure.raw?.status === 403)
    ?? resolvedFailures[0]
    ?? null

  async function retryFailedQueries() {
    const results = await Promise.all([
      personasQuery.isError ? personasQuery.refetch() : null,
      modelsQuery.isError ? modelsQuery.refetch() : null,
      templatesQuery.isError ? templatesQuery.refetch() : null,
    ])
    if (results.every((result) => result?.isError !== true)) {
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.refreshed') })
    }
  }

  // Auto-select meaningful defaults once queries resolve.
  // Selectors otherwise default to "None" even when real defaults exist,
  // which reads as "no selection" rather than a sensible baseline.
  // We only apply a default if the current value is empty so user overrides
  // (including explicit "None" via the last option) are preserved.
  const personaDefaultApplied = useRef(false)
  useEffect(() => {
    if (personaDefaultApplied.current) return
    if (!personasQuery.isSuccess) return
    if (personaId) {
      personaDefaultApplied.current = true
      return
    }
    if (activePersonas.length === 0) return
    const fallback = activePersonas.find((p) => p.isDefault) ?? activePersonas[0]
    personaDefaultApplied.current = true
    onPersonaChange(fallback.id)
  }, [personasQuery.isSuccess, personaId, activePersonas, onPersonaChange])

  const modelDefaultApplied = useRef(false)
  useEffect(() => {
    if (modelDefaultApplied.current) return
    if (!modelsQuery.isSuccess) return
    if (modelId) {
      modelDefaultApplied.current = true
      return
    }
    if (models.length === 0) return
    const fallback = models.find((m) => m.isDefault) ?? models[0]
    modelDefaultApplied.current = true
    onModelChange(fallback.name)
  }, [modelsQuery.isSuccess, modelId, models, onModelChange])

  return (
    <div className="config-toolbar">
      {resolvedFailure ? (
        <div className="config-toolbar__notice" role="status">
          <div>
            <strong>{resolvedFailure.raw?.status === 403
              ? t('chatInspector.config.permissionTitle')
              : t('chatInspector.config.unavailableTitle')}</strong>
            <p>{resolvedFailure.raw?.status === 403
              ? t('chatInspector.config.permissionDescription')
              : t('chatInspector.config.unavailableDescription')}</p>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => void retryFailedQueries()}>
            {t('chatInspector.config.retry')}
          </button>
        </div>
      ) : null}
      {/* Persona dropdown */}
      <div className="config-toolbar__field">
        <div className="config-toolbar__label-row">
          <label className="config-toolbar__label" htmlFor="ci-persona">
            {t('chatInspector.config.persona')}
          </label>
          <HelpHint
            title={t('chatInspector.help.personaTitle')}
            label={t('chatInspector.help.persona')}
            placement="right"
          />
        </div>
        {personasQuery.isError ? (
          <span className="config-toolbar__field-unavailable">{t('chatInspector.config.unavailableValue')}</span>
        ) : (
          <select
            id="ci-persona"
            className={`config-toolbar__select${personaId === '' ? ' config-toolbar__select--placeholder' : ''}`}
            value={personaId}
            onChange={(e) => onPersonaChange(e.target.value)}
          >
            {activePersonas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.isDefault ? ` ${t('chatInspector.config.default')}` : ''}
              </option>
            ))}
            <option value="">{t('chatInspector.config.nonePersona')}</option>
          </select>
        )}
      </div>

      {/* Model dropdown */}
      <div className="config-toolbar__field">
        <div className="config-toolbar__label-row">
          <label className="config-toolbar__label" htmlFor="ci-model">
            {t('chatInspector.config.model')}
          </label>
          <HelpHint
            title={t('chatInspector.help.modelTitle')}
            label={t('chatInspector.help.model')}
            placement="right"
          />
        </div>
        {modelsQuery.isError ? (
          <span className="config-toolbar__field-unavailable">{t('chatInspector.config.unavailableValue')}</span>
        ) : (
          <select
            id="ci-model"
            className={`config-toolbar__select${modelId === '' ? ' config-toolbar__select--placeholder' : ''}`}
            value={modelId}
            onChange={(e) => onModelChange(e.target.value)}
          >
            {models.map((m) => (
              <option key={m.name} value={m.name}>
                {formatModelName(m.name)}
                {m.isDefault ? ` ${t('chatInspector.config.default')}` : ''}
              </option>
            ))}
            <option value="">{t('chatInspector.config.noneModel')}</option>
          </select>
        )}
      </div>

      {/* Prompt Template dropdown */}
      <div className="config-toolbar__field">
        <div className="config-toolbar__label-row">
          <label className="config-toolbar__label" htmlFor="ci-template">
            {t('chatInspector.config.template')}
          </label>
          <HelpHint
            title={t('chatInspector.help.templateTitle')}
            label={t('chatInspector.help.template')}
            placement="right"
          />
        </div>
        {templatesQuery.isError ? (
          <span className="config-toolbar__field-unavailable">{t('chatInspector.config.unavailableValue')}</span>
        ) : (
          <select
            id="ci-template"
            className={`config-toolbar__select${templateId === '' ? ' config-toolbar__select--placeholder' : ''}`}
            value={templateId}
            onChange={(e) => onTemplateChange(e.target.value)}
          >
            {templatesQuery.data?.map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {tpl.name}
              </option>
            ))}
            <option value="">{t('chatInspector.config.noneTemplate')}</option>
          </select>
        )}
      </div>
    </div>
  )
}

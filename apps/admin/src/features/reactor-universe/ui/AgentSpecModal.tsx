import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useToastStore } from '../../../shared/store/toast.store'
import { DetailModal, OperationButton } from '../../../shared/ui'
import { SectionErrorBoundary } from '../../../shared/ui/SectionErrorBoundary'
import * as agentApi from '../api'
import type { AgentSpec } from '../types'
import { agentSpecSchema, type AgentSpecFormValues } from '../schema'
import { SystemPromptSection } from './SystemPromptSection'

export function AgentSpecModal({
  agent,
  onClose,
}: {
  agent: AgentSpec | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const isEdit = !!agent
  const [technicalError, setTechnicalError] = useState<string | null>(null)

  const form = useForm<AgentSpecFormValues>({
    resolver: zodResolver(agentSpecSchema),
    defaultValues: {
      name: agent?.name ?? '',
      description: agent?.description ?? '',
      toolNames: agent?.toolNames.join(', ') ?? '',
      keywords: agent?.keywords.join(', ') ?? '',
      systemPrompt: '',
      mode: (agent?.mode as AgentSpecFormValues['mode']) ?? 'REACT',
      enabled: agent?.enabled ?? true,
    },
  })
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = form

  const mutation = useMutation({
    mutationFn: async (values: AgentSpecFormValues) => {
      const sharedPayload = {
        name: values.name,
        description: values.description,
        toolNames: values.toolNames.split(',').map((s) => s.trim()).filter(Boolean),
        keywords: values.keywords.split(',').map((s) => s.trim()).filter(Boolean),
        mode: values.mode,
        enabled: values.enabled,
      }
      if (isEdit && agent) {
        // List responses intentionally do not include the resolved answer
        // principles. Editing ordinary role fields must not imply that an
        // unseen, audit-protected value will be replaced.
        return agentApi.updateAgentSpec(agent.id, sharedPayload)
      }
      return agentApi.createAgentSpec({
        ...sharedPayload,
        systemPrompt: values.systemPrompt || undefined,
      })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.reactorUniverse.all() })
      // Edits to a spec may rewrite the resolved system prompt, so the
      // staleTime: Infinity cache must be cleared to force the next reveal
      // to re-fetch (and write a fresh audit log entry).
      if (isEdit && agent) {
        void queryClient.invalidateQueries({
          queryKey: queryKeys.reactorUniverse.systemPrompt(agent.id),
        })
      }
      addToast({
        type: 'success',
        message: isEdit ? t('reactorUniverse.updated') : t('reactorUniverse.created'),
      })
      onClose()
    },
    onError: (err: unknown) => {
      setTechnicalError(getErrorMessage(err))
      setError('root', { message: t('reactorUniverse.saveUnavailable') })
    },
  })

  return (
    <DetailModal
      open
      title={isEdit ? t('reactorUniverse.editAgent') : t('reactorUniverse.createAgent')}
      onClose={onClose}
    >
      <form
        onSubmit={(event) => {
          void handleSubmit((values) => mutation.mutate(values))(event)
        }}
        noValidate
      >
        <div className="modal-body">
          {errors.root && (
            <div
              id="agent-spec-form-error"
              className="alert alert-error"
              role="alert"
            >
              <span>{errors.root.message}</span>
              {technicalError ? (
                <details className="agent-spec-form__technical-error">
                  <summary>{t('common.technicalDetails')}</summary>
                  <code>{technicalError}</code>
                </details>
              ) : null}
            </div>
          )}

          <div className="form-group">
            <label className="form-label" htmlFor="agent-spec-name">
              {t('reactorUniverse.form.name')}
            </label>
            <input
              id="agent-spec-name"
              className="form-input"
              {...register('name')}
              aria-invalid={!!errors.name}
              aria-describedby={errors.name ? 'agent-spec-name-error' : undefined}
              placeholder={t('reactorUniverse.form.namePlaceholder')}
            />
            {errors.name && (
              <span
                id="agent-spec-name-error"
                className="form-error"
                role="alert"
              >
                {errors.name.message}
              </span>
            )}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="agent-spec-description">
              {t('reactorUniverse.form.description')}
            </label>
            <textarea
              id="agent-spec-description"
              className="form-input"
              rows={2}
              {...register('description')}
              aria-invalid={!!errors.description}
              aria-describedby={errors.description ? 'agent-spec-description-error' : undefined}
              placeholder={t('reactorUniverse.form.descriptionPlaceholder')}
            />
            {errors.description && (
              <span
                id="agent-spec-description-error"
                className="form-error"
                role="alert"
              >
                {errors.description.message}
              </span>
            )}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="agent-spec-keywords">
              {t('reactorUniverse.form.keywords')}
            </label>
            <input
              id="agent-spec-keywords"
              className="form-input"
              {...register('keywords')}
              aria-invalid={!!errors.keywords}
              aria-describedby={
                errors.keywords ? 'agent-spec-keywords-error' : 'agent-spec-keywords-hint'
              }
              placeholder={t('reactorUniverse.form.keywordsPlaceholder')}
            />
            {errors.keywords ? (
              <span
                id="agent-spec-keywords-error"
                className="form-error"
                role="alert"
              >
                {errors.keywords.message}
              </span>
            ) : (
              <span id="agent-spec-keywords-hint" className="form-hint">
                {t('reactorUniverse.form.keywordsHint')}
              </span>
            )}
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="agent-spec-tool-names">
              {t('reactorUniverse.form.toolNames')}
            </label>
            <input
              id="agent-spec-tool-names"
              className="form-input"
              {...register('toolNames')}
              aria-invalid={!!errors.toolNames}
              aria-describedby={
                errors.toolNames ? 'agent-spec-tool-names-error' : 'agent-spec-tool-names-hint'
              }
              placeholder={t('reactorUniverse.form.toolNamesPlaceholder')}
            />
            {errors.toolNames ? (
              <span
                id="agent-spec-tool-names-error"
                className="form-error"
                role="alert"
              >
                {errors.toolNames.message}
              </span>
            ) : (
              <span id="agent-spec-tool-names-hint" className="form-hint">
                {t('reactorUniverse.form.toolNamesHint')}
              </span>
            )}
          </div>

          {!isEdit && (
            <div className="form-group">
              <label className="form-label" htmlFor="agent-spec-system-prompt">
                {t('reactorUniverse.form.systemPrompt')}
              </label>
              <textarea
                id="agent-spec-system-prompt"
                className="form-input"
                rows={4}
                {...register('systemPrompt')}
                aria-invalid={!!errors.systemPrompt}
                aria-describedby={
                  errors.systemPrompt ? 'agent-spec-system-prompt-error' : undefined
                }
                placeholder={t('reactorUniverse.form.systemPromptPlaceholder')}
              />
              {errors.systemPrompt && (
                <span
                  id="agent-spec-system-prompt-error"
                  className="form-error"
                  role="alert"
                >
                  {errors.systemPrompt.message}
                </span>
              )}
            </div>
          )}

          <div className="form-row">
            <div className="form-group">
              <label className="form-label" htmlFor="agent-spec-mode">
                {t('reactorUniverse.form.mode')}
              </label>
              <select
                id="agent-spec-mode"
                className="form-input"
                {...register('mode')}
                aria-invalid={!!errors.mode}
              >
                <option value="REACT">{t('reactorUniverse.modes.REACT')}</option>
                <option value="STANDARD">{t('reactorUniverse.modes.STANDARD')}</option>
                <option value="PLAN_EXECUTE">{t('reactorUniverse.modes.PLAN_EXECUTE')}</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label form-label--checkbox">
                <input type="checkbox" {...register('enabled')} />
                {t('reactorUniverse.form.enabled')}
              </label>
            </div>
          </div>

          {isEdit && agent && (
            <SectionErrorBoundary name="agent-spec-system-prompt">
              <SystemPromptSection specId={agent.id} />
            </SectionErrorBoundary>
          )}
        </div>

        <div className="modal-actions">
          <OperationButton type="button" variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </OperationButton>
          <OperationButton type="submit" isOperating={isSubmitting || mutation.isPending}>
            {isEdit ? t('common.save') : t('reactorUniverse.createAgent')}
          </OperationButton>
        </div>
      </form>
    </DetailModal>
  )
}

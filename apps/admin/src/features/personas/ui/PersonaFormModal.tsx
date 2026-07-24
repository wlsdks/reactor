import { useEffect, useRef, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { ChevronRight } from 'lucide-react'
import { DetailModal, DraftRecoveryBanner, FieldStatusIndicator, OperationButton } from '../../../shared/ui'
import { useFieldStatus } from '../../../shared/lib/useFieldStatus'
import { useFormDraft } from '../../../shared/lib/useFormDraft'
import { useFormFirstFieldFocus } from '../../../shared/lib/useFormFirstFieldFocus'
import * as personasApi from '../api'
import * as promptsApi from '../../prompts/api'
import type { TemplateResponse } from '../../prompts'
import type { PersonaResponse } from '../types'
import { personaFormSchema, type PersonaFormValues } from '../schema'

interface PersonaFormModalProps {
  open: boolean
  onClose: () => void
  onSaved: (persona: PersonaResponse) => void
  persona?: PersonaResponse | null
}

const CREATE_DEFAULTS: PersonaFormValues = {
  name: '',
  systemPrompt: '',
  icon: '',
  description: '',
  responseGuideline: '',
  welcomeMessage: '',
  promptTemplateId: '',
  isDefault: false,
  isActive: true,
}

function personaToFormValues(persona: PersonaResponse): PersonaFormValues {
  return {
    name: persona.name,
    systemPrompt: persona.systemPrompt,
    icon: persona.icon ?? '',
    description: persona.description ?? '',
    responseGuideline: persona.responseGuideline ?? '',
    welcomeMessage: persona.welcomeMessage ?? '',
    promptTemplateId: persona.promptTemplateId ?? '',
    isDefault: persona.isDefault,
    isActive: persona.isActive,
  }
}

export function PersonaFormModal({ open, onClose, onSaved, persona }: PersonaFormModalProps) {
  const { t } = useTranslation()
  const isEditMode = !!persona
  const [templates, setTemplates] = useState<TemplateResponse[]>([])
  const formRef = useRef<HTMLFormElement>(null)
  useFormFirstFieldFocus(formRef, open)

  const {
    register,
    handleSubmit,
    setError,
    control,
    reset,
    formState: { errors, isSubmitting, dirtyFields },
  } = useForm<PersonaFormValues>({
    resolver: zodResolver(personaFormSchema),
    mode: 'onChange',
    defaultValues: persona ? personaToFormValues(persona) : CREATE_DEFAULTS,
  })

  const nameValue = useWatch({ control, name: 'name' })
  const systemPromptValue = useWatch({ control, name: 'systemPrompt' })

  // Auto-save the entire form to localStorage so an accidental modal close does
  // not lose work. Use a per-record key in edit mode so concurrent create + edit
  // sessions don't collide.
  const draftValues = useWatch({ control })
  const draftStorageKey = persona ? `personas:edit:${persona.id}` : 'personas:create'
  const {
    recoveredDraft,
    recoveredAt,
    acceptRecovery,
    dismissRecovery,
    clearDraft,
  } = useFormDraft<Partial<PersonaFormValues>>({
    storageKey: draftStorageKey,
    values: draftValues as Partial<PersonaFormValues>,
    enabled: open,
  })

  const nameStatus = useFieldStatus({
    value: nameValue,
    hasError: !!errors.name,
    isDirty: !!dirtyFields.name,
  })
  const systemPromptStatus = useFieldStatus({
    value: systemPromptValue,
    hasError: !!errors.systemPrompt,
    isDirty: !!dirtyFields.systemPrompt,
  })

  // Reset form when persona prop changes (switching between create/edit or different persona)
  useEffect(() => {
    if (open) {
      reset(persona ? personaToFormValues(persona) : CREATE_DEFAULTS)
    }
  }, [persona, open, reset])

  // Load prompt templates
  useEffect(() => {
    if (!open) return
    let active = true
    promptsApi.listTemplates()
      .then(items => { if (active) setTemplates(items) })
      .catch(() => { if (active) setTemplates([]) })
    return () => { active = false }
  }, [open])

  async function onSubmit(values: PersonaFormValues) {
    try {
      const payload = {
        name: values.name,
        systemPrompt: values.systemPrompt,
        icon: values.icon || null,
        description: values.description || null,
        responseGuideline: values.responseGuideline || null,
        welcomeMessage: values.welcomeMessage || null,
        promptTemplateId: values.promptTemplateId || null,
        isDefault: values.isDefault,
        isActive: values.isActive,
      }

      const response = isEditMode
        ? await personasApi.updatePersona(persona.id, payload)
        : await personasApi.createPersona(payload)

      clearDraft()
      onSaved(response)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      setError('root', { message })
    }
  }

  const title = isEditMode
    ? t('personas.editModal.title')
    : t('personas.createModal.title')

  const submitLabel = isEditMode
    ? t('common.save')
    : t('personas.createModal.submit')

  return (
    <DetailModal open={open} title={title} onClose={onClose}>
      <DraftRecoveryBanner
        open={!!recoveredDraft}
        savedAt={recoveredAt ?? undefined}
        onAccept={() => {
          if (recoveredDraft) {
            // Merge over the active defaults so missing fields keep their
            // current shape (recovered drafts may be partial).
            reset({
              ...(persona ? personaToFormValues(persona) : CREATE_DEFAULTS),
              ...recoveredDraft,
            } as PersonaFormValues)
          }
          acceptRecovery()
        }}
        onDismiss={dismissRecovery}
      />
      {errors.root && (
        <div className="alert alert-error" role="alert">{errors.root.message}</div>
      )}

      <form className="persona-form" ref={formRef} onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="form-group">
          <label htmlFor="persona-name">
            {t('personas.name')}
            <span className="form-label-required" aria-hidden="true">*</span>
            <FieldStatusIndicator status={nameStatus} />
          </label>
          <input
            id="persona-name"
            aria-required="true"
            {...register('name')}
            placeholder={t('personas.namePlaceholder')}
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? 'persona-name-error' : undefined}
          />
          {errors.name && (
            <p id="persona-name-error" className="form-error" role="alert">{errors.name.message}</p>
          )}
        </div>

        {/* System Prompt */}
        <div className="form-group">
          <label htmlFor="persona-system-prompt">
            {t('personas.systemPrompt')}
            <span className="form-label-required" aria-hidden="true">*</span>
            <FieldStatusIndicator status={systemPromptStatus} />
          </label>
          <p id="persona-systemPrompt-hint" className="detail-note" style={{ marginTop: 0 }}>
            {t('personas.systemPromptHelp')}
          </p>
          <textarea
            id="persona-system-prompt"
            rows={5}
            aria-required="true"
            {...register('systemPrompt')}
            placeholder={t('personas.systemPromptPlaceholder')}
            aria-invalid={!!errors.systemPrompt}
            aria-describedby={errors.systemPrompt ? 'persona-systemPrompt-error' : 'persona-systemPrompt-hint'}
          />
          {errors.systemPrompt && (
            <p id="persona-systemPrompt-error" className="form-error" role="alert">{errors.systemPrompt.message}</p>
          )}
        </div>

        <details className="persona-form__optional">
          <summary>
            <ChevronRight className="persona-form__optional-icon" aria-hidden="true" />
            <span>
              <strong>{t('personas.formSection.details')}</strong>
              <small>{t('personas.formSection.detailsDescription')}</small>
            </span>
          </summary>

          <div className="form-group">
          <label htmlFor="persona-description">{t('personas.purposeNote')}</label>
          <p className="detail-note" style={{ marginTop: 0 }}>
            {t('personas.formSection.descriptionHelp')}
          </p>
          <input
            id="persona-description"
            {...register('description')}
            placeholder={t('personas.descriptionPlaceholder')}
            aria-invalid={!!errors.description}
            aria-describedby={errors.description ? 'persona-description-error' : undefined}
          />
          {errors.description && (
            <p id="persona-description-error" className="form-error" role="alert">{errors.description.message}</p>
          )}
          </div>

          <div className="form-group">
          <label htmlFor="persona-guideline">{t('personas.responseGuideline')}</label>
          <p className="detail-note" style={{ marginTop: 0 }}>
            {t('personas.formSection.guidelineHelp')}
          </p>
          <textarea
            id="persona-guideline"
            rows={3}
            {...register('responseGuideline')}
            placeholder={t('personas.responseGuidelinePlaceholder')}
            aria-invalid={!!errors.responseGuideline}
            aria-describedby={errors.responseGuideline ? 'persona-responseGuideline-error' : undefined}
          />
          {errors.responseGuideline && (
            <p id="persona-responseGuideline-error" className="form-error" role="alert">{errors.responseGuideline.message}</p>
          )}
          </div>

          <div className="form-group">
          <label htmlFor="persona-welcome">{t('personas.welcomeMessage')}</label>
          <p className="detail-note" style={{ marginTop: 0 }}>
            {t('personas.formSection.welcomeHelp')}
          </p>
          <input
            id="persona-welcome"
            {...register('welcomeMessage')}
            placeholder={t('personas.welcomeMessagePlaceholder')}
            aria-invalid={!!errors.welcomeMessage}
            aria-describedby={errors.welcomeMessage ? 'persona-welcomeMessage-error' : undefined}
          />
          {errors.welcomeMessage && (
            <p id="persona-welcomeMessage-error" className="form-error" role="alert">{errors.welcomeMessage.message}</p>
          )}
          </div>

          <div className="form-group">
          <label htmlFor="persona-template">{t('personas.linkedPromptTemplate')}</label>
          <p className="detail-note" style={{ marginTop: 0 }}>
            {t('personas.formSection.templateHelp')}
          </p>
          <select id="persona-template" {...register('promptTemplateId')}>
            <option value="">{t('personas.linkedPromptTemplateNone')}</option>
            {templates.map(tmpl => (
              <option key={tmpl.id} value={tmpl.id}>{tmpl.name}</option>
            ))}
          </select>
          </div>

          <div className="form-row">
            <div className="form-group form-check">
              <input type="checkbox" id="persona-form-isDefault" {...register('isDefault')} />
              <label htmlFor="persona-form-isDefault">{t('personas.setDefault')}</label>
            </div>
            <div className="form-group form-check">
              <input type="checkbox" id="persona-form-isActive" {...register('isActive')} />
              <label htmlFor="persona-form-isActive">{t('personas.active')}</label>
            </div>
          </div>
        </details>

        {/* Actions */}
        <div className="modal-actions">
          <OperationButton
            variant="secondary"
            onClick={onClose}
            disabled={isSubmitting}
          >
            {t('common.cancel')}
          </OperationButton>
          <OperationButton
            type="submit"
            variant="primary"
            isOperating={isSubmitting}
          >
            {submitLabel}
          </OperationButton>
        </div>
      </form>
    </DetailModal>
  )
}

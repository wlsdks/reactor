import { useRef } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useToastStore } from '../../../shared/store/toast.store'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { DraftRecoveryBanner, FieldStatusIndicator, HelpHint, SideDrawer } from '../../../shared/ui'
import { useFieldStatus } from '../../../shared/lib/useFieldStatus'
import { useFormDraft } from '../../../shared/lib/useFormDraft'
import { useFormFirstFieldFocus } from '../../../shared/lib/useFormFirstFieldFocus'
import { slackBotCreateSchema, slackBotUpdateSchema } from '../schema'
import type { SlackBotCreateFormValues, SlackBotUpdateFormValues } from '../schema'
import type { SlackBot, CreateSlackBotRequest, UpdateSlackBotRequest } from '../types'
import * as slackBotApi from '../api'

interface SlackBotFormModalProps {
  bot: SlackBot | null
  onClose: () => void
}

export function SlackBotFormModal({ bot, onClose }: SlackBotFormModalProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const isEdit = !!bot
  const formRef = useRef<HTMLFormElement>(null)
  // Modal is mounted only while open, so trigger focus on first mount.
  useFormFirstFieldFocus(formRef, true)

  const createForm = useForm<SlackBotCreateFormValues>({
    resolver: zodResolver(slackBotCreateSchema),
    mode: 'onChange',
    defaultValues: {
      name: '',
      workspace: '',
      botToken: '',
      appToken: '',
      signingSecret: '',
      description: '',
      isActive: true,
    },
  })

  const updateForm = useForm<SlackBotUpdateFormValues>({
    resolver: zodResolver(slackBotUpdateSchema),
    mode: 'onChange',
    defaultValues: {
      name: bot?.name ?? '',
      workspace: bot?.workspace ?? '',
      botToken: '',
      appToken: '',
      signingSecret: '',
      description: bot?.description ?? '',
      isActive: bot?.isActive ?? true,
    },
  })

  const form = isEdit ? updateForm : createForm
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, isValid, isValidating, dirtyFields },
    setError,
  } = form

  // useWatch (react-compiler-safe). The two branches are typed independently
  // because create and update schemas differ (token fields required vs optional);
  // we always call both hooks (rules of hooks) and pick the active one.
  const createNameVal = useWatch({ control: createForm.control, name: 'name' })
  const createWorkspaceVal = useWatch({ control: createForm.control, name: 'workspace' })
  const createBotTokenVal = useWatch({ control: createForm.control, name: 'botToken' })
  const createAppTokenVal = useWatch({ control: createForm.control, name: 'appToken' })
  const createSigningSecretVal = useWatch({ control: createForm.control, name: 'signingSecret' })
  const createDescriptionVal = useWatch({ control: createForm.control, name: 'description' })

  const updateNameVal = useWatch({ control: updateForm.control, name: 'name' })
  const updateWorkspaceVal = useWatch({ control: updateForm.control, name: 'workspace' })
  const updateBotTokenVal = useWatch({ control: updateForm.control, name: 'botToken' })
  const updateAppTokenVal = useWatch({ control: updateForm.control, name: 'appToken' })
  const updateSigningSecretVal = useWatch({ control: updateForm.control, name: 'signingSecret' })
  const updateDescriptionVal = useWatch({ control: updateForm.control, name: 'description' })

  // Persist a draft of the safe (non-secret) fields only. Bot tokens, app
  // tokens, and signing secrets are never written to localStorage — admins
  // re-enter them on recovery, matching the existing edit-mode policy where
  // these inputs render blank and are only sent if the admin types something.
  type DraftSafeFields = {
    name: string
    workspace: string
    description: string
    isActive?: boolean
  }
  const draftValues: DraftSafeFields = {
    name: isEdit ? updateNameVal : createNameVal,
    workspace: isEdit ? updateWorkspaceVal : createWorkspaceVal,
    description: isEdit ? (updateDescriptionVal ?? '') : (createDescriptionVal ?? ''),
    isActive: isEdit ? updateForm.getValues('isActive') : true,
  }
  const draftStorageKey = isEdit && bot ? `slack-bots:edit:${bot.id}` : 'slack-bots:create'
  const {
    recoveredDraft,
    recoveredAt,
    acceptRecovery,
    dismissRecovery,
    clearDraft,
  } = useFormDraft<DraftSafeFields>({
    storageKey: draftStorageKey,
    values: draftValues,
    enabled: true,
  })

  const nameVal = isEdit ? updateNameVal : createNameVal
  const workspaceVal = isEdit ? updateWorkspaceVal : createWorkspaceVal
  const botTokenVal = isEdit ? updateBotTokenVal : createBotTokenVal
  const appTokenVal = isEdit ? updateAppTokenVal : createAppTokenVal
  const signingSecretVal = isEdit ? updateSigningSecretVal : createSigningSecretVal
  const descriptionVal = isEdit ? updateDescriptionVal : createDescriptionVal

  const nameStatus = useFieldStatus({
    value: nameVal,
    hasError: !!errors.name,
    isDirty: !!dirtyFields.name,
  })
  const workspaceStatus = useFieldStatus({
    value: workspaceVal,
    hasError: !!errors.workspace,
    isDirty: !!dirtyFields.workspace,
  })
  const botTokenStatus = useFieldStatus({
    value: botTokenVal,
    hasError: !!errors.botToken,
    isDirty: !!dirtyFields.botToken,
  })
  const appTokenStatus = useFieldStatus({
    value: appTokenVal,
    hasError: !!errors.appToken,
    isDirty: !!dirtyFields.appToken,
  })
  const signingSecretStatus = useFieldStatus({
    value: signingSecretVal,
    hasError: !!errors.signingSecret,
    isDirty: !!dirtyFields.signingSecret,
  })
  const descriptionStatus = useFieldStatus({
    value: descriptionVal,
    hasError: !!errors.description,
    isDirty: !!dirtyFields.description,
  })

  const mutation = useMutation({
    mutationFn: async (vals: SlackBotCreateFormValues | SlackBotUpdateFormValues) => {
      if (isEdit && bot) {
        const payload: UpdateSlackBotRequest = {
          name: vals.name,
          workspace: vals.workspace,
          description: vals.description || null,
          isActive: vals.isActive,
        }
        // Only include token fields if the admin entered a new value
        if (vals.botToken) payload.botToken = vals.botToken
        if (vals.appToken) payload.appToken = vals.appToken
        if (vals.signingSecret) payload.signingSecret = vals.signingSecret
        return slackBotApi.updateSlackBot(bot.id, payload)
      }
      const createValues = vals as SlackBotCreateFormValues
      const payload: CreateSlackBotRequest = {
        name: createValues.name,
        workspace: createValues.workspace,
        botToken: createValues.botToken,
        appToken: createValues.appToken,
        signingSecret: createValues.signingSecret,
        description: createValues.description || null,
      }
      return slackBotApi.createSlackBot(payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.slackBots.all() })
      addToast({
        type: 'success',
        message: isEdit ? t('slackBotsTab.updated') : t('slackBotsTab.created'),
      })
      clearDraft()
      onClose()
    },
    onError: (error: unknown) => {
      setError('root', { message: getErrorMessage(error) })
    },
  })

  const submitDisabled = isSubmitting || mutation.isPending || isValidating || !isValid

  return (
    <SideDrawer
      open
      title={isEdit ? t('slackBotsTab.editBot') : t('slackBotsTab.addBot')}
      onClose={onClose}
      size="wide"
    >
      <form className="slack-bot-form" ref={formRef} onSubmit={handleSubmit((v) => mutation.mutate(v))}>
        <DraftRecoveryBanner
          open={!!recoveredDraft}
          savedAt={recoveredAt ?? undefined}
          onAccept={() => {
            if (recoveredDraft) {
              // Apply only the safe (non-secret) fields. Secrets are
              // intentionally never persisted, so we leave token inputs
              // alone for the admin to re-enter.
              const target = isEdit ? updateForm : createForm
              target.setValue('name', recoveredDraft.name ?? '', { shouldDirty: true })
              target.setValue('workspace', recoveredDraft.workspace ?? '', { shouldDirty: true })
              target.setValue('description', recoveredDraft.description ?? '', { shouldDirty: true })
              if (isEdit && typeof recoveredDraft.isActive === 'boolean') {
                updateForm.setValue('isActive', recoveredDraft.isActive, { shouldDirty: true })
              }
            }
            acceptRecovery()
          }}
          onDismiss={dismissRecovery}
        />
        {errors.root && (
          <div className="form-error" role="alert">{errors.root.message}</div>
        )}

        <div className="slack-bot-form__section-heading">
          <h4>{t('slackBotsTab.formBasicsTitle')}</h4>
          <p>{t('slackBotsTab.formBasicsDescription')}</p>
        </div>

        <div className="form-group">
          <div className="form-label-row">
            <label className="form-label" htmlFor="slack-bot-name">
              {t('common.name')}
              <span className="form-label-required" aria-hidden="true">*</span>
              <FieldStatusIndicator status={nameStatus} />
            </label>
            <HelpHint label={t('slackBotsTab.hint.name')} title={t('common.name')} />
          </div>
          <input
            id="slack-bot-name"
            className="form-input"
            aria-required="true"
            {...register('name')}
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? 'name-error' : undefined}
          />
          {errors.name && (
            <span id="name-error" className="form-error" role="alert">{errors.name.message}</span>
          )}
        </div>

        <div className="form-group">
          <div className="form-label-row">
            <label className="form-label" htmlFor="slack-bot-workspace">
              {t('slackBotsTab.workspace')}
              <span className="form-label-required" aria-hidden="true">*</span>
              <FieldStatusIndicator status={workspaceStatus} />
            </label>
            <HelpHint label={t('slackBotsTab.hint.workspace')} title={t('slackBotsTab.workspace')} />
          </div>
          <input
            id="slack-bot-workspace"
            className="form-input"
            aria-required="true"
            {...register('workspace')}
            aria-invalid={!!errors.workspace}
            aria-describedby={errors.workspace ? 'workspace-error' : undefined}
          />
          {errors.workspace && (
            <span id="workspace-error" className="form-error" role="alert">{errors.workspace.message}</span>
          )}
        </div>

        <div className="slack-bot-form__section-heading">
          <h4>{t('slackBotsTab.formCredentialsTitle')}</h4>
          <p>{t('slackBotsTab.formCredentialsDescription')}</p>
        </div>

        <div className="form-group">
          <div className="form-label-row">
            <label className="form-label" htmlFor="slack-bot-botToken">
              {t('slackBotsTab.botToken')}
              {!isEdit && <span className="form-label-required" aria-hidden="true">*</span>}
              <FieldStatusIndicator status={botTokenStatus} />
            </label>
            <HelpHint label={t('slackBotsTab.hint.botToken')} title={t('slackBotsTab.botToken')} />
          </div>
          <input
            id="slack-bot-botToken"
            className="form-input"
            type="password"
            autoComplete="new-password"
            aria-required={!isEdit}
            {...register('botToken')}
            placeholder={isEdit ? t('slackBotsTab.tokenPlaceholder') : undefined}
            aria-invalid={!!errors.botToken}
            aria-describedby={errors.botToken ? 'botToken-error' : undefined}
          />
          {errors.botToken && (
            <span id="botToken-error" className="form-error" role="alert">{errors.botToken.message}</span>
          )}
        </div>

        <div className="form-group">
          <div className="form-label-row">
            <label className="form-label" htmlFor="slack-bot-appToken">
              {t('slackBotsTab.appToken')}
              {!isEdit && <span className="form-label-required" aria-hidden="true">*</span>}
              <FieldStatusIndicator status={appTokenStatus} />
            </label>
            <HelpHint label={t('slackBotsTab.hint.appToken')} title={t('slackBotsTab.appToken')} />
          </div>
          <input
            id="slack-bot-appToken"
            className="form-input"
            type="password"
            autoComplete="new-password"
            aria-required={!isEdit}
            {...register('appToken')}
            placeholder={isEdit ? t('slackBotsTab.tokenPlaceholder') : undefined}
            aria-invalid={!!errors.appToken}
            aria-describedby={errors.appToken ? 'appToken-error' : undefined}
          />
          {errors.appToken && (
            <span id="appToken-error" className="form-error" role="alert">{errors.appToken.message}</span>
          )}
        </div>

        <div className="form-group">
          <div className="form-label-row">
            <label className="form-label" htmlFor="slack-bot-signingSecret">
              {t('slackBotsTab.signingSecret')}
              {!isEdit && <span className="form-label-required" aria-hidden="true">*</span>}
              <FieldStatusIndicator status={signingSecretStatus} />
            </label>
            <HelpHint label={t('slackBotsTab.hint.signingSecret')} title={t('slackBotsTab.signingSecret')} />
          </div>
          <input
            id="slack-bot-signingSecret"
            className="form-input"
            type="password"
            autoComplete="new-password"
            aria-required={!isEdit}
            {...register('signingSecret')}
            placeholder={isEdit ? t('slackBotsTab.tokenPlaceholder') : undefined}
            aria-invalid={!!errors.signingSecret}
            aria-describedby={errors.signingSecret ? 'signingSecret-error' : undefined}
          />
          {errors.signingSecret && (
            <span id="signingSecret-error" className="form-error" role="alert">{errors.signingSecret.message}</span>
          )}
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="slack-bot-description">
            {t('common.description')}
            <FieldStatusIndicator status={descriptionStatus} />
          </label>
          <textarea
            id="slack-bot-description"
            className="form-input"
            rows={3}
            {...register('description')}
            aria-invalid={!!errors.description}
            aria-describedby={errors.description ? 'description-error' : undefined}
          />
          {errors.description && (
            <span id="description-error" className="form-error" role="alert">{errors.description.message}</span>
          )}
        </div>

        {isEdit && (
          <div className="form-group">
            <label className="form-label form-label--checkbox">
              <input type="checkbox" {...register('isActive')} />
              {t('common.active')}
            </label>
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitDisabled}
          >
            {isEdit ? t('common.save') : t('slackBotsTab.addBot')}
          </button>
        </div>
      </form>
    </SideDrawer>
  )
}

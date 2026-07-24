import { useForm, type UseFormRegister, type FieldValues } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'

import { OperationButton } from '../../../shared/ui/OperationButton'
import {
  createFaqChannelSchema,
  updateFaqChannelSchema,
  type CreateFaqChannelFormValues,
  type UpdateFaqChannelFormValues,
} from '../schema'
import type { FaqChannel } from '../types'

interface BaseProps {
  onCancel: () => void
  isPending: boolean
  rootError?: string | null
}

interface CreateProps extends BaseProps {
  mode: 'create'
  initialValues?: undefined
  onSubmit: (values: CreateFaqChannelFormValues) => void | Promise<void>
}

interface EditProps extends BaseProps {
  mode: 'edit'
  initialValues: FaqChannel
  onSubmit: (values: UpdateFaqChannelFormValues) => void | Promise<void>
}

type Props = CreateProps | EditProps

const DEFAULT_VALUES: Required<
  Pick<
    CreateFaqChannelFormValues,
    'autoReplyMode' | 'enabled' | 'confidenceThreshold' | 'daysBack' | 'reIngestIntervalHours'
  >
> = {
  enabled: true,
  autoReplyMode: 'OFF',
  confidenceThreshold: 0.7,
  daysBack: 30,
  reIngestIntervalHours: 24,
}

/**
 * Form body for creating or editing a Slack FAQ channel. Mounted inside a
 * DetailModal by the parent — this component only owns the form state.
 */
export function FaqChannelForm(props: Props) {
  if (props.mode === 'create') {
    return <FaqChannelCreateForm {...props} />
  }
  return <FaqChannelEditForm {...props} />
}

function FaqChannelCreateForm({
  onSubmit,
  onCancel,
  isPending,
  rootError,
}: CreateProps) {
  const { t } = useTranslation()
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CreateFaqChannelFormValues>({
    resolver: zodResolver(createFaqChannelSchema),
    defaultValues: {
      channelId: '',
      channelName: '',
      ...DEFAULT_VALUES,
    },
  })

  const submit = handleSubmit(async (values) => {
    await onSubmit(values)
  })

  return (
    <form onSubmit={submit} aria-label={t('slackFaq.form.createAria')}>
      {rootError && (
        <div className="form-error" role="alert" id="faq-form-root-error">
          {rootError}
        </div>
      )}
      <SharedFields
        register={register as unknown as UseFormRegister<FieldValues>}
        errors={errors as unknown as Record<string, { message?: string } | undefined>}
        channelIdDisabled={false}
      />
      <FormFooter
        onCancel={onCancel}
        isPending={isPending}
        submitLabel={t('slackFaq.form.createSubmit')}
      />
    </form>
  )
}

function FaqChannelEditForm({
  initialValues,
  onSubmit,
  onCancel,
  isPending,
  rootError,
}: EditProps) {
  const { t } = useTranslation()
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<UpdateFaqChannelFormValues>({
    resolver: zodResolver(updateFaqChannelSchema),
    defaultValues: {
      channelName: initialValues.channelName ?? '',
      enabled: initialValues.enabled,
      autoReplyMode: initialValues.autoReplyMode,
      confidenceThreshold: initialValues.confidenceThreshold,
      daysBack: initialValues.daysBack,
      reIngestIntervalHours: initialValues.reIngestIntervalHours,
    },
  })

  const submit = handleSubmit(async (values) => {
    await onSubmit(values)
  })

  return (
    <form onSubmit={submit} aria-label={t('slackFaq.form.editAria')}>
      {rootError && (
        <div className="form-error" role="alert" id="faq-form-root-error">
          {rootError}
        </div>
      )}
      <div className="form-group">
        <label className="form-label" htmlFor="faq-channel-id-readonly">
          {t('slackFaq.form.channelId')}
        </label>
        <input
          id="faq-channel-id-readonly"
          className="form-input"
          value={initialValues.channelId}
          disabled
          readOnly
          aria-disabled="true"
        />
      </div>
      <SharedFields
        register={register as unknown as UseFormRegister<FieldValues>}
        errors={errors as unknown as Record<string, { message?: string } | undefined>}
        channelIdDisabled
      />
      <FormFooter
        onCancel={onCancel}
        isPending={isPending}
        submitLabel={t('common.save')}
      />
    </form>
  )
}

interface SharedFieldsProps {
  // The form types diverge between create and edit, but the shared subset of
  // fields is structurally compatible. Treating register as
  // UseFormRegister<FieldValues> keeps this component reusable without
  // sacrificing zod validation (which still runs against the per-mode schema).
  register: UseFormRegister<FieldValues>
  errors: Record<string, { message?: string } | undefined>
  channelIdDisabled: boolean
}

function SharedFields({ register, errors, channelIdDisabled }: SharedFieldsProps) {
  const { t } = useTranslation()
  return (
    <>
      {!channelIdDisabled && (
        <div className="form-group">
          <label className="form-label" htmlFor="faq-channel-id">
            {t('slackFaq.form.channelId')}
            <span className="form-label-required" aria-hidden="true">
              *
            </span>
          </label>
          <input
            id="faq-channel-id"
            className="form-input"
            aria-required="true"
            aria-invalid={!!errors.channelId}
            aria-describedby={errors.channelId ? 'faq-channel-id-error' : undefined}
            {...register('channelId')}
          />
          {errors.channelId && (
            <span id="faq-channel-id-error" className="form-error" role="alert">
              {errors.channelId.message}
            </span>
          )}
        </div>
      )}

      <div className="form-group">
        <label className="form-label" htmlFor="faq-channel-name">
          {t('slackFaq.form.channelName')}
        </label>
        <input
          id="faq-channel-name"
          className="form-input"
          aria-invalid={!!errors.channelName}
          aria-describedby={errors.channelName ? 'faq-channel-name-error' : undefined}
          {...register('channelName')}
        />
        {errors.channelName && (
          <span id="faq-channel-name-error" className="form-error" role="alert">
            {errors.channelName.message}
          </span>
        )}
      </div>

      <div className="form-group">
        <label className="form-label form-label--checkbox" htmlFor="faq-enabled">
          <input id="faq-enabled" type="checkbox" {...register('enabled')} />
          {t('slackFaq.form.enabled')}
        </label>
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="faq-auto-reply-mode">
          {t('slackFaq.form.autoReplyMode')}
        </label>
        <select id="faq-auto-reply-mode" className="form-input" {...register('autoReplyMode')}>
          <option value="OFF">{t('slackFaq.form.modeOff')}</option>
          <option value="AUTO">{t('slackFaq.form.modeAuto')}</option>
          <option value="SUGGEST">{t('slackFaq.form.modeSuggest')}</option>
        </select>
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="faq-confidence-threshold">
          {t('slackFaq.form.confidenceThreshold')}
        </label>
        <input
          id="faq-confidence-threshold"
          className="form-input"
          type="number"
          step="0.05"
          min="0"
          max="1"
          aria-invalid={!!errors.confidenceThreshold}
          aria-describedby={
            errors.confidenceThreshold ? 'faq-confidence-threshold-error' : undefined
          }
          {...register('confidenceThreshold', { valueAsNumber: true })}
        />
        {errors.confidenceThreshold && (
          <span
            id="faq-confidence-threshold-error"
            className="form-error"
            role="alert"
          >
            {errors.confidenceThreshold.message}
          </span>
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="faq-days-back">
          {t('slackFaq.form.daysBack')}
        </label>
        <input
          id="faq-days-back"
          className="form-input"
          type="number"
          min="1"
          max="365"
          step="1"
          aria-invalid={!!errors.daysBack}
          aria-describedby={errors.daysBack ? 'faq-days-back-error' : undefined}
          {...register('daysBack', { valueAsNumber: true })}
        />
        {errors.daysBack && (
          <span id="faq-days-back-error" className="form-error" role="alert">
            {errors.daysBack.message}
          </span>
        )}
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="faq-reingest-hours">
          {t('slackFaq.form.reIngestIntervalHours')}
        </label>
        <input
          id="faq-reingest-hours"
          className="form-input"
          type="number"
          min="1"
          max="720"
          step="1"
          aria-invalid={!!errors.reIngestIntervalHours}
          aria-describedby={
            errors.reIngestIntervalHours ? 'faq-reingest-hours-error' : undefined
          }
          {...register('reIngestIntervalHours', { valueAsNumber: true })}
        />
        {errors.reIngestIntervalHours && (
          <span
            id="faq-reingest-hours-error"
            className="form-error"
            role="alert"
          >
            {errors.reIngestIntervalHours.message}
          </span>
        )}
      </div>
    </>
  )
}

function FormFooter({
  onCancel,
  isPending,
  submitLabel,
}: {
  onCancel: () => void
  isPending: boolean
  submitLabel: string
}) {
  const { t } = useTranslation()
  return (
    <div className="modal-footer">
      <button
        type="button"
        className="btn btn-ghost"
        onClick={onCancel}
        disabled={isPending}
      >
        {t('common.cancel')}
      </button>
      <OperationButton type="submit" variant="primary" isOperating={isPending}>
        {submitLabel}
      </OperationButton>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { useForm, Controller, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ConfirmDialog, FieldStatusIndicator, LoadingSpinner, NumberInputStepper, SkeletonCard, ToggleSwitch } from '../../../shared/ui'
import { useFieldStatus } from '../../../shared/lib/useFieldStatus'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { formatDateTimeCompact } from '../../../shared/lib/formatters'
import { useToastStore } from '../../../shared/store/toast.store'
import * as ragCacheApi from '../api'
import { ragPolicySchema, type RagPolicyFormValues } from '../schema'
import type { RagPolicy } from '../types'

const DEFAULT_VALUES: RagPolicyFormValues = {
  enabled: true,
  requireReview: true,
  allowedChannels: [],
  minQueryChars: 10,
  minResponseChars: 20,
  blockedPatterns: [],
}

function toFormValues(policy: RagPolicy): RagPolicyFormValues {
  return {
    enabled: policy.enabled,
    requireReview: policy.requireReview,
    allowedChannels: policy.allowedChannels ?? [],
    minQueryChars: policy.minQueryChars,
    minResponseChars: policy.minResponseChars,
    blockedPatterns: policy.blockedPatterns ?? [],
  }
}

interface ChipInputProps {
  id: string
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  ariaLabel?: string
}

function ChipInput({ id, value, onChange, placeholder, ariaLabel }: ChipInputProps) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState('')

  function commit() {
    const trimmed = draft.trim()
    if (!trimmed) return
    if (value.includes(trimmed)) {
      setDraft('')
      return
    }
    onChange([...value, trimmed])
    setDraft('')
  }

  function remove(idx: number) {
    const next = value.filter((_, i) => i !== idx)
    onChange(next)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      commit()
    } else if (e.key === 'Backspace' && draft === '' && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div className="rag-policy-value-input">
      {value.length > 0 && (
        <ul className="rag-policy-value-input__list" aria-label={ariaLabel}>
          {value.map((chip, idx) => (
            <li key={`${chip}-${idx}`}>
              <span>{chip}</span>
              <button
                type="button"
                onClick={() => remove(idx)}
                aria-label={t('ragCachePage.policy.removeValue', { value: chip })}
              >
                {t('common.delete')}
              </button>
            </li>
          ))}
        </ul>
      )}
      <input
        id={id}
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={commit}
        placeholder={placeholder}
        aria-label={ariaLabel}
      />
    </div>
  )
}

export function RagPolicyEditor() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [showResetConfirm, setShowResetConfirm] = useState(false)
  const [showOffConfirm, setShowOffConfirm] = useState(false)
  const [pendingValues, setPendingValues] = useState<RagPolicyFormValues | null>(null)

  const { data: policyState, isLoading } = useQuery({
    queryKey: queryKeys.ragCache.policy(),
    queryFn: ragCacheApi.getRagPolicy,
  })

  const {
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting, isDirty, dirtyFields },
  } = useForm<RagPolicyFormValues>({
    resolver: zodResolver(ragPolicySchema),
    mode: 'onChange',
    defaultValues: DEFAULT_VALUES,
  })

  useEffect(() => {
    if (policyState?.effective) {
      reset(toFormValues(policyState.effective))
    }
  }, [policyState, reset])

  const requireReview = useWatch({ control, name: 'requireReview' })
  const minQueryCharsValue = useWatch({ control, name: 'minQueryChars' })
  const minResponseCharsValue = useWatch({ control, name: 'minResponseChars' })

  const minQueryStatus = useFieldStatus({
    value: minQueryCharsValue,
    hasError: !!errors.minQueryChars,
    isDirty: !!dirtyFields.minQueryChars,
  })
  const minResponseStatus = useFieldStatus({
    value: minResponseCharsValue,
    hasError: !!errors.minResponseChars,
    isDirty: !!dirtyFields.minResponseChars,
  })
  const wasRequireReview = policyState?.effective.requireReview ?? true
  const willBypass = wasRequireReview && !requireReview

  const updateMutation = useMutation({
    mutationFn: ragCacheApi.updateRagPolicy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ragCache.policy() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
    },
    onError: (err: Error) => {
      useToastStore.getState().addToast({ type: 'error', message: err.message })
    },
  })

  const resetMutation = useMutation({
    mutationFn: ragCacheApi.resetRagPolicy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.ragCache.policy() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
    },
    onError: (err: Error) => {
      useToastStore.getState().addToast({ type: 'error', message: err.message })
    },
  })

  function onSubmit(values: RagPolicyFormValues) {
    if (wasRequireReview && !values.requireReview) {
      setPendingValues(values)
      setShowOffConfirm(true)
      return
    }
    updateMutation.mutate(values)
  }

  function confirmBypass() {
    if (pendingValues) {
      updateMutation.mutate(pendingValues)
    }
    setShowOffConfirm(false)
    setPendingValues(null)
  }

  function handleReset() {
    setShowResetConfirm(false)
    resetMutation.mutate()
  }

  if (isLoading) {
    return (
      <section className="rag-policy-editor" aria-busy="true">
        <SkeletonCard height={320} />
      </section>
    )
  }

  const saving = isSubmitting || updateMutation.isPending
  const resetting = resetMutation.isPending

  return (
    <section className="rag-policy-editor" aria-labelledby="rag-policy-title">
      <div className="rag-policy-editor__header">
        <div>
          <h2 id="rag-policy-title" className="section-title">{t('ragCachePage.policy.title')}</h2>
          <p>{t('ragCachePage.policy.description')}</p>
        </div>
        {policyState && (
          <span className="rag-policy-editor__source">
            {policyState.stored
              ? t('ragCachePage.policy.usingStored')
              : t('ragCachePage.policy.usingDefaults')}
          </span>
        )}
      </div>

      {willBypass && (
        <div
          role="alert"
          className="alert alert-error"
        >
          <strong>{t('ragCachePage.policy.requireReviewWarning')}</strong>
          <p>
            {t('ragCachePage.policy.requireReviewWarningDesc')}
          </p>
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="rag-toggle-row">
          <div className="rag-toggle-row__info">
            <label htmlFor="rag-policy-enabled" className="rag-toggle-row__label">{t('ragCachePage.policy.enabled')}</label>
            <span className="rag-toggle-row__desc">{t('ragCachePage.policy.enabledDesc')}</span>
          </div>
          <Controller
            control={control}
            name="enabled"
            render={({ field }) => (
              <ToggleSwitch
                checked={field.value}
                onChange={field.onChange}
                label={t('ragCachePage.policy.enabled')}
              />
            )}
          />
        </div>

        <div className="rag-toggle-row">
          <div className="rag-toggle-row__info">
            <label htmlFor="rag-policy-require-review" className="rag-toggle-row__label">{t('ragCachePage.policy.requireReview')}</label>
            <span className="rag-toggle-row__desc">{t('ragCachePage.policy.requireReviewDesc')}</span>
          </div>
          <Controller
            control={control}
            name="requireReview"
            render={({ field }) => (
              <ToggleSwitch
                checked={field.value}
                onChange={field.onChange}
                label={t('ragCachePage.policy.requireReview')}
              />
            )}
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="rag-policy-min-query">
              {t('ragCachePage.policy.minQueryChars')}
              <span className="form-label-required" aria-hidden="true">*</span>
              <FieldStatusIndicator status={minQueryStatus} />
            </label>
            <Controller
              control={control}
              name="minQueryChars"
              render={({ field }) => (
                <NumberInputStepper
                  id="rag-policy-min-query"
                  value={field.value ?? null}
                  onChange={(next) => field.onChange(next ?? 0)}
                  onBlur={field.onBlur}
                  min={0}
                  max={10000}
                  ariaLabel={t('ragCachePage.policy.minQueryChars')}
                  aria-required
                  aria-invalid={!!errors.minQueryChars}
                  aria-describedby={errors.minQueryChars ? 'rag-policy-min-query-error' : undefined}
                />
              )}
            />
            {errors.minQueryChars && (
              <p id="rag-policy-min-query-error" className="form-error" role="alert">
                {errors.minQueryChars.message}
              </p>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="rag-policy-min-response">
              {t('ragCachePage.policy.minResponseChars')}
              <span className="form-label-required" aria-hidden="true">*</span>
              <FieldStatusIndicator status={minResponseStatus} />
            </label>
            <Controller
              control={control}
              name="minResponseChars"
              render={({ field }) => (
                <NumberInputStepper
                  id="rag-policy-min-response"
                  value={field.value ?? null}
                  onChange={(next) => field.onChange(next ?? 0)}
                  onBlur={field.onBlur}
                  min={0}
                  max={10000}
                  ariaLabel={t('ragCachePage.policy.minResponseChars')}
                  aria-required
                  aria-invalid={!!errors.minResponseChars}
                  aria-describedby={errors.minResponseChars ? 'rag-policy-min-response-error' : undefined}
                />
              )}
            />
            {errors.minResponseChars && (
              <p id="rag-policy-min-response-error" className="form-error" role="alert">
                {errors.minResponseChars.message}
              </p>
            )}
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="rag-policy-allowed-channels">{t('ragCachePage.policy.allowedChannels')}</label>
          <p className="detail-note">
            {t('ragCachePage.policy.allowedChannelsHint')}
          </p>
          <Controller
            control={control}
            name="allowedChannels"
            render={({ field }) => (
              <ChipInput
                id="rag-policy-allowed-channels"
                value={field.value}
                onChange={field.onChange}
                ariaLabel={t('ragCachePage.policy.allowedChannels')}
              />
            )}
          />
        </div>

        <div className="form-group">
          <label htmlFor="rag-policy-blocked-patterns">{t('ragCachePage.policy.blockedPatterns')}</label>
          <p className="detail-note">
            {t('ragCachePage.policy.blockedPatternsHint')}
          </p>
          <Controller
            control={control}
            name="blockedPatterns"
            render={({ field }) => (
              <ChipInput
                id="rag-policy-blocked-patterns"
                value={field.value}
                onChange={field.onChange}
                ariaLabel={t('ragCachePage.policy.blockedPatterns')}
              />
            )}
          />
        </div>

        {policyState?.effective.updatedAt && (
          <p className="rag-policy-editor__saved-at">
            {t('ragCachePage.policy.savedAt')}: {formatDateTimeCompact(policyState.effective.updatedAt)}
          </p>
        )}

        <div className="rag-policy-editor__actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setShowResetConfirm(true)}
            disabled={saving || resetting}
          >
            {resetting ? <LoadingSpinner size="sm" /> : t('ragCachePage.policy.reset')}
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={saving || resetting || !isDirty}
          >
            {saving ? <LoadingSpinner size="sm" /> : t('ragCachePage.policy.save')}
          </button>
        </div>
      </form>

      {showResetConfirm && (
        <ConfirmDialog
          title={t('ragCachePage.policy.reset')}
          message={t('ragCachePage.policy.resetConfirm')}
          onConfirm={handleReset}
          onCancel={() => setShowResetConfirm(false)}
          danger
        />
      )}

      {showOffConfirm && (
        <ConfirmDialog
          title={t('ragCachePage.policy.requireReviewWarning')}
          message={t('ragCachePage.policy.requireReviewWarningDesc')}
          onConfirm={confirmBypass}
          onCancel={() => {
            setShowOffConfirm(false)
            setPendingValues(null)
          }}
          danger
          confirmText="DISABLE REVIEW"
        />
      )}
    </section>
  )
}

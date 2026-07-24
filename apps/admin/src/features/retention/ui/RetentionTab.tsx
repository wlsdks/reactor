import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Controller, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { SkeletonCard, ConfirmDialog, NumberInputStepper, OperationButton, WorkspaceUnavailable } from '../../../shared/ui'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { showApiErrorToast } from '../../../shared/lib/showApiErrorToast'
import { getRetentionPolicy, updateRetentionPolicy } from '../api'
import { retentionPolicySchema } from '../schema'
import type { RetentionPolicyFormValues } from '../schema'
import type { RetentionPolicy } from '../types'
import './RetentionTab.css'

const DEFAULT_POLICY: RetentionPolicy = {
  sessionRetentionDays: 90,
  conversationRetentionDays: 365,
  auditRetentionDays: 730,
  metricRetentionDays: 180,
  checkpointRetentionDays: 90,
}

interface FieldDef {
  name: keyof RetentionPolicyFormValues
  defaultValue: number
}

const FIELDS: FieldDef[] = [
  { name: 'sessionRetentionDays', defaultValue: 90 },
  { name: 'conversationRetentionDays', defaultValue: 365 },
  { name: 'auditRetentionDays', defaultValue: 730 },
  { name: 'metricRetentionDays', defaultValue: 180 },
  { name: 'checkpointRetentionDays', defaultValue: 90 },
]

export function RetentionTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [showResetConfirm, setShowResetConfirm] = useState(false)
  const fieldLabels: Record<keyof RetentionPolicyFormValues, string> = {
    sessionRetentionDays: t('retentionTab.sessionRetention'),
    conversationRetentionDays: t('retentionTab.conversationRetention'),
    auditRetentionDays: t('retentionTab.auditRetention'),
    metricRetentionDays: t('retentionTab.metricRetention'),
    checkpointRetentionDays: t('retentionTab.checkpointRetention'),
  }
  const fieldDescriptions: Record<keyof RetentionPolicyFormValues, string> = {
    sessionRetentionDays: t('retentionTab.fieldDescriptions.sessionRetention'),
    conversationRetentionDays: t('retentionTab.fieldDescriptions.conversationRetention'),
    auditRetentionDays: t('retentionTab.fieldDescriptions.auditRetention'),
    metricRetentionDays: t('retentionTab.fieldDescriptions.metricRetention'),
    checkpointRetentionDays: t('retentionTab.fieldDescriptions.checkpointRetention'),
  }

  const { data: policy, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: queryKeys.retention.policy(),
    queryFn: getRetentionPolicy,
  })

  const {
    handleSubmit,
    control,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<RetentionPolicyFormValues>({
    resolver: zodResolver(retentionPolicySchema),
    values: policy ?? DEFAULT_POLICY,
  })

  const saveMutation = useMutation({
    mutationFn: updateRetentionPolicy,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.retention.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
    },
    onError: (err: Error) => { showApiErrorToast(err) },
  })

  const resetMutation = useMutation({
    mutationFn: () => updateRetentionPolicy(DEFAULT_POLICY),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.retention.all() })
      reset(DEFAULT_POLICY)
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
    },
    onError: (err: Error) => { showApiErrorToast(err) },
  })

  function onSubmit(data: RetentionPolicyFormValues) {
    saveMutation.mutate(data)
  }

  function handleResetConfirm() {
    setShowResetConfirm(false)
    resetMutation.mutate()
  }

  if (isLoading) {
    return (
      <div className="retention-tab">
        <SkeletonCard height={280} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="retention-tab">
        <WorkspaceUnavailable
          title={t('retentionTab.unavailableTitle')}
          description={t('retentionTab.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refetch}
          isRetrying={isFetching}
          secondaryAction={{ label: t('retentionTab.openHealth'), to: '/health' }}
          guide={{
            title: t('retentionTab.recoveryGuideTitle'),
            steps: [
              t('retentionTab.recoveryCheckAccount'),
              t('retentionTab.recoveryCheckStatus'),
              t('retentionTab.recoveryRetry'),
            ],
            technicalLabel: t('retentionTab.technicalError'),
            technicalDetail: getErrorMessage(error),
          }}
        />
      </div>
    )
  }

  return (
    <div className="retention-tab">
      <div className="retention-tab__heading">
        <h2 className="section-title">{t('retentionTab.title')}</h2>
        <p>{t('retentionTab.description')}</p>
      </div>

      <form onSubmit={(event) => void handleSubmit(onSubmit)(event)} className="retention-tab__form">
        <div className="retention-tab__fields">
          {FIELDS.map((field) => (
            <div className="retention-tab__field" key={field.name}>
              <div className="retention-tab__field-copy">
                <label htmlFor={field.name}>{fieldLabels[field.name]}</label>
                <p>{fieldDescriptions[field.name]}</p>
              </div>
              <div className="retention-tab__field-control">
                <Controller
                  control={control}
                  name={field.name}
                  render={({ field: controllerField }) => (
                    <NumberInputStepper
                      id={field.name}
                      value={controllerField.value ?? null}
                      onChange={(next) => controllerField.onChange(next ?? field.defaultValue)}
                      onBlur={controllerField.onBlur}
                      min={1}
                      max={3650}
                      ariaLabel={fieldLabels[field.name]}
                      suffix={t('retentionTab.days')}
                      aria-invalid={!!errors[field.name]}
                      aria-describedby={errors[field.name] ? `${field.name}-error` : undefined}
                    />
                  )}
                />
                {errors[field.name] && (
                  <div id={`${field.name}-error`} role="alert" className="form-error">
                    {t('retentionTab.validationRange')}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="retention-tab__actions">
          <OperationButton
            type="submit"
            variant="primary"
            isOperating={isSubmitting || saveMutation.isPending}
            disabled={!isDirty}
          >
            {t('common.save')}
          </OperationButton>
          <OperationButton
            variant="secondary"
            onClick={() => setShowResetConfirm(true)}
            isOperating={resetMutation.isPending}
          >
            {t('retentionTab.resetDefaults')}
          </OperationButton>
        </div>
      </form>

      {showResetConfirm && (
        <ConfirmDialog
          title={t('retentionTab.resetTitle')}
          message={t('retentionTab.resetMessage')}
          onConfirm={handleResetConfirm}
          onCancel={() => setShowResetConfirm(false)}
          danger
          confirmText={t('retentionTab.resetConfirmText')}
        />
      )}
    </div>
  )
}

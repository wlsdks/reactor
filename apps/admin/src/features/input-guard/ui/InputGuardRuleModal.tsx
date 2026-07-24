import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { DetailModal, LoadingSpinner, FieldStatusIndicator, useAnnouncer } from '../../../shared/ui'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useFieldStatus } from '../../../shared/lib/useFieldStatus'
import * as inputGuardApi from '../api'
import type { InputGuardRule, InputGuardRuleRequest } from '../api'
import {
  inputGuardRuleSchema,
  type InputGuardRuleFormValues,
} from '../schema'
import { patternTypeLabel, ruleActionLabel } from '../inputGuardLabels'

type Mode = 'read' | 'edit'

interface Props {
  open: boolean
  rule?: InputGuardRule | null
  /**
   * Initial display mode. Defaults to `'edit'` for backward compatibility.
   * `'read'` shows a definition list of the rule with an "Edit" toggle that
   * flips to the form. Only meaningful when `rule` is supplied.
   */
  mode?: Mode
  onClose: () => void
  onDelete?: () => void
}

function formatTimestamp(value: string): string {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString()
}

const CREATE_DEFAULTS: InputGuardRuleFormValues = {
  name: '',
  pattern: '',
  patternType: 'regex',
  action: 'block',
  priority: 100,
  category: 'custom',
  description: '',
  enabled: true,
}

export function InputGuardRuleModal({ open, rule, mode: initialMode = 'edit', onClose, onDelete }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const { announce } = useAnnouncer()

  // Local mode state — caller is expected to remount (via `key`) when switching
  // between rules or read/edit intent, so the useState initializer always
  // captures the correct initialMode for each session.
  const [mode, setMode] = useState<Mode>(initialMode)

  const isEdit = !!rule
  const {
    register,
    handleSubmit,
    control,
    setError,
    formState: { errors, isSubmitting, isValid, isValidating, dirtyFields },
    reset,
  } = useForm<InputGuardRuleFormValues>({
    resolver: zodResolver(inputGuardRuleSchema),
    mode: 'onChange',
    defaultValues: rule
      ? {
          name: rule.name,
          pattern: rule.pattern,
          patternType: rule.patternType,
          action: rule.action,
          priority: rule.priority,
          category: rule.category,
          description: rule.description ?? '',
          enabled: rule.enabled,
        }
      : CREATE_DEFAULTS,
  })

  // useWatch (react-compiler-safe). watch() returns a non-memoizable function.
  const patternType = useWatch({ control, name: 'patternType' })
  const nameVal = useWatch({ control, name: 'name' })
  const patternVal = useWatch({ control, name: 'pattern' })
  const priorityVal = useWatch({ control, name: 'priority' })

  const nameStatus = useFieldStatus({
    value: nameVal,
    hasError: !!errors.name,
    isDirty: !!dirtyFields.name,
  })
  const patternStatus = useFieldStatus({
    value: patternVal,
    hasError: !!errors.pattern,
    isDirty: !!dirtyFields.pattern,
  })
  const priorityStatus = useFieldStatus({
    value: priorityVal,
    hasError: !!errors.priority,
    isDirty: !!dirtyFields.priority,
  })

  const createMutation = useMutation({
    mutationFn: (data: InputGuardRuleRequest) => inputGuardApi.createInputGuardRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inputGuard.rules() })
      addToast({ type: 'success', message: t('inputGuard.rules.created') })
      announce(t('common.a11y.created'))
      reset(CREATE_DEFAULTS)
      onClose()
    },
    onError: (err: Error) => {
      setError('root', { message: err.message })
      announce(err.message, { priority: 'assertive' })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: InputGuardRuleRequest }) =>
      inputGuardApi.updateInputGuardRule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inputGuard.rules() })
      addToast({ type: 'success', message: t('inputGuard.rules.updated') })
      announce(t('common.a11y.updated'))
      onClose()
    },
    onError: (err: Error) => {
      setError('root', { message: err.message })
      announce(err.message, { priority: 'assertive' })
    },
  })

  const saving = createMutation.isPending || updateMutation.isPending || isSubmitting

  function onSubmit(data: InputGuardRuleFormValues) {
    const payload: InputGuardRuleRequest = {
      name: data.name,
      pattern: data.pattern,
      patternType: data.patternType,
      action: data.action,
      priority: data.priority,
      category: data.category.trim() || 'custom',
      description: data.description?.trim() ? data.description.trim() : null,
      enabled: data.enabled,
    }
    if (isEdit && rule) updateMutation.mutate({ id: rule.id, data: payload })
    else createMutation.mutate(payload)
  }

  const isReadMode = mode === 'read' && !!rule
  const title = isReadMode
    ? t('inputGuard.rules.detailTitle')
    : isEdit
      ? t('inputGuard.rules.editTitle')
      : t('inputGuard.rules.createTitle')

  // Helper: returns translated text only when the key actually resolves.
  const hint = (key: string): string | null => {
    const translated = t(key)
    return translated && translated !== key ? translated : null
  }

  const submitDisabled = saving || isValidating || !isValid

  return (
    <DetailModal open={open} title={title} onClose={onClose}>
      {isReadMode && rule ? (
        <div className="ig-rule-read">
          <dl className="ig-rule-read__list">
            <dt>{t('inputGuard.rules.fieldName')}</dt>
            <dd>{rule.name}</dd>

            <dt>{t('inputGuard.rules.fieldPatternType')}</dt>
            <dd>{patternTypeLabel(t, rule.patternType)}</dd>

            <dt>{t('inputGuard.rules.fieldAction')}</dt>
            <dd>{ruleActionLabel(t, rule.action)}</dd>

            <dt>{t('inputGuard.rules.fieldPriority')}</dt>
            <dd>{rule.priority}</dd>

            <dt>{t('inputGuard.rules.fieldDescription')}</dt>
            <dd>{rule.description ?? ''}</dd>

            <dt>{t('inputGuard.rules.fieldEnabled')}</dt>
            <dd>{rule.enabled ? t('inputGuard.rules.statusEnabled') : t('inputGuard.rules.statusPaused')}</dd>

            <dt>{t('inputGuard.rules.fieldCreatedAt')}</dt>
            <dd>{formatTimestamp(rule.createdAt)}</dd>

            <dt>{t('inputGuard.rules.fieldUpdatedAt')}</dt>
            <dd>{formatTimestamp(rule.updatedAt)}</dd>
          </dl>
          <details className="ig-rule-read__technical">
            <summary>{t('inputGuard.rules.technicalDetails')}</summary>
            <dl className="ig-rule-read__list">
              <dt>{t('inputGuard.rules.technicalPattern')}</dt>
              <dd><code>{rule.pattern}</code></dd>

              <dt>{t('inputGuard.rules.technicalCategory')}</dt>
              <dd><code>{rule.category}</code></dd>

              <dt>{t('inputGuard.rules.technicalId')}</dt>
              <dd><code>{rule.id}</code></dd>
            </dl>
          </details>
          <div className="modal-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
            >
              {t('common.close')}
            </button>
            {onDelete ? (
              <button
                type="button"
                className="btn btn-danger"
                onClick={onDelete}
              >
                {t('inputGuard.rules.delete')}
              </button>
            ) : null}
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setMode('edit')}
            >
              {t('inputGuard.rules.editButton')}
            </button>
          </div>
        </div>
      ) : (
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        {errors.root && (
          <div className="alert alert-error" role="alert">
            {errors.root.message}
          </div>
        )}

        <div className="form-group">
          <label htmlFor="ig-rule-name">
            {t('inputGuard.rules.fieldName')}
            <span className="form-label-required" aria-hidden="true">*</span>
            <FieldStatusIndicator status={nameStatus} />
          </label>
          <input
            id="ig-rule-name"
            type="text"
            aria-required="true"
            {...register('name')}
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? 'ig-rule-name-error' : 'ig-rule-name-hint'}
            placeholder={t('inputGuard.rules.fieldNamePlaceholder')}
          />
          {hint('inputGuard.rules.hintName') && (
            <p id="ig-rule-name-hint" className="form-hint">{hint('inputGuard.rules.hintName')}</p>
          )}
          {errors.name && (
            <span id="ig-rule-name-error" className="form-error" role="alert">
              {errors.name.message}
            </span>
          )}
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="ig-rule-type">{t('inputGuard.rules.fieldPatternType')}</label>
            <select id="ig-rule-type" {...register('patternType')}>
              <option value="regex">{t('inputGuard.rules.fieldPatternTypeRegex')}</option>
              <option value="keyword">{t('inputGuard.rules.fieldPatternTypeKeyword')}</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="ig-rule-action">{t('inputGuard.rules.fieldAction')}</label>
            <select id="ig-rule-action" {...register('action')}>
              <option value="block">{t('inputGuard.rules.fieldActionBlock')}</option>
              <option value="warn">{t('inputGuard.rules.fieldActionWarn')}</option>
              <option value="flag">{t('inputGuard.rules.fieldActionFlag')}</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="ig-rule-pattern">
            {t('inputGuard.rules.fieldPattern')}
            <span className="form-label-required" aria-hidden="true">*</span>
            <FieldStatusIndicator status={patternStatus} />
          </label>
          <textarea
            id="ig-rule-pattern"
            rows={3}
            aria-required="true"
            {...register('pattern')}
            aria-invalid={!!errors.pattern}
            aria-describedby={errors.pattern ? 'ig-rule-pattern-error' : 'ig-rule-pattern-hint'}
            placeholder={
              patternType === 'keyword'
                ? t('inputGuard.rules.fieldPatternPlaceholderKeyword')
                : t('inputGuard.rules.fieldPatternPlaceholderRegex')
            }
            style={{ fontFamily: 'var(--font-mono, monospace)' }}
          />
          {hint('inputGuard.rules.hintPattern') && (
            <p id="ig-rule-pattern-hint" className="form-hint">{hint('inputGuard.rules.hintPattern')}</p>
          )}
          {errors.pattern && (
            <span id="ig-rule-pattern-error" className="form-error" role="alert">
              {errors.pattern.message}
            </span>
          )}
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="ig-rule-category">{t('inputGuard.rules.fieldCategory')}</label>
            <input
              id="ig-rule-category"
              type="text"
              {...register('category')}
              placeholder={t('inputGuard.rules.fieldCategoryPlaceholder')}
              aria-invalid={!!errors.category}
              aria-describedby={errors.category ? 'ig-rule-category-error' : undefined}
            />
            {errors.category && (
              <span id="ig-rule-category-error" className="form-error" role="alert">
                {errors.category.message}
              </span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="ig-rule-priority">
              {t('inputGuard.rules.fieldPriority')}
              <FieldStatusIndicator status={priorityStatus} />
            </label>
            <input
              id="ig-rule-priority"
              type="number"
              min={0}
              max={10000}
              {...register('priority', { valueAsNumber: true })}
              aria-invalid={!!errors.priority}
              aria-describedby={errors.priority ? 'ig-rule-priority-error' : 'ig-rule-priority-hint'}
            />
            {hint('inputGuard.rules.hintPriority') && (
              <p id="ig-rule-priority-hint" className="form-hint">{hint('inputGuard.rules.hintPriority')}</p>
            )}
            {errors.priority && (
              <span id="ig-rule-priority-error" className="form-error" role="alert">
                {errors.priority.message}
              </span>
            )}
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="ig-rule-desc">{t('inputGuard.rules.fieldDescription')}</label>
          <textarea
            id="ig-rule-desc"
            rows={2}
            {...register('description')}
            aria-invalid={!!errors.description}
            aria-describedby={errors.description ? 'ig-rule-desc-error' : undefined}
          />
          {errors.description && (
            <span id="ig-rule-desc-error" className="form-error" role="alert">
              {errors.description.message}
            </span>
          )}
        </div>

        <div className="form-group form-check">
          <input id="ig-rule-enabled" type="checkbox" {...register('enabled')} />
          <label htmlFor="ig-rule-enabled">{t('inputGuard.rules.fieldEnabled')}</label>
        </div>

        <div className="modal-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={saving}
          >
            {t('common.cancel')}
          </button>
          <button type="submit" className="btn btn-primary" disabled={submitDisabled}>
            {saving ? <LoadingSpinner size="sm" /> : t('common.save')}
          </button>
        </div>
      </form>
      )}
    </DetailModal>
  )
}

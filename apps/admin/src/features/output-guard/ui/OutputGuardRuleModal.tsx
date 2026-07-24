import { useRef, useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { DetailModal, LoadingSpinner, FieldStatusIndicator, useAnnouncer } from '../../../shared/ui'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useFieldStatus } from '../../../shared/lib/useFieldStatus'
import { useFormFirstFieldFocus } from '../../../shared/lib/useFormFirstFieldFocus'
import * as outputGuardApi from '../api'
import type { OutputGuardRule, OutputBlockAction } from '../types'
import { ruleFormSchema, keywordsToPattern, type RuleFormValues } from '../schema'
import { getRegexIssue } from '../outputGuardOps'

type RuleMode = 'preset' | 'keyword' | 'regex'

interface OutputGuardRuleModalProps {
  open: boolean
  onClose: () => void
  onSaved: () => void
  rule?: OutputGuardRule | null
}

interface PresetDefinition {
  key: string
  icon: string
  nameKey: string
  pattern: string
  action: OutputBlockAction
  priority: number
}

const PRESETS: PresetDefinition[] = [
  {
    key: 'email',
    icon: '\u{1F4E7}',
    nameKey: 'outputGuardPage.preset.email',
    pattern: '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}',
    action: 'MASK',
    priority: 100,
  },
  {
    key: 'phone',
    icon: '\u{1F4F1}',
    nameKey: 'outputGuardPage.preset.phone',
    pattern: '(\\+?\\d{1,3}[- ]?)?\\(?\\d{2,4}\\)?[- ]?\\d{3,4}[- ]?\\d{4}',
    action: 'MASK',
    priority: 100,
  },
  {
    key: 'apiKey',
    icon: '\u{1F511}',
    nameKey: 'outputGuardPage.preset.apiKey',
    pattern: '(?:api[_-]?key|token|secret)[\\s:=]+["\']?[A-Za-z0-9_\\-]{20,}',
    action: 'REJECT',
    priority: 50,
  },
  {
    key: 'creditCard',
    icon: '\u{1F4B3}',
    nameKey: 'outputGuardPage.preset.creditCard',
    pattern: '\\b\\d{4}[- ]?\\d{4}[- ]?\\d{4}[- ]?\\d{4}\\b',
    action: 'MASK',
    priority: 100,
  },
  {
    key: 'rrn',
    icon: '\u{1F194}',
    nameKey: 'outputGuardPage.preset.rrn',
    pattern: '\\b\\d{6}[- ]?\\d{7}\\b',
    action: 'REJECT',
    priority: 50,
  },
  {
    key: 'bankAccount',
    icon: '\u{1F3E6}',
    nameKey: 'outputGuardPage.preset.bankAccount',
    pattern: '\\b\\d{3,6}[- ]?\\d{2,6}[- ]?\\d{2,6}[- ]?\\d{0,4}\\b',
    action: 'MASK',
    priority: 100,
  },
]

const CREATE_DEFAULTS: RuleFormValues = {
  name: '',
  pattern: '',
  action: 'MASK',
  priority: 100,
  enabled: true,
}

export function OutputGuardRuleModal({ open, onClose, onSaved, rule }: OutputGuardRuleModalProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { announce } = useAnnouncer()

  const isEdit = !!rule
  const [mode, setMode] = useState<RuleMode>('preset')
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null)
  const [keywords, setKeywords] = useState('')
  const formRef = useRef<HTMLFormElement>(null)
  useFormFirstFieldFocus(formRef, open)

  const {
    register,
    handleSubmit,
    setValue,
    control,
    setError,
    formState: { errors, dirtyFields },
  } = useForm<RuleFormValues>({
    resolver: zodResolver(ruleFormSchema),
    mode: 'onChange',
    defaultValues: rule
      ? {
          name: rule.name,
          pattern: rule.pattern,
          action: rule.action,
          priority: rule.priority,
          enabled: rule.enabled,
        }
      : CREATE_DEFAULTS,
  })

  const watchedPattern = useWatch({ control, name: 'pattern' })
  const watchedName = useWatch({ control, name: 'name' })
  const watchedPriority = useWatch({ control, name: 'priority' })
  const regexIssue = watchedPattern?.trim() ? getRegexIssue(watchedPattern) : null

  const nameStatus = useFieldStatus({
    value: watchedName,
    hasError: !!errors.name,
    isDirty: !!dirtyFields.name,
  })
  const patternStatus = useFieldStatus({
    value: watchedPattern,
    hasError: !!errors.pattern || !!regexIssue,
    isDirty: !!dirtyFields.pattern,
  })
  const priorityStatus = useFieldStatus({
    value: watchedPriority,
    hasError: !!errors.priority,
    isDirty: !!dirtyFields.priority,
  })

  const createMutation = useMutation({
    mutationFn: outputGuardApi.createRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.outputGuard.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.created') })
      announce(t('common.a11y.created'))
      onSaved()
      onClose()
    },
    onError: (err: Error) => {
      setError('root', { message: err.message })
      announce(err.message, { priority: 'assertive' })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: RuleFormValues }) =>
      outputGuardApi.updateRule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.outputGuard.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      announce(t('common.a11y.updated'))
      onSaved()
      onClose()
    },
    onError: (err: Error) => {
      setError('root', { message: err.message })
      announce(err.message, { priority: 'assertive' })
    },
  })

  const saving = createMutation.isPending || updateMutation.isPending

  function handlePresetClick(preset: PresetDefinition) {
    setSelectedPreset(preset.key)
    setValue('name', t(preset.nameKey))
    setValue('pattern', preset.pattern)
    setValue('action', preset.action)
    setValue('priority', preset.priority)
  }

  function handleKeywordChange(value: string) {
    setKeywords(value)
    const pattern = keywordsToPattern(value)
    setValue('pattern', pattern)
  }

  function onSubmit(data: RuleFormValues) {
    // Validate regex before sending
    if (regexIssue) {
      setError('pattern', {
        message: t('outputGuardPage.validation.invalidRegex', { message: regexIssue }),
      })
      return
    }

    if (isEdit && rule) {
      updateMutation.mutate({ id: rule.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  const title = isEdit ? t('outputGuardPage.editRule') : t('outputGuardPage.createRule')

  return (
    <DetailModal open={open} title={title} onClose={onClose}>
      {/* Mode tabs - only in create mode */}
      {!isEdit && (
        <div className="rule-mode-tabs">
          <button
            type="button"
            className={mode === 'preset' ? 'active' : ''}
            onClick={() => setMode('preset')}
          >
            {t('outputGuardPage.modePreset')}
          </button>
          <button
            type="button"
            className={mode === 'keyword' ? 'active' : ''}
            onClick={() => setMode('keyword')}
          >
            {t('outputGuardPage.modeKeyword')}
          </button>
          <button
            type="button"
            className={mode === 'regex' ? 'active' : ''}
            onClick={() => setMode('regex')}
          >
            {t('outputGuardPage.modeRegex')}
          </button>
        </div>
      )}

      <form ref={formRef} onSubmit={handleSubmit(onSubmit)} noValidate>
        {errors.root && (
          <div className="alert alert-error" role="alert">
            {errors.root.message}
          </div>
        )}

        {/* Preset mode */}
        {!isEdit && mode === 'preset' && (
          <>
            <div className="preset-grid">
              {PRESETS.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  className={`preset-card${selectedPreset === preset.key ? ' selected' : ''}`}
                  onClick={() => handlePresetClick(preset)}
                >
                  <span className="preset-card__icon">{preset.icon}</span>
                  <span>{t(preset.nameKey)}</span>
                </button>
              ))}
            </div>

            {selectedPreset && (
              <>
                <div className="form-group">
                  <label htmlFor="rule-name">
                    {t('common.name')}
                    <span className="form-label-required" aria-hidden="true">*</span>
                    <FieldStatusIndicator status={nameStatus} />
                  </label>
                  <input
                    id="rule-name"
                    aria-required="true"
                    {...register('name')}
                    aria-invalid={!!errors.name}
                    aria-describedby={errors.name ? 'rule-name-error' : undefined}
                  />
                  {errors.name && (
                    <span id="rule-name-error" className="form-error" role="alert">{errors.name.message}</span>
                  )}
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label htmlFor="rule-action">{t('outputGuardPage.ruleAction')}</label>
                    <select id="rule-action" {...register('action')}>
                      <option value="MASK">MASK</option>
                      <option value="REJECT">REJECT</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label htmlFor="rule-priority">
                      {t('outputGuardPage.rulePriority')}
                      <span className="form-label-required" aria-hidden="true">*</span>
                      <FieldStatusIndicator status={priorityStatus} />
                    </label>
                    <input
                      id="rule-priority"
                      type="number"
                      min={1}
                      max={10000}
                      aria-required="true"
                      {...register('priority', { valueAsNumber: true })}
                      aria-invalid={!!errors.priority}
                      aria-describedby={errors.priority ? 'rule-priority-error' : undefined}
                    />
                    {errors.priority && (
                      <span id="rule-priority-error" className="form-error" role="alert">{errors.priority.message}</span>
                    )}
                  </div>
                </div>
                <div className="form-group form-check">
                  <input id="rule-enabled" type="checkbox" {...register('enabled')} />
                  <label htmlFor="rule-enabled">{t('common.enabled')}</label>
                </div>
              </>
            )}
          </>
        )}

        {/* Keyword mode */}
        {!isEdit && mode === 'keyword' && (
          <>
            <div className="form-group">
              <label htmlFor="rule-name">
                {t('common.name')}
                <span className="form-label-required" aria-hidden="true">*</span>
                <FieldStatusIndicator status={nameStatus} />
              </label>
              <input
                id="rule-name"
                aria-required="true"
                {...register('name')}
                aria-invalid={!!errors.name}
                aria-describedby={errors.name ? 'rule-name-error' : undefined}
              />
              {errors.name && (
                <span id="rule-name-error" className="form-error" role="alert">{errors.name.message}</span>
              )}
            </div>
            <div className="form-group">
              <label htmlFor="rule-keywords">
                {t('outputGuardPage.keywordLabel')}
                <span className="form-label-required" aria-hidden="true">*</span>
              </label>
              <input
                id="rule-keywords"
                aria-required="true"
                value={keywords}
                onChange={(e) => handleKeywordChange(e.target.value)}
                placeholder={t('outputGuardPage.keywordPlaceholder')}
                aria-describedby="rule-keywords-hint"
              />
              <span id="rule-keywords-hint" className="form-hint">{t('outputGuardPage.keywordHelp')}</span>
            </div>
            {watchedPattern && (
              <div className="form-group">
                <label>{t('outputGuardPage.regexPattern')}</label>
                <pre className="code-block">{watchedPattern}</pre>
              </div>
            )}
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="rule-action">{t('outputGuardPage.ruleAction')}</label>
                <select id="rule-action" {...register('action')}>
                  <option value="MASK">MASK</option>
                  <option value="REJECT">REJECT</option>
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="rule-priority">
                  {t('outputGuardPage.rulePriority')}
                  <span className="form-label-required" aria-hidden="true">*</span>
                  <FieldStatusIndicator status={priorityStatus} />
                </label>
                <input
                  id="rule-priority"
                  type="number"
                  min={1}
                  max={10000}
                  aria-required="true"
                  {...register('priority', { valueAsNumber: true })}
                  aria-invalid={!!errors.priority}
                  aria-describedby={errors.priority ? 'rule-priority-error' : undefined}
                />
                {errors.priority && (
                  <span id="rule-priority-error" className="form-error" role="alert">{errors.priority.message}</span>
                )}
              </div>
            </div>
            <div className="form-group form-check">
              <input id="rule-enabled" type="checkbox" {...register('enabled')} />
              <label htmlFor="rule-enabled">{t('common.enabled')}</label>
            </div>
          </>
        )}

        {/* Regex mode (also used for edit) */}
        {(isEdit || mode === 'regex') && (
          <>
            <div className="form-group">
              <label htmlFor="rule-name">
                {t('common.name')}
                <span className="form-label-required" aria-hidden="true">*</span>
                <FieldStatusIndicator status={nameStatus} />
              </label>
              <input
                id="rule-name"
                aria-required="true"
                {...register('name')}
                aria-invalid={!!errors.name}
                aria-describedby={errors.name ? 'rule-name-error' : undefined}
              />
              {errors.name && (
                <span id="rule-name-error" className="form-error" role="alert">{errors.name.message}</span>
              )}
            </div>
            <div className="form-group">
              <label htmlFor="rule-pattern">
                {t('outputGuardPage.regexPattern')}
                <span className="form-label-required" aria-hidden="true">*</span>
                <FieldStatusIndicator status={patternStatus} />
              </label>
              <textarea
                id="rule-pattern"
                rows={4}
                aria-required="true"
                {...register('pattern')}
                aria-invalid={!!errors.pattern || !!regexIssue}
                aria-describedby={errors.pattern ? 'rule-pattern-error' : undefined}
              />
              {errors.pattern && (
                <span id="rule-pattern-error" className="form-error" role="alert">{errors.pattern.message}</span>
              )}
            </div>
            {regexIssue && (
              <div className="alert alert-error" role="alert" style={{ marginBottom: 'var(--space-3)' }}>
                {t('outputGuardPage.validation.invalidRegex', { message: regexIssue })}
              </div>
            )}
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="rule-action">{t('outputGuardPage.ruleAction')}</label>
                <select id="rule-action" {...register('action')}>
                  <option value="MASK">MASK</option>
                  <option value="REJECT">REJECT</option>
                </select>
              </div>
              <div className="form-group">
                <label htmlFor="rule-priority">
                  {t('outputGuardPage.rulePriority')}
                  <span className="form-label-required" aria-hidden="true">*</span>
                  <FieldStatusIndicator status={priorityStatus} />
                </label>
                <input
                  id="rule-priority"
                  type="number"
                  min={1}
                  max={10000}
                  aria-required="true"
                  {...register('priority', { valueAsNumber: true })}
                  aria-invalid={!!errors.priority}
                  aria-describedby={errors.priority ? 'rule-priority-error' : undefined}
                />
                {errors.priority && (
                  <span id="rule-priority-error" className="form-error" role="alert">{errors.priority.message}</span>
                )}
              </div>
            </div>
            <div className="form-group form-check">
              <input id="rule-enabled" type="checkbox" {...register('enabled')} />
              <label htmlFor="rule-enabled">{t('common.enabled')}</label>
            </div>
          </>
        )}

        {/* Hidden pattern field for preset/keyword modes (already registered via watch) */}
        {!isEdit && mode !== 'regex' && (
          <input type="hidden" {...register('pattern')} />
        )}

        {/* Submit - show only when form fields are visible */}
        {(isEdit || mode === 'regex' || mode === 'keyword' || (mode === 'preset' && selectedPreset)) && (
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              {t('common.cancel')}
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? <LoadingSpinner size="sm" /> : t('common.save')}
            </button>
          </div>
        )}
      </form>
    </DetailModal>
  )
}

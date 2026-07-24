import { useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Check, CircleAlert } from 'lucide-react'
import { useFocusTrap } from '../../../shared/lib/useFocusTrap'
import { useFormFirstFieldFocus } from '../../../shared/lib/useFormFirstFieldFocus'
import { useEscapeKey } from '../../../shared/lib/useEscapeKey'
import { useBodyOverflowLock } from '../../../shared/lib/useBodyOverflowLock'
import { LoadingSpinner, NumberInputStepper, ToggleSwitch } from '../../../shared/ui'
import {
  inferTypeFromKey,
  inferTypeFromValue,
  serializeValue,
  validateJson,
  valueTypeKinds,
} from '../schema'
import type { ValueTypeKind } from '../schema'
import type { AdminSetting } from '../types'
import { getOperatorSettingName } from '../settingDisplay'

interface SettingEditModalProps {
  setting: AdminSetting
  isPending: boolean
  onSave: (value: string) => void
  onClose: () => void
}

/**
 * Determine which kind should be pre-selected when the modal opens.
 * Order of precedence:
 *   1. Explicit backend type (boolean / number / json are trusted).
 *   2. Key-name heuristics (*.enabled, *.order, *.requestsPerMinute, ...).
 *   3. Best-effort sniff of the raw stored value.
 *   4. Fallback to "string".
 */
function pickInitialKind(setting: AdminSetting): ValueTypeKind {
  const type = setting.type.toLowerCase()
  if (type === 'boolean') return 'boolean'
  if (type === 'number' || type === 'integer') return 'number'
  if (type === 'json') {
    // Distinguish object vs array from the payload when possible.
    const sniff = inferTypeFromValue(setting.value)
    return sniff === 'array' ? 'array' : 'object'
  }
  const byKey = inferTypeFromKey(setting.key)
  if (byKey) return byKey
  if (type === 'string' && setting.value) return inferTypeFromValue(setting.value)
  return 'string'
}

function labelForKind(t: (k: string) => string, kind: ValueTypeKind): string {
  switch (kind) {
    case 'string':
      return t('settingsPage.edit.typeString')
    case 'number':
      return t('settingsPage.edit.typeNumber')
    case 'boolean':
      return t('settingsPage.edit.typeBoolean')
    case 'object':
      return t('settingsPage.edit.typeObject')
    case 'array':
      return t('settingsPage.edit.typeArray')
  }
}

export function SettingEditModal({ setting, isPending, onSave, onClose }: SettingEditModalProps) {
  const { t } = useTranslation()
  const settingLabels = {
    cacheEnabled: t('adminSettingsTab.settingLabels.cacheEnabled'),
    unknown: t('adminSettingsTab.unknownSetting'),
  }
  const modalRef = useRef<HTMLDivElement>(null)
  const formRef = useRef<HTMLFormElement>(null)

  useFocusTrap(modalRef, true)
  // Modal is mounted only while open, so trigger focus on first mount.
  // Run after useFocusTrap so the first form field wins over the close button.
  // Skip the value-type meta select — the editable value control is what the
  // admin actually wants focused.
  useFormFirstFieldFocus(formRef, true, {
    selector:
      'input:not([type="hidden"]):not([disabled]):not([readonly]),' +
      'textarea:not([disabled]):not([readonly]),' +
      'select:not([disabled]):not(#setting-value-type)',
  })
  useEscapeKey(true, onClose)
  useBodyOverflowLock(true)

  const isSecret = setting.type.toLowerCase() === 'secret'
  const settingName = getOperatorSettingName(setting, settingLabels)

  // For SECRET we keep the original freeform behavior (empty means "keep").
  const [kind, setKind] = useState<ValueTypeKind>(() => (isSecret ? 'string' : pickInitialKind(setting)))
  const [rawValue, setRawValue] = useState<string>(() => (isSecret ? '' : setting.value))
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Live validation derived from the current raw value + selected kind.
  const jsonCheck = useMemo(() => {
    if (kind !== 'object' && kind !== 'array') return null
    return validateJson(rawValue, kind)
  }, [rawValue, kind])

  const numberInvalid = kind === 'number' && rawValue !== '' && Number.isNaN(Number(rawValue))
  const hasRequiredError = !isSecret && rawValue.trim() === '' && kind !== 'boolean'
  const canSubmit = (() => {
    if (isSubmitting || isPending) return false
    if (isSecret) return true // empty means keep
    if (hasRequiredError) return false
    if (numberInvalid) return false
    if (jsonCheck && !jsonCheck.valid) return false
    return true
  })()

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSubmitError(null)

    // SECRET: blank means keep existing, matches prior behavior.
    if (isSecret) {
      if (rawValue === '') return
      setIsSubmitting(true)
      try {
        onSave(rawValue)
      } finally {
        setIsSubmitting(false)
      }
      return
    }

    try {
      const serialized = serializeValue(rawValue, kind)
      setIsSubmitting(true)
      onSave(serialized)
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Invalid value')
    } finally {
      setIsSubmitting(false)
    }
  }

  function renderValueControl() {
    const disabled = isSubmitting || isPending
    const commonAria = {
      'aria-describedby': submitError ? 'value-error' : undefined,
    }

    if (isSecret) {
      return (
        <>
          <input
            id="setting-value"
            type="password"
            value={rawValue}
            onChange={e => setRawValue(e.target.value)}
            placeholder={t('adminSettingsTab.leaveBlankToKeep')}
            disabled={disabled}
            aria-label={t('adminSettingsTab.value')}
          />
          <p className="detail-note">{t('adminSettingsTab.leaveBlankToKeep')}</p>
        </>
      )
    }

    switch (kind) {
      case 'boolean':
        return (
          <div className="setting-edit-boolean">
            <ToggleSwitch
              checked={rawValue === 'true'}
              disabled={disabled}
              label={t('adminSettingsTab.value')}
              onChange={checked => setRawValue(checked ? 'true' : 'false')}
            />
            <span>{rawValue === 'true' ? t('adminSettingsTab.booleanEnabled') : t('adminSettingsTab.booleanDisabled')}</span>
          </div>
        )
      case 'number': {
        const parsedNumeric = rawValue === '' ? null : Number(rawValue)
        const numericValue = parsedNumeric !== null && Number.isNaN(parsedNumeric) ? null : parsedNumeric
        return (
          <NumberInputStepper
            id="setting-value"
            value={numericValue}
            onChange={(next) => setRawValue(next === null ? '' : String(next))}
            disabled={disabled}
            ariaLabel={t('adminSettingsTab.value')}
            aria-invalid={numberInvalid}
            aria-describedby={submitError ? 'value-error' : undefined}
          />
        )
      }
      case 'object':
      case 'array': {
        const valid = jsonCheck?.valid === true
        return (
          <>
            <textarea
              id="setting-value"
              value={rawValue}
              onChange={e => setRawValue(e.target.value)}
              rows={10}
              spellCheck={false}
              wrap="off"
              disabled={disabled}
              aria-invalid={jsonCheck != null && !jsonCheck.valid}
              aria-label={t('adminSettingsTab.value')}
              style={{
                fontFamily: 'var(--font-mono)',
                whiteSpace: 'pre',
                overflowWrap: 'normal',
                overflowX: 'auto',
              }}
              {...commonAria}
            />
            <div
              className={`setting-edit-validation ${valid ? 'is-valid' : 'is-invalid'}`}
              role="status"
              aria-live="polite"
              title={!valid ? jsonCheck?.error : undefined}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 'var(--space-1)',
                marginTop: 'var(--space-1)',
                width: 'fit-content',
                cursor: !valid && jsonCheck?.error ? 'help' : 'default',
              }}
            >
              {valid ? <Check size={14} aria-hidden="true" /> : <CircleAlert size={14} aria-hidden="true" />}
              <span>{valid ? t('settingsPage.edit.jsonValid') : t('settingsPage.edit.jsonInvalid')}</span>
            </div>
          </>
        )
      }
      case 'string':
      default:
        return (
          <input
            id="setting-value"
            type="text"
            value={rawValue}
            onChange={e => setRawValue(e.target.value)}
            disabled={disabled}
            aria-label={t('adminSettingsTab.value')}
            {...commonAria}
          />
        )
    }
  }

  return createPortal(
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal modal-lg"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="setting-edit-modal-title"
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span id="setting-edit-modal-title">{t('adminSettingsTab.editSetting')}</span>
          <button className="detail-close-btn" onClick={onClose} aria-label={t('common.close')}>
            ×
          </button>
        </div>

        <form ref={formRef} onSubmit={handleSubmit}>
          <div className="setting-edit-context">
            <h3>{settingName}</h3>
            <p>{t('adminSettingsTab.editDescription')}</p>
          </div>

          <div className="form-group">
            <label htmlFor="setting-value">{t('adminSettingsTab.newValue')}</label>
            {renderValueControl()}
            {submitError && (
              <div id="value-error" role="alert" className="form-error">
                {submitError}
              </div>
            )}
          </div>

          <details className="setting-edit-technical">
            <summary>{t('adminSettingsTab.developerDetails')}</summary>
            <div className="form-group">
              <label>{t('adminSettingsTab.key')}</label>
              <code className="code-block setting-edit-technical__key">{setting.key}</code>
            </div>

            {!isSecret && (
              <div className="form-group">
                <label htmlFor="setting-value-type">{t('settingsPage.edit.typeLabel')}</label>
                <select
                  id="setting-value-type"
                  className="form-select"
                  value={kind}
                  onChange={e => setKind(e.target.value as ValueTypeKind)}
                  disabled={isSubmitting || isPending}
                >
                  {valueTypeKinds.map(k => (
                    <option key={k} value={k}>
                      {labelForKind(t, k)}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </details>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!canSubmit}
            >
              {isPending ? <LoadingSpinner size="sm" /> : t('common.save')}
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  )
}

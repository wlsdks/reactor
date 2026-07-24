import type { Control, FieldErrors, UseFormRegister } from 'react-hook-form'
import { useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import type { McpServerFormValues } from '../schema'
import { KNOWN_MCP_SERVER_PRESETS, type KnownMcpServerKind } from '../presets'

const PRESET_LABEL: Record<KnownMcpServerKind, string> = {
  atlassian: 'mcpServers.register.presetAtlassian',
  swagger: 'mcpServers.register.presetSwagger',
  generic: 'mcpServers.register.presetGeneric',
}

interface RegisterServerStep1Props {
  register: UseFormRegister<McpServerFormValues>
  errors: FieldErrors<McpServerFormValues>
  control: Control<McpServerFormValues>
  isEditMode: boolean
  matchedPreset: KnownMcpServerKind | null
  onApplyPreset: (kind: KnownMcpServerKind) => void
  onNext: () => void
  onCancel: () => void
}

export function RegisterServerStep1({
  register,
  errors,
  control,
  isEditMode,
  matchedPreset,
  onApplyPreset,
  onNext,
  onCancel,
}: RegisterServerStep1Props) {
  // React Compiler memoization can cache the JSX subtree containing the `register('name')`
  // spread, preventing change events from reaching form state when register is received as
  // a prop. Opt out so the input wiring re-evaluates on every render.
  'use no memo'

  const { t } = useTranslation()
  const nameValue = useWatch({ control, name: 'name', defaultValue: '' })

  return (
    <>
      {/* Preset buttons */}
      <section style={{ marginBottom: 'var(--space-6)' }}>
        <div
          style={{
            fontSize: 'var(--text-xxs)',
            fontWeight: 'var(--font-weight-strong)',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
            marginBottom: 'var(--space-2)',
          }}
        >
          {t('mcpServers.quickPresetsTitle')}
        </div>
        <p
          style={{
            fontSize: '0.78rem',
            color: 'var(--text-dim)',
            marginBottom: 'var(--space-3)',
          }}
        >
          {t('mcpServers.quickPresetsDescription')}
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          {KNOWN_MCP_SERVER_PRESETS.map((kind) => (
            <button
              key={kind}
              type="button"
              className={`btn btn-secondary${matchedPreset === kind ? ' btn-active' : ''}`}
              onClick={() => {
                if (!isEditMode) onApplyPreset(kind)
              }}
              disabled={isEditMode}
              style={isEditMode ? { opacity: matchedPreset === kind ? 1 : 0.4, cursor: 'not-allowed' } : undefined}
              aria-label={t(PRESET_LABEL[kind])}
            >
              {t(PRESET_LABEL[kind])}
            </button>
          ))}
        </div>
      </section>

      {/* Server Name */}
      <div className="form-group">
        <label htmlFor="register-name">{t('mcpServers.register.fieldName')}</label>
        <input
          id="register-name"
          {...register('name')}
          disabled={isEditMode}
          placeholder={t('mcpServers.register.serverNamePlaceholder')}
          style={isEditMode ? { opacity: 0.6, cursor: 'not-allowed' } : undefined}
          aria-invalid={!!errors.name}
          aria-describedby={errors.name ? 'register-name-error' : undefined}
        />
        {errors.name && <p id="register-name-error" className="form-error" role="alert">{errors.name.message}</p>}
      </div>

      {/* Step 1 actions */}
      <div className="modal-actions">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onCancel}
        >
          {t('common.cancel')}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!nameValue?.trim()}
          onClick={onNext}
        >
          {t('mcpServers.register.next')}
        </button>
      </div>
    </>
  )
}

export { PRESET_LABEL }

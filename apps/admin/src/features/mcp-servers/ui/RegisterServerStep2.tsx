import type { FieldErrors, UseFormRegister, UseFormSetValue } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { OperationButton } from '../../../shared/ui'
import type { McpServerFormValues } from '../schema'
import { KNOWN_MCP_SERVER_PRESETS, type KnownMcpServerKind } from '../presets'
import { PRESET_LABEL } from './RegisterServerStep1'

interface RegisterServerStep2Props {
  register: UseFormRegister<McpServerFormValues>
  errors: FieldErrors<McpServerFormValues>
  setValue: UseFormSetValue<McpServerFormValues>
  isEditMode: boolean
  matchedPreset: KnownMcpServerKind | null
  tags: string[]
  suggestedTags: string[]
  tagInput: string
  setTagInput: (value: string) => void
  getTagColor: (tag: string) => string
  isSubmitting: boolean
  isMutating: boolean
  onBack: () => void
  onCancel: () => void
}

export function RegisterServerStep2({
  register,
  errors,
  setValue,
  isEditMode,
  matchedPreset,
  tags,
  suggestedTags,
  tagInput,
  setTagInput,
  getTagColor,
  isSubmitting,
  isMutating,
  onBack,
  onCancel,
}: RegisterServerStep2Props) {
  // React Compiler memoization can cache the JSX subtree containing `register(...)`
  // spreads, preventing change events from reaching form state when register is received
  // as a prop. Opt out so the input wiring re-evaluates on every render.
  'use no memo'

  const { t } = useTranslation()

  function handleTagKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== 'Enter') return
    e.preventDefault()
    const trimmed = tagInput.trim()
    if (!trimmed) return
    if (!tags.includes(trimmed)) {
      setValue('tags', [...tags, trimmed])
    }
    setTagInput('')
  }

  function removeTag(tag: string) {
    setValue('tags', tags.filter((t) => t !== tag))
  }

  function addSuggestedTag(tag: string) {
    if (!tags.includes(tag)) {
      setValue('tags', [...tags, tag])
    }
  }

  return (
    <>
      {/* Preset buttons — visible but non-interactive in step 2 edit mode */}
      {isEditMode && (
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
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            {KNOWN_MCP_SERVER_PRESETS.map((kind) => (
              <button
                key={kind}
                type="button"
                className={`btn btn-secondary${matchedPreset === kind ? ' btn-active' : ''}`}
                disabled
                style={{ opacity: matchedPreset === kind ? 1 : 0.4, cursor: 'not-allowed' }}
                aria-label={t(PRESET_LABEL[kind])}
              >
                {t(PRESET_LABEL[kind])}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Transport Type */}
      <div className="form-group">
        <label htmlFor="register-transport">{t('mcpServers.register.fieldTransport')}</label>
        <select
          id="register-transport"
          {...register('transportType')}
          aria-invalid={!!errors.transportType}
          aria-describedby={errors.transportType ? 'register-transport-error' : undefined}
        >
          <option value="STDIO">STDIO</option>
          <option value="STREAMABLE_HTTP">STREAMABLE_HTTP</option>
        </select>
        {errors.transportType && <p id="register-transport-error" className="form-error" role="alert">{errors.transportType.message}</p>}
      </div>

      {/* Config JSON */}
      <div className="form-group">
        <label htmlFor="register-config">{t('mcpServers.register.fieldConfig')}</label>
        <textarea
          id="register-config"
          {...register('configRaw')}
          rows={8}
          style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}
          spellCheck={false}
          aria-invalid={!!errors.configRaw}
          aria-describedby={errors.configRaw ? 'register-config-error' : undefined}
        />
        {errors.configRaw && <p id="register-config-error" className="form-error" role="alert">{errors.configRaw.message}</p>}
      </div>

      {/* Tags */}
      <div className="form-group">
        <label htmlFor="register-tags">{t('mcpServers.register.fieldTags')}</label>

        {/* Existing tag pills */}
        {tags.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', marginBottom: 'var(--space-2)' }}>
            {tags.map((tag) => {
              const color = getTagColor(tag)
              return (
                <span
                  key={tag}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 'var(--space-1)',
                    padding: '2px var(--space-2)',
                    borderRadius: 12,
                    fontSize: '0.75rem',
                    fontFamily: 'var(--font-mono)',
                    background: `${color}22`,
                    border: `1px solid ${color}55`,
                    color,
                  }}
                >
                  {tag}
                  <button
                    type="button"
                    onClick={() => removeTag(tag)}
                    aria-label={`Remove tag ${tag}`}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: '0 2px',
                      color: 'var(--text-muted)',
                      lineHeight: 1,
                      fontSize: 'var(--text-xxs)',
                    }}
                  >
                    ×
                  </button>
                </span>
              )
            })}
          </div>
        )}

        {/* Tag input */}
        <input
          id="register-tags"
          type="text"
          value={tagInput}
          onChange={(e) => setTagInput(e.target.value)}
          onKeyDown={handleTagKeyDown}
          placeholder={t('mcpServers.register.tagPlaceholder')}
          autoComplete="off"
        />

        {/* Autocomplete suggestions */}
        {suggestedTags.length > 0 && tagInput === '' && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)', marginTop: 'var(--space-2)' }}>
            {suggestedTags.slice(0, 10).map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => addSuggestedTag(tag)}
                style={{
                  padding: '2px var(--space-2)',
                  borderRadius: 12,
                  fontSize: '0.72rem',
                  fontFamily: 'var(--font-mono)',
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-dim)',
                  cursor: 'pointer',
                }}
              >
                {tag}
              </button>
            ))}
          </div>
        )}

        {errors.tags && <p id="register-tags-error" className="form-error">{String(errors.tags.message)}</p>}
      </div>

      {/* Step 2 actions */}
      <div className="modal-actions">
        {!isEditMode && (
          <OperationButton
            variant="secondary"
            onClick={onBack}
            disabled={isSubmitting || isMutating}
          >
            {t('mcpServers.register.back')}
          </OperationButton>
        )}
        <OperationButton
          variant="secondary"
          onClick={onCancel}
          disabled={isSubmitting || isMutating}
        >
          {t('common.cancel')}
        </OperationButton>
        <OperationButton
          type="submit"
          variant="primary"
          isOperating={isSubmitting || isMutating}
        >
          {isEditMode ? t('common.save') : t('mcpServers.registerButton')}
        </OperationButton>
      </div>
    </>
  )
}

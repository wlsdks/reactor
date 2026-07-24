import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { LoadingSpinner, EmptyState } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useToastStore } from '../../../shared/store/toast.store'
import * as inputGuardApi from '../api'
import type { StageConfigField } from '../api'

interface Props {
  stageName: string
}

/**
 * Stage tunable parameters panel — embedded inside the Pipeline drawer.
 *
 * UX rationale:
 * - Loads current effective values (default or runtime-overridden) + schema.
 * - Overridden fields get a yellow tinted background + badge for at-a-glance status.
 * - restartRequired fields get a red badge so operators know live-apply won't happen.
 * - Save button only enabled when diff is non-empty; counts the changed keys.
 *
 * The form (`StageConfigForm`) is split out so it can take `config` as a prop
 * and seed local draft state via a `useState` initializer. The outer panel
 * remounts the form on each new `query.data` reference (via `key`), which
 * replaces the previous setState-in-effect pattern that caused React Compiler
 * bail-outs.
 */
export function StageConfigPanel({ stageName }: Props) {
  const { t } = useTranslation()

  const query = useQuery({
    queryKey: queryKeys.inputGuard.stageConfig(stageName),
    queryFn: () => inputGuardApi.getStageConfig(stageName),
  })

  if (query.isLoading) return <LoadingSpinner size="sm" />
  if (!query.data) {
    return <div className="alert alert-error">{getErrorMessage(query.error)}</div>
  }

  const { config, note } = query.data
  const entries = Object.entries(config)

  if (entries.length === 0) {
    return <EmptyState message={note ?? t('inputGuard.stageConfig.empty')} />
  }

  // Remount the form whenever the fetched data is replaced
  // (initial load + post-save invalidation). `dataUpdatedAt` advances on each
  // successful refetch, so the inner form re-runs its useState initializer
  // and seeds draft from the freshest server values — replacing the prior
  // setState-in-effect on `[query.data]`.
  return (
    <StageConfigForm
      key={`${stageName}-${query.dataUpdatedAt}`}
      stageName={stageName}
      config={config}
    />
  )
}

interface StageConfigFormProps {
  stageName: string
  config: Record<string, StageConfigField>
}

function humanizeConfigKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/^./, (letter) => letter.toUpperCase())
}

function StageConfigForm({ stageName, config }: StageConfigFormProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)

  const [draft, setDraft] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {}
    for (const [k, v] of Object.entries(config)) initial[k] = v.value
    return initial
  })

  const mutation = useMutation({
    mutationFn: () =>
      inputGuardApi.updateStageConfig(stageName, {
        config: computeDiff(config, draft),
      }),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.inputGuard.stageConfig(stageName) })
      addToast({ type: 'success', message: res.note })
    },
    onError: (err: Error) =>
      addToast({ type: 'error', message: getErrorMessage(err) }),
  })

  const entries = Object.entries(config)
  const diff = computeDiff(config, draft)
  const diffCount = Object.keys(diff).length

  function resetDraft() {
    const reset: Record<string, string> = {}
    for (const [k, v] of Object.entries(config)) reset[k] = v.value
    setDraft(reset)
  }

  return (
    <div className="ig-stage-config">
      {entries.map(([key, spec]) => {
        const fieldLabel = t(`inputGuard.stageConfig.fields.${key}`, {
          defaultValue: humanizeConfigKey(key),
        })
        const fieldDescription = t(`inputGuard.stageConfig.fieldDescriptions.${key}`, {
          defaultValue: spec.description,
        })

        return (
          <div
            key={key}
            className={`ig-stage-config__field${spec.overridden ? ' ig-stage-config__field--overridden' : ''}`}
          >
          <div className="ig-stage-config__field-head">
            <label className="ig-stage-config__label" htmlFor={`stage-config-${stageName}-${key}`}>
              {fieldLabel}
            </label>
            {spec.overridden && (
              <span className="badge badge-yellow">
                {t('inputGuard.stageConfig.overriddenBadge')}
              </span>
            )}
            {spec.restartRequired && (
              <span className="badge badge-red">
                {t('inputGuard.stageConfig.restartRequiredBadge')}
              </span>
            )}
          </div>
          <div className="ig-stage-config__desc">{fieldDescription}</div>
          <input
            id={`stage-config-${stageName}-${key}`}
            className="ig-stage-config__input"
            type="text"
            value={draft[key] ?? ''}
            onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
            aria-label={fieldLabel}
          />
          <div className="ig-stage-config__default">
            {t('inputGuard.stageConfig.defaultLabel')}: <code>{spec.default}</code>
          </div>
          <details className="ig-stage-config__technical">
            <summary>{t('inputGuard.stageConfig.technicalField')}</summary>
            <code>{key}</code>
            <span>{spec.type}</span>
          </details>
          </div>
        )
      })}

      <div className="ig-stage-config__actions">
        {diffCount > 0 && (
          <button
            type="button"
            className="btn btn-sm btn-secondary"
            onClick={resetDraft}
          >
            {t('inputGuard.stageConfig.reset')}
          </button>
        )}
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={diffCount === 0 || mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? (
            <LoadingSpinner size="sm" />
          ) : (
            t('inputGuard.stageConfig.saveWithCount', { count: diffCount })
          )}
        </button>
      </div>
    </div>
  )
}

function computeDiff(
  config: Record<string, { value: string }>,
  draft: Record<string, string>,
): Record<string, string> {
  const diff: Record<string, string> = {}
  for (const [key, spec] of Object.entries(config)) {
    const draftVal = draft[key] ?? spec.value
    if (draftVal !== spec.value) diff[key] = draftVal
  }
  return diff
}

import { useState, type FormEvent } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { Ban } from 'lucide-react'
import { HelpHint, LoadingSpinner } from '../../../shared/ui'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import * as inputGuardApi from '../api'
import type { SimulateResponse, SimulateStageResult } from '../api'

/**
 * Translates a backend stage identifier (e.g. `UnicodeNormalization`,
 * `rate-limit`) into a Korean label. Falls back to the raw identifier when no
 * translation exists so newly-added backend stages stay visible until copy is
 * added — that is preferable to silently hiding a stage from operators.
 */
function localizeStage(t: TFunction, raw: string): string {
  const key = `inputGuard.stages.${raw}`
  const translated = t(key)
  return translated === key ? raw : translated
}

/**
 * Translates a backend reason / action code (e.g. `PROMPT_INJECTION`,
 * `RATE_LIMITED`) into Korean operator copy. Same fallback policy as
 * `localizeStage`.
 */
function localizeReasonCode(t: TFunction, raw: string): string {
  const key = `inputGuard.reasons.${raw}`
  const translated = t(key)
  return translated === key ? raw : translated
}

interface PresetDefinition {
  labelKey: string
  valueKey: string
}

const PRESETS: PresetDefinition[] = [
  { labelKey: 'inputGuard.simulate.presetNormal', valueKey: 'inputGuard.simulate.sampleNormal' },
  { labelKey: 'inputGuard.simulate.presetInjection', valueKey: 'inputGuard.simulate.sampleInjection' },
  { labelKey: 'inputGuard.simulate.presetLong', valueKey: 'LONG' }, // special
  { labelKey: 'inputGuard.simulate.presetKoreanGreeting', valueKey: 'inputGuard.simulate.sampleKoreanGreeting' },
  { labelKey: 'inputGuard.simulate.presetHomograph', valueKey: 'inputGuard.simulate.sampleHomograph' },
]

/**
 * Input Guard simulation — dry-run without touching production metrics.
 *
 * UX rationale:
 * - Sample preset buttons for quick testing of common attack patterns.
 * - Verdict banner (passed/blocked) with severity colour + blocking stage name.
 * - Per-stage timeline so operators see where in the pipeline a block occurred.
 * - userId field defaults to `simulate-admin` to avoid polluting real rate-limit buckets.
 */
export function InputGuardSimulateTab() {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [userId, setUserId] = useState('simulate-admin')
  const [result, setResult] = useState<SimulateResponse | null>(null)

  const mutation = useMutation({
    mutationFn: () => inputGuardApi.simulateInputGuard({ input, userId }),
    onSuccess: (res) => setResult(res),
  })

  const errorMsg = mutation.error ? getErrorMessage(mutation.error) : null

  function applyPreset(preset: PresetDefinition) {
    if (preset.valueKey === 'LONG') {
      setInput('a'.repeat(15000))
    } else {
      setInput(t(preset.valueKey))
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!input.trim()) return
    mutation.mutate()
  }

  return (
    <div>
      <div
        className="alert alert-info"
        style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-2)' }}
      >
        <span>{t('inputGuard.simulate.notice')}</span>
        <HelpHint label={t('inputGuard.helpHints.simulationNote')} />
      </div>

      <form className="detail-panel detail-panel--compact" onSubmit={handleSubmit}>
        <h2 className="section-title">{t('inputGuard.simulate.inputTitle')}</h2>

        <div className="ig-sim-presets">
          <span className="ig-sim-presets__label">{t('inputGuard.simulate.presets')}:</span>
          {PRESETS.map((p) => (
            <button
              key={p.labelKey}
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => applyPreset(p)}
            >
              {t(p.labelKey)}
            </button>
          ))}
        </div>

        <textarea
          className="ig-sim-textarea"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t('inputGuard.simulate.placeholder')}
          rows={5}
          maxLength={10000}
          aria-label={t('inputGuard.simulate.inputTitle')}
        />

        <div className="ig-sim-controls">
          <label htmlFor="sim-user" className="ig-toolbar__label">
            {t('inputGuard.simulate.userId')}
          </label>
          <input
            id="sim-user"
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            maxLength={120}
          />
          <span className="ig-sim-char-count">{formatLocaleNumber(input.length)} / 10,000</span>
          <div className="ig-toolbar__spacer" />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!input.trim() || mutation.isPending}
          >
            {mutation.isPending ? <LoadingSpinner size="sm" /> : t('inputGuard.simulate.run')}
          </button>
        </div>
      </form>

      {errorMsg && <div className="alert alert-error">{errorMsg}</div>}

      {result && (
        <>
          <div className={`ig-verdict ig-verdict--${result.passed ? 'passed' : 'blocked'}`}>
            <span className="ig-verdict__label">
              {result.passed
                ? t('inputGuard.simulate.verdictPassed')
                : t('inputGuard.simulate.verdictBlocked')}
            </span>
            <span className="ig-verdict__meta">
              {result.blockingStage && (
                <>
                  {t('inputGuard.simulate.blockingStage')}:{' '}
                  <strong>{localizeStage(t, result.blockingStage)}</strong>
                  {' · '}
                </>
              )}
              {t('inputGuard.simulate.totalDuration')}: {result.totalDurationMs}ms
            </span>
          </div>

          <div className="detail-panel detail-panel--compact">
            <h2
              className="section-title"
              style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}
            >
              {t('inputGuard.simulate.stageResults')}
              <HelpHint label={t('inputGuard.helpHints.stages')} />
            </h2>
            <div className="ig-stage-results">
              {result.stageResults.map((s, idx) => (
                <StageResultRow key={`${s.stage}-${idx}`} stage={s} t={t} />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

/**
 * Derives the visual intent of a stage row from its outcome:
 * - `rejected` — stage blocked the request (red emphasis, Ban icon)
 * - `warn` — stage passed but flagged the request (yellow emphasis)
 * - `passed` — stage allowed the request (green emphasis)
 *
 * The intent drives both the left-border accent and the badge color so the
 * blocking step is unmistakable when an operator skims the seven-stage timeline.
 */
function getStageIntent(stage: SimulateStageResult): 'passed' | 'warn' | 'rejected' {
  if (!stage.passed) return 'rejected'
  const action = stage.action.toLowerCase()
  if (action === 'warn' || action === 'flag') return 'warn'
  return 'passed'
}

function StageResultRow({ stage, t }: { stage: SimulateStageResult; t: TFunction }) {
  const intent = getStageIntent(stage)
  const badgeClass =
    intent === 'rejected' ? 'badge-red' : intent === 'warn' ? 'badge-yellow' : 'badge-green'
  return (
    <div className={`ig-stage-result ig-stage-result--${intent}`}>
      <span className="ig-stage-result__order" aria-hidden="true">
        {stage.order}
      </span>
      <span className="ig-stage-result__name" title={stage.stage}>
        {localizeStage(t, stage.stage)}
      </span>
      <span className={`badge ${badgeClass}`}>
        {intent === 'rejected' && (
          <Ban size={12} strokeWidth={2.25} aria-hidden="true" className="ig-stage-result__icon" />
        )}
        {localizeReasonCode(t, stage.action.toUpperCase())}
      </span>
      <span className="ig-stage-result__duration">{stage.durationMs}ms</span>
      {stage.reason && (
        <span className="ig-stage-result__reason">
          {stage.category && (
            <code title={stage.category}>{localizeReasonCode(t, stage.category)}</code>
          )}
          {stage.reason}
        </span>
      )}
    </div>
  )
}

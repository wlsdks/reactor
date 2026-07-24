import { useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { HelpHint, NumberInputStepper, OperationButton, SideDrawer } from '../../../shared/ui'
import { useFormFirstFieldFocus } from '../../../shared/lib/useFormFirstFieldFocus'
import {
  summarizeSchedulerFormReadiness,
  type SchedulerFormSignal,
  type SchedulerJobFormState,
} from '../schedulerForm'
import type { JobType, ScheduledJobResponse } from '../types'

// ── Props ──────────────────────────────────────────────────────────────────

interface SchedulerJobFormModalProps {
  form: SchedulerJobFormState
  editingJob: ScheduledJobResponse | null
  formError: string | null
  isSaving: boolean
  onFormChange: (updater: (current: SchedulerJobFormState) => SchedulerJobFormState) => void
  onSave: () => void
  onClose: () => void
}

// ── Helpers ────────────────────────────────────────────────────────────────

function describeFormSignal(signal: SchedulerFormSignal, t: (key: string) => string): string {
  return t(`scheduler.formSignalDetails.${signal.detailId}`)
}

// ── Component ──────────────────────────────────────────────────────────────

export function SchedulerJobFormModal({
  form,
  editingJob,
  formError,
  isSaving,
  onFormChange,
  onSave,
  onClose,
}: SchedulerJobFormModalProps) {
  const { t } = useTranslation()
  const formRef = useRef<HTMLDivElement>(null)
  // Modal is mounted only while open, so trigger focus on first mount.
  useFormFirstFieldFocus(formRef, true)

  function updateField<K extends keyof SchedulerJobFormState>(key: K, value: SchedulerJobFormState[K]) {
    onFormChange((current) => ({ ...current, [key]: value }))
  }

  function updateNumericField(key: 'agentMaxToolCalls' | 'maxRetryCount' | 'executionTimeoutMs', next: number | null) {
    updateField(key, next === null ? '' : String(next))
  }

  function parseNumericField(raw: string): number | null {
    if (raw.trim() === '') return null
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }

  const formReadiness = summarizeSchedulerFormReadiness(form)

  return (
    <SideDrawer
      open
      size="wide"
      title={editingJob ? t('scheduler.edit') : t('scheduler.create')}
      onClose={onClose}
    >
      <div ref={formRef} className="scheduler-job-form">
        {formError && <div className="alert alert-error">{formError}</div>}

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="scheduler-name">{t('common.name')}</label>
            <input id="scheduler-name" value={form.name} onChange={(event) => updateField('name', event.target.value)} />
          </div>
          <div className="form-group">
            <label htmlFor="scheduler-job-type">{t('scheduler.jobType')}</label>
            <select
              id="scheduler-job-type"
              value={form.jobType}
              onChange={(event) => updateField('jobType', event.target.value as JobType)}
            >
              <option value="AGENT">{t('scheduler.jobTypes.AGENT')}</option>
              <option value="MCP_TOOL">{t('scheduler.jobTypes.MCP_TOOL')}</option>
              <option value="PROMPT_LAB_AUTO_OPTIMIZE">{t('scheduler.jobTypes.PROMPT_LAB_AUTO_OPTIMIZE')}</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="scheduler-description">{t('common.description')}</label>
          <input id="scheduler-description" value={form.description} onChange={(event) => updateField('description', event.target.value)} />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="scheduler-cron" className="form-label--with-hint">
              {t('scheduler.scheduleLabel')}
              <HelpHint title={t('scheduler.cron')} label={t('scheduler.scheduleHelp')} />
            </label>
            <input id="scheduler-cron" value={form.cronExpression} onChange={(event) => updateField('cronExpression', event.target.value)} />
          </div>
          <div className="form-group">
            <label htmlFor="scheduler-timezone" className="form-label--with-hint">
              {t('scheduler.timezone')}
              <HelpHint title={t('scheduler.timezone')} label={t('scheduler.timezoneHelp')} />
            </label>
            <input id="scheduler-timezone" value={form.timezone} onChange={(event) => updateField('timezone', event.target.value)} />
          </div>
        </div>

        {form.jobType === 'AGENT' && (
          <>
            <div className="form-group">
              <label htmlFor="scheduler-agent-prompt">{t('scheduler.agentPrompt')}</label>
              <textarea id="scheduler-agent-prompt" rows={5} value={form.agentPrompt} onChange={(event) => updateField('agentPrompt', event.target.value)} />
            </div>
            <details className="scheduler-form-section">
              <summary>
                <span>{t('scheduler.advancedSettings')}</span>
                <small>{t('scheduler.advancedSettingsDescription')}</small>
              </summary>
              <div className="scheduler-form-section__body">
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="scheduler-persona-id">{t('scheduler.personaId')}</label>
                <input
                  id="scheduler-persona-id"
                  value={form.personaId}
                  onChange={(event) => updateField('personaId', event.target.value)}
                />
              </div>
              <div className="form-group">
                <label htmlFor="scheduler-agent-model">{t('scheduler.agentModel')}</label>
                <input
                  id="scheduler-agent-model"
                  value={form.agentModel}
                  onChange={(event) => updateField('agentModel', event.target.value)}
                />
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="scheduler-agent-system-prompt">{t('scheduler.agentSystemPrompt')}</label>
              <textarea
                id="scheduler-agent-system-prompt"
                rows={4}
                value={form.agentSystemPrompt}
                onChange={(event) => updateField('agentSystemPrompt', event.target.value)}
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="scheduler-max-tool-calls">{t('scheduler.maxToolCalls')}</label>
                <NumberInputStepper
                  id="scheduler-max-tool-calls"
                  value={parseNumericField(form.agentMaxToolCalls)}
                  onChange={(next) => updateNumericField('agentMaxToolCalls', next)}
                  min={1}
                  max={1000}
                  ariaLabel={t('scheduler.maxToolCalls')}
                />
              </div>
            </div>
              </div>
            </details>
          </>
        )}

        {form.jobType === 'MCP_TOOL' && (
          <>
            <div className="form-row">
              <div className="form-group">
                <label htmlFor="scheduler-mcp-server">{t('scheduler.mcpServer')}</label>
                <input id="scheduler-mcp-server" value={form.mcpServerName} onChange={(event) => updateField('mcpServerName', event.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="scheduler-tool-name">{t('scheduler.toolName')}</label>
                <input id="scheduler-tool-name" value={form.toolName} onChange={(event) => updateField('toolName', event.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="scheduler-tool-args">{t('scheduler.toolArguments')}</label>
              <textarea
                id="scheduler-tool-args"
                rows={6}
                value={form.toolArgumentsRaw}
                onChange={(event) => updateField('toolArgumentsRaw', event.target.value)}
              />
            </div>
          </>
        )}

        {form.jobType === 'PROMPT_LAB_AUTO_OPTIMIZE' && (
          <div className="form-group">
            <label htmlFor="scheduler-tool-args">{t('scheduler.promptOptimizationConfig')}</label>
            <textarea
              id="scheduler-tool-args"
              rows={6}
              value={form.toolArgumentsRaw}
              onChange={(event) => updateField('toolArgumentsRaw', event.target.value)}
            />
            <p className="detail-note">{t('scheduler.promptOptimizationConfigHelp')}</p>
          </div>
        )}

        <details className="scheduler-form-section">
          <summary>
            <span>{t('scheduler.deliverySettings')}</span>
            <small>{t('scheduler.deliverySettingsDescription')}</small>
          </summary>
          <div className="scheduler-form-section__body">
        <div className="form-group">
          <label htmlFor="scheduler-tags">{t('scheduler.tags')}</label>
          <input
            id="scheduler-tags"
            value={form.tagsRaw}
            onChange={(event) => updateField('tagsRaw', event.target.value)}
            placeholder={t('scheduler.tagsPlaceholder')}
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="scheduler-slack-channel">{t('scheduler.slackChannel')}</label>
            <input
              id="scheduler-slack-channel"
              value={form.slackChannelId}
              onChange={(event) => updateField('slackChannelId', event.target.value)}
            />
          </div>
          <div className="form-group">
            <label htmlFor="scheduler-teams-webhook">{t('scheduler.teamsWebhook')}</label>
            <input
              id="scheduler-teams-webhook"
              value={form.teamsWebhookUrl}
              onChange={(event) => updateField('teamsWebhookUrl', event.target.value)}
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group form-check">
            <input id="enabled" type="checkbox" checked={form.enabled} onChange={(event) => updateField('enabled', event.target.checked)} />
            <label htmlFor="enabled">{t('scheduler.enabled')}</label>
          </div>
          <div className="form-group form-check">
            <input id="retry" type="checkbox" checked={form.retryOnFailure} onChange={(event) => updateField('retryOnFailure', event.target.checked)} />
            <label htmlFor="retry">{t('scheduler.retryOnFailure')}</label>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="scheduler-max-retry">{t('scheduler.maxRetryCount')}</label>
            <NumberInputStepper
              id="scheduler-max-retry"
              value={parseNumericField(form.maxRetryCount)}
              onChange={(next) => updateNumericField('maxRetryCount', next)}
              min={0}
              max={20}
              ariaLabel={t('scheduler.maxRetryCount')}
            />
          </div>
          <div className="form-group">
            <label htmlFor="scheduler-timeout" className="form-label--with-hint">
              {t('scheduler.maximumExecutionTime')}
              <HelpHint title={t('scheduler.maximumExecutionTime')} label={t('scheduler.maximumExecutionTimeHelp')} />
            </label>
            <NumberInputStepper
              id="scheduler-timeout"
              value={parseNumericField(form.executionTimeoutMs)}
              onChange={(next) => updateNumericField('executionTimeoutMs', next)}
              min={0}
              max={3600000}
              step={1000}
              ariaLabel={t('scheduler.maximumExecutionTime')}
              suffix="ms"
            />
          </div>
        </div>
          </div>
        </details>

        <section className={`scheduler-form-review scheduler-form-review--${formReadiness.status.toLowerCase()}`}>
          <div className="detail-section-header">
            <h2 className="section-title">{t('scheduler.formReadinessTitle')}</h2>
            <span className={`scheduler-state scheduler-state--${formReadiness.status.toLowerCase()}`}>
              <span aria-hidden="true" />
              {formReadiness.failCount > 0 ? t('scheduler.formBlocked') : t('scheduler.formReady')}
            </span>
          </div>
          <p className="detail-note">{t('scheduler.formReadinessDescription')}</p>
          {formReadiness.signals.filter((signal) => signal.status === 'FAIL').map((signal) => (
            <p className="scheduler-form-review__blocker" key={signal.id}>
              <strong>{t(`scheduler.formSignals.${signal.id}`)}</strong>
              <span>{describeFormSignal(signal, t)}</span>
            </p>
          ))}
          {formReadiness.warnCount > 0 && (
            <details className="scheduler-form-review__warnings">
              <summary>{t('scheduler.formWarnings', { count: formReadiness.warnCount })}</summary>
              <ul>
                {formReadiness.signals.filter((signal) => signal.status === 'WARN').map((signal) => (
                  <li key={signal.id}>
                    <strong>{t(`scheduler.formSignals.${signal.id}`)}</strong>
                    <span>{describeFormSignal(signal, t)}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>

        <div className="modal-actions">
          <OperationButton variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </OperationButton>
          <OperationButton
            variant="primary"
            onClick={onSave}
            isOperating={isSaving}
          >
            {t('common.save')}
          </OperationButton>
        </div>
      </div>
    </SideDrawer>
  )
}

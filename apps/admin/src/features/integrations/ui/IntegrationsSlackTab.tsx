import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { HelpHint, OperationButton, ReleaseWorkflowBacklink, StatusBadge } from '../../../shared/ui'
import { RELEASE_SLACK_GATEWAY_PATH } from '../../../shared/releaseWorkflow'
import * as integrationsApi from '../api'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import type { HttpCallResult } from '../types'
import type { ControlPlaneProbeSnapshot } from '../controlPlaneProbes'
import { describeManifestStatus, describeProbeHttp, describeProbeReason, describeProbeStatus } from './probeDescribers'
import { IntegrationTestResult } from './IntegrationTestResult'

// ── Helpers ────────────────────────────────────────────────────────────────

type SlackMode = 'command' | 'event'

function isManualProbeBlocked(probe: ControlPlaneProbeSnapshot | null): boolean {
  return probe != null && (probe.status === 'FAIL' || probe.reason === 'notAdvertised')
}

// ── Props ──────────────────────────────────────────────────────────────────

interface IntegrationsSlackTabProps {
  commandProbe: ControlPlaneProbeSnapshot | null
  eventProbe: ControlPlaneProbeSnapshot | null
  error: string | null
  onError: (error: string | null) => void
}

// ── Component ──────────────────────────────────────────────────────────────

export function IntegrationsSlackTab({
  commandProbe,
  eventProbe,
  error,
  onError,
}: IntegrationsSlackTabProps) {
  const { t } = useTranslation()

  const [mode, setMode] = useState<SlackMode>('command')
  const [advancedOpen, setAdvancedOpen] = useState(false)

  // Command state
  const [command, setCommand] = useState('/ask')
  const [commandText, setCommandText] = useState('오늘 발생한 주요 문제를 알려줘')
  const [commandChannelId, setCommandChannelId] = useState('C_TEST_ADMIN')
  const [commandResponseUrl, setCommandResponseUrl] = useState('https://example.com/slack-response')
  const [sendingCommand, setSendingCommand] = useState(false)
  const [commandResult, setCommandResult] = useState<HttpCallResult | null>(null)

  // Event state
  const [eventPayloadRaw, setEventPayloadRaw] = useState(`{
  "type": "url_verification",
  "challenge": "test-challenge"
}`)
  const [eventRetryNum, setEventRetryNum] = useState('')
  const [eventRetryReason, setEventRetryReason] = useState('')
  const [sendingEvent, setSendingEvent] = useState(false)
  const [eventResult, setEventResult] = useState<HttpCallResult | null>(null)

  const activeProbe = mode === 'command' ? commandProbe : eventProbe
  const manualActionBlocked = isManualProbeBlocked(activeProbe)

  function applyPreset(type: SlackMode) {
    if (type === 'command') {
      setCommand('/ask')
      setCommandText('오늘 발생한 주요 문제를 세 가지로 정리해줘')
      return
    }
    setEventPayloadRaw(`{
  "type": "app_mention",
  "event": {
    "type": "app_mention",
    "text": "@bot summarize today's incidents"
  }
}`)
  }

  async function handleSendSlackCommand(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    if (!commandText.trim()) {
      onError(t('integrationsPage.errors.commandTextRequired'))
      return
    }

    setSendingCommand(true)
    onError(null)
    try {
      const result = await integrationsApi.sendSlackCommand({
        command,
        text: commandText,
        channelId: commandChannelId,
        responseUrl: commandResponseUrl,
      })
      setCommandResult(result)
    } catch (e) {
      onError(getErrorMessage(e))
    } finally {
      setSendingCommand(false)
    }
  }

  async function handleSendSlackEvent(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    if (!eventPayloadRaw.trim()) {
      onError(t('integrationsPage.errors.eventPayloadRequired'))
      return
    }

    setSendingEvent(true)
    onError(null)
    try {
      const payload = JSON.parse(eventPayloadRaw) as Record<string, unknown>
      const result = await integrationsApi.sendSlackEvent({
        payload,
        retryNum: eventRetryNum || undefined,
        retryReason: eventRetryReason || undefined,
      })
      setEventResult(result)
    } catch (e) {
      onError(getErrorMessage(e))
    } finally {
      setSendingEvent(false)
    }
  }

  const activeResult = mode === 'command' ? commandResult : eventResult

  return (
    <section className="integration-tool-workspace" aria-labelledby="integration-slack-tool-title">
      {error && <div className="alert alert-error">{error}</div>}

      <header className="integration-tool-workspace__header">
        <div>
          <h2 id="integration-slack-tool-title">{t('integrationsPage.testerTabSlack')}</h2>
          <p>{mode === 'command'
            ? t('integrationsPage.modeDescription.command')
            : t('integrationsPage.modeDescription.event')}</p>
        </div>
      </header>

      <div className="detail-tabs integration-tool-workspace__tabs" role="tablist" aria-label={t('integrationsPage.modeTablistLabel')}>
        <button id="integrations-slack-tab-command" className={`tab-btn ${mode === 'command' ? 'active' : ''}`} role="tab" type="button" aria-selected={mode === 'command'} aria-controls="integrations-slack-tabpanel" onClick={() => setMode('command')}>
          {t('integrationsPage.modeCommand')}
        </button>
        <button id="integrations-slack-tab-event" className={`tab-btn ${mode === 'event' ? 'active' : ''}`} role="tab" type="button" aria-selected={mode === 'event'} aria-controls="integrations-slack-tabpanel" onClick={() => setMode('event')}>
          {t('integrationsPage.modeEvent')}
        </button>
      </div>

      {activeProbe && (
        <section className={`integration-tool-readiness integration-tool-readiness--${activeProbe.status.toLowerCase()}`} aria-label={t('integrationsPage.toolReadiness.label')}>
          <span className="integration-tool-readiness__dot" aria-hidden />
          <div>
            <div className="integration-tool-readiness__title-row">
              <strong>{t('integrationsPage.toolReadiness.label')}</strong>
              <HelpHint
                label={t('integrationsPage.toolReadiness.help')}
                title={t('integrationsPage.toolReadiness.label')}
              />
            </div>
            <p>{describeProbeReason(t, activeProbe)}</p>
          </div>
          <details className="integration-tool-readiness__technical">
            <summary>{t('integrationsPage.toolReadiness.technicalDetails')}</summary>
            <dl>
              <div>
                <dt>{t('integrationsPage.probeManifest')}</dt>
                <dd>{describeManifestStatus(t, activeProbe)}</dd>
              </div>
              <div>
                <dt>{t('integrationsPage.status')}</dt>
                <dd>{describeProbeHttp(t, activeProbe)}</dd>
              </div>
            </dl>
            {activeProbe.detail ? <p>{activeProbe.detail}</p> : null}
          </details>
        </section>
      )}

      <form
        id="integrations-slack-tabpanel"
        className="integration-tool-form"
        role="tabpanel"
        aria-labelledby={mode === 'command' ? 'integrations-slack-tab-command' : 'integrations-slack-tab-event'}
        onSubmit={(event) => void (mode === 'command' ? handleSendSlackCommand(event) : handleSendSlackEvent(event))}
      >
        {mode === 'command' ? (
          <>
            <div className="form-group">
              <div className="integration-tool-form__field-heading">
                <label htmlFor="slack-command-text">{t('integrationsPage.commandText')}</label>
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => applyPreset(mode)}>
                  {t('integrationsPage.applyPreset')}
                </button>
              </div>
              <input id="slack-command-text" value={commandText} onChange={e => setCommandText(e.target.value)} />
            </div>
            <details
              className="integration-tool-form__advanced"
              open={advancedOpen}
              onToggle={(e) => setAdvancedOpen((e.target as HTMLDetailsElement).open)}
            >
              <summary>{t('integrationsPage.advanced')}</summary>
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="slack-command">{t('integrationsPage.command')}</label>
                  <input id="slack-command" value={command} onChange={e => setCommand(e.target.value)} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="slack-channel-id">{t('integrationsPage.channelId')}</label>
                  <input id="slack-channel-id" value={commandChannelId} onChange={e => setCommandChannelId(e.target.value)} />
                </div>
                <div className="form-group">
                  <label htmlFor="slack-response-url">{t('integrationsPage.responseUrl')}</label>
                  <input id="slack-response-url" value={commandResponseUrl} onChange={e => setCommandResponseUrl(e.target.value)} />
                </div>
              </div>
            </details>
          </>
        ) : (
          <>
            <div className="form-group">
              <div className="integration-tool-form__field-heading">
                <label htmlFor="slack-event-payload">{t('integrationsPage.eventPayload')}</label>
                <HelpHint
                  label={t('integrationsPage.eventPayloadHelp')}
                  title={t('integrationsPage.eventPayloadHelpTitle')}
                />
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => applyPreset(mode)}>
                  {t('integrationsPage.applyPreset')}
                </button>
              </div>
              <textarea id="slack-event-payload" rows={8} value={eventPayloadRaw} onChange={e => setEventPayloadRaw(e.target.value)} />
            </div>
            <details
              className="integration-tool-form__advanced"
              open={advancedOpen}
              onToggle={(e) => setAdvancedOpen((e.target as HTMLDetailsElement).open)}
            >
              <summary>{t('integrationsPage.advanced')}</summary>
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="slack-retry-num">{t('integrationsPage.retryNum')}</label>
                  <input id="slack-retry-num" value={eventRetryNum} onChange={e => setEventRetryNum(e.target.value)} />
                </div>
                <div className="form-group">
                  <label htmlFor="slack-retry-reason">{t('integrationsPage.retryReason')}</label>
                  <input id="slack-retry-reason" value={eventRetryReason} onChange={e => setEventRetryReason(e.target.value)} />
                </div>
              </div>
            </details>
          </>
        )}
        <div className="integration-tool-form__submit">
          <OperationButton
            type="submit"
            isOperating={mode === 'command' ? sendingCommand : sendingEvent}
            disabled={manualActionBlocked}
            disabledReason={manualActionBlocked ? t('integrationsPage.toolReadiness.blockedAction') : undefined}
          >
            {mode === 'command' ? t('integrationsPage.sendCommand') : t('integrationsPage.sendEvent')}
          </OperationButton>
          <span>{t('integrationsPage.toolForm.submitHint')}</span>
        </div>

        <details className="integration-technical-details">
          <summary>{t('integrationsPage.slackTechnicalDetails')}</summary>
          <div className="integration-technical-details__body">
            <div className="integration-technical-details__links">
              <ReleaseWorkflowBacklink stepId="integrations" />
              <Link className="btn btn-secondary btn-sm" to={RELEASE_SLACK_GATEWAY_PATH}>
                {t('integrationsPage.releaseSmoke.workflowSlack')}
              </Link>
            </div>
            <div className="integration-technical-details__section">
              <div className="detail-section-header">
                <strong>{t('integrationsPage.slackSmokeHandoff.title')}</strong>
                <StatusBadge
                  status={activeProbe?.status ?? 'WARN'}
                  label={describeProbeStatus(t, activeProbe?.status ?? 'WARN')}
                />
              </div>
              <p className="detail-note">{t('integrationsPage.slackSmokeHandoff.description')}</p>
              <div className="detail-meta">
                <span>{t('integrationsPage.slackSmokeHandoff.env')}</span>
                <span>{t('integrationsPage.slackSmokeHandoff.evidence')}</span>
              </div>
            </div>
          </div>
        </details>
      </form>

      {activeResult ? <IntegrationTestResult result={activeResult} title={t('integrationsPage.lastResponse')} /> : null}
    </section>
  )
}

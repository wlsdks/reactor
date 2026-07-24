import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { HelpHint, OperationButton } from '../../../shared/ui'
import * as integrationsApi from '../api'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import type { HttpCallResult } from '../types'
import type { ControlPlaneProbeSnapshot } from '../controlPlaneProbes'
import { describeManifestStatus, describeProbeHttp, describeProbeReason } from './probeDescribers'
import { IntegrationTestResult } from './IntegrationTestResult'

// ── Helpers ────────────────────────────────────────────────────────────────

function safeMetadata(raw: string): Record<string, string> {
  if (!raw.trim()) return {}
  const parsed = JSON.parse(raw)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('metadata must be a JSON object')
  }
  const entries = Object.entries(parsed)
  return Object.fromEntries(entries.map(([key, value]) => [key, String(value)]))
}

function isManualProbeBlocked(probe: ControlPlaneProbeSnapshot | null): boolean {
  return probe != null && (probe.status === 'FAIL' || probe.reason === 'notAdvertised')
}

// ── Props ──────────────────────────────────────────────────────────────────

interface IntegrationsErrorReportTabProps {
  errorReportProbe: ControlPlaneProbeSnapshot | null
  error: string | null
  onError: (error: string | null) => void
}

// ── Component ──────────────────────────────────────────────────────────────

export function IntegrationsErrorReportTab({
  errorReportProbe,
  error,
  onError,
}: IntegrationsErrorReportTabProps) {
  const { t } = useTranslation()

  const [advancedOpen, setAdvancedOpen] = useState(false)

  const [errorApiKey, setErrorApiKey] = useState('')
  const [serviceName, setServiceName] = useState('reactor-admin')
  const [repoSlug, setRepoSlug] = useState('reactor/admin')
  const [slackChannel, setSlackChannel] = useState('C0123456789')
  const [environment, setEnvironment] = useState('production')
  const [stackTrace, setStackTrace] = useState('java.lang.IllegalStateException: sample\n\tat com.example.reactor.Sample.test(Sample.kt:12)')
  const [errorMetadataRaw, setErrorMetadataRaw] = useState('{"host":"admin-dev-01"}')
  const [sendingErrorReport, setSendingErrorReport] = useState(false)
  const [errorReportResult, setErrorReportResult] = useState<HttpCallResult | null>(null)

  const manualActionBlocked = isManualProbeBlocked(errorReportProbe)

  function applyPreset() {
    setStackTrace('java.lang.IllegalStateException: payment pipeline failed\n\tat com.example.reactor.PaymentService.run(PaymentService.kt:88)')
  }

  async function handleSendErrorReport(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    if (!stackTrace.trim() || !slackChannel.trim()) {
      onError(t('integrationsPage.errors.errorRequired'))
      return
    }

    setSendingErrorReport(true)
    onError(null)
    try {
      const result = await integrationsApi.sendErrorReport({
        stackTrace,
        serviceName,
        repoSlug,
        slackChannel,
        environment: environment || undefined,
        metadata: safeMetadata(errorMetadataRaw),
        apiKey: errorApiKey || undefined,
      })
      setErrorReportResult(result)
    } catch (e) {
      onError(getErrorMessage(e))
    } finally {
      setSendingErrorReport(false)
    }
  }

  return (
    <section className="integration-tool-workspace" aria-labelledby="integration-error-tool-title">
      {error && <div className="alert alert-error">{error}</div>}

      <header className="integration-tool-workspace__header">
        <div>
          <h2 id="integration-error-tool-title">{t('integrationsPage.testerTabError')}</h2>
          <p>{t('integrationsPage.modeDescription.error')}</p>
        </div>
      </header>

      {errorReportProbe && (
        <section className={`integration-tool-readiness integration-tool-readiness--${errorReportProbe.status.toLowerCase()}`} aria-label={t('integrationsPage.toolReadiness.label')}>
          <span className="integration-tool-readiness__dot" aria-hidden />
          <div>
            <div className="integration-tool-readiness__title-row">
              <strong>{t('integrationsPage.toolReadiness.label')}</strong>
              <HelpHint
                label={t('integrationsPage.toolReadiness.help')}
                title={t('integrationsPage.toolReadiness.label')}
              />
            </div>
            <p>{describeProbeReason(t, errorReportProbe)}</p>
          </div>
          <details className="integration-tool-readiness__technical">
            <summary>{t('integrationsPage.toolReadiness.technicalDetails')}</summary>
            <dl>
              <div>
                <dt>{t('integrationsPage.probeManifest')}</dt>
                <dd>{describeManifestStatus(t, errorReportProbe)}</dd>
              </div>
              <div>
                <dt>{t('integrationsPage.status')}</dt>
                <dd>{describeProbeHttp(t, errorReportProbe)}</dd>
              </div>
            </dl>
            {errorReportProbe.detail ? <p>{errorReportProbe.detail}</p> : null}
          </details>
        </section>
      )}

      <form className="integration-tool-form" onSubmit={(event) => void handleSendErrorReport(event)}>
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="error-slack-channel">{t('integrationsPage.slackChannel')}</label>
            <input id="error-slack-channel" value={slackChannel} onChange={e => setSlackChannel(e.target.value)} />
          </div>
          <div className="form-group">
            <label htmlFor="error-environment">{t('integrationsPage.environment')}</label>
            <input id="error-environment" value={environment} onChange={e => setEnvironment(e.target.value)} />
          </div>
        </div>
        <div className="form-group">
          <div className="integration-tool-form__field-heading">
            <label htmlFor="error-stack-trace">{t('integrationsPage.stackTrace')}</label>
            <button className="btn btn-secondary btn-sm" type="button" onClick={applyPreset}>
              {t('integrationsPage.applyPreset')}
            </button>
          </div>
          <textarea id="error-stack-trace" rows={6} value={stackTrace} onChange={e => setStackTrace(e.target.value)} />
        </div>
        <details
          className="integration-tool-form__advanced"
          open={advancedOpen}
          onToggle={(e) => setAdvancedOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary>{t('integrationsPage.advanced')}</summary>
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="error-service-name">{t('integrationsPage.serviceName')}</label>
              <input id="error-service-name" value={serviceName} onChange={e => setServiceName(e.target.value)} />
            </div>
            <div className="form-group">
              <label htmlFor="error-repo-slug">{t('integrationsPage.repoSlug')}</label>
              <input id="error-repo-slug" value={repoSlug} onChange={e => setRepoSlug(e.target.value)} />
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="error-metadata">{t('integrationsPage.metadataJson')}</label>
            <textarea id="error-metadata" rows={3} value={errorMetadataRaw} onChange={e => setErrorMetadataRaw(e.target.value)} />
          </div>
          <div className="form-group">
            <label htmlFor="error-api-key">{t('integrationsPage.apiKeyOptional')}</label>
            <input id="error-api-key" value={errorApiKey} onChange={e => setErrorApiKey(e.target.value)} />
          </div>
        </details>
        <div className="integration-tool-form__submit">
          <OperationButton
            type="submit"
            isOperating={sendingErrorReport}
            disabled={manualActionBlocked}
            disabledReason={manualActionBlocked ? t('integrationsPage.toolReadiness.blockedAction') : undefined}
          >
            {t('integrationsPage.sendError')}
          </OperationButton>
          <span>{t('integrationsPage.toolForm.submitHint')}</span>
        </div>
      </form>

      {errorReportResult ? <IntegrationTestResult result={errorReportResult} title={t('integrationsPage.lastResponse')} /> : null}
    </section>
  )
}

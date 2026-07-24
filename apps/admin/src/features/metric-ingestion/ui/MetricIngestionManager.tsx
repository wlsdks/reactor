import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { HelpHint, OperationButton, PageHeader } from '../../../shared/ui'
import { getErrorMessage, resolveApiError } from '../../../shared/lib/getErrorMessage'
import { ApiError, NetworkError } from '../../../shared/api/errors'
import * as api from '../api'
import type {
  EvalResultRequest,
  EvalRunResultsRequest,
  McpHealthRequest,
  ToolCallRequest,
} from '../types'
import './MetricIngestionManager.css'

type IngestionType = 'mcpHealth' | 'toolCall' | 'evalResult' | 'evalResults' | 'batch'

const INGESTION_TYPES: IngestionType[] = ['mcpHealth', 'toolCall', 'evalResult', 'evalResults', 'batch']
const SUMMARY_RESULT_FIELDS = new Set(['success', 'ingested', 'count', 'message'])

const ENDPOINTS: Record<IngestionType, string> = {
  mcpHealth: '/api/admin/metrics/ingest/mcp-health',
  toolCall: '/api/admin/metrics/ingest/tool-call',
  evalResult: '/api/admin/metrics/ingest/eval-result',
  evalResults: '/api/admin/metrics/ingest/eval-results',
  batch: '/api/admin/metrics/ingest/batch',
}

const DEFAULT_PAYLOADS: Record<IngestionType, string> = {
  mcpHealth: JSON.stringify({
    tenantId: 'default',
    serverName: 'mcp-main',
    status: 'CONNECTED',
    responseTimeMs: 120,
    toolCount: 8,
  }, null, 2),
  toolCall: JSON.stringify({
    tenantId: 'default',
    runId: 'run-123',
    toolName: 'jira_create_issue',
    success: true,
    durationMs: 230,
  }, null, 2),
  evalResult: JSON.stringify({
    tenantId: 'default',
    evalRunId: 'eval-001',
    testCaseId: 'tc-001',
    pass: true,
    score: 0.92,
    latencyMs: 830,
    tokenUsage: 1550,
    cost: 0.003,
    tags: ['smoke'],
  }, null, 2),
  evalResults: JSON.stringify({
    tenantId: 'default',
    evalRunId: 'eval-002',
    results: [
      { testCaseId: 'tc-101', pass: true, score: 0.88, latencyMs: 710, tokenUsage: 1200 },
      { testCaseId: 'tc-102', pass: false, score: 0.41, latencyMs: 990, tokenUsage: 1900, failureClass: 'ASSERT_FAIL' },
    ],
  }, null, 2),
  batch: JSON.stringify([
    { tenantId: 'default', serverName: 'mcp-main', status: 'CONNECTED', responseTimeMs: 100, toolCount: 10 },
    { tenantId: 'default', serverName: 'mcp-secondary', status: 'DISCONNECTED', responseTimeMs: 0, toolCount: 0 },
  ], null, 2),
}

function isIngestionType(value: string | null): value is IngestionType {
  return value != null && INGESTION_TYPES.some((type) => type === value)
}

function parseJsonObject<T>(raw: string): T {
  const parsed: unknown = JSON.parse(raw)
  if (parsed == null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('JSON_OBJECT_REQUIRED')
  }
  return parsed as T
}

function parseJsonArray<T>(raw: string): T[] {
  const parsed: unknown = JSON.parse(raw)
  if (!Array.isArray(parsed)) throw new Error('JSON_ARRAY_REQUIRED')
  return parsed as T[]
}

function formatResultValue(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

type PayloadInspection =
  | { valid: true; recordCount: number }
  | { valid: false; errorId: 'invalidJson' | 'jsonObjectRequired' | 'jsonArrayRequired' }

function inspectPayload(type: IngestionType, raw: string): PayloadInspection {
  try {
    const parsed: unknown = JSON.parse(raw)
    if (type === 'batch') {
      return Array.isArray(parsed)
        ? { valid: true, recordCount: parsed.length }
        : { valid: false, errorId: 'jsonArrayRequired' }
    }
    if (parsed == null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { valid: false, errorId: 'jsonObjectRequired' }
    }
    const recordCount = type === 'evalResults' && Array.isArray((parsed as { results?: unknown }).results)
      ? (parsed as { results: unknown[] }).results.length
      : 1
    return { valid: true, recordCount }
  } catch {
    return { valid: false, errorId: 'invalidJson' }
  }
}

export function MetricIngestionManager() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const typeParam = searchParams.get('type')
  const activeType: IngestionType = isIngestionType(typeParam) ? typeParam : 'mcpHealth'
  const [payloads, setPayloads] = useState(DEFAULT_PAYLOADS)
  const [loading, setLoading] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [technicalError, setTechnicalError] = useState<string | null>(null)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const resultEntries = result == null
    ? []
    : Object.entries(result).filter(([key]) => SUMMARY_RESULT_FIELDS.has(key))
  const payloadInspection = inspectPayload(activeType, payloads[activeType])

  function selectType(next: IngestionType) {
    const params = new URLSearchParams(searchParams)
    if (next === 'mcpHealth') params.delete('type')
    else params.set('type', next)
    setSearchParams(params, { replace: true })
    setError(null)
    setTechnicalError(null)
    setResult(null)
    setConfirmed(false)
  }

  function updatePayload(value: string) {
    setPayloads((current) => ({ ...current, [activeType]: value }))
    setError(null)
    setTechnicalError(null)
    setResult(null)
    setConfirmed(false)
  }

  function ingestionAction(): () => Promise<Record<string, unknown>> {
    const raw = payloads[activeType]
    switch (activeType) {
      case 'mcpHealth':
        return () => api.ingestMcpHealth(parseJsonObject<McpHealthRequest>(raw))
      case 'toolCall':
        return () => api.ingestToolCall(parseJsonObject<ToolCallRequest>(raw))
      case 'evalResult':
        return () => api.ingestEvalResult(parseJsonObject<EvalResultRequest>(raw))
      case 'evalResults':
        return () => api.ingestEvalResults(parseJsonObject<EvalRunResultsRequest>(raw))
      case 'batch':
        return () => api.ingestMcpHealthBatch(parseJsonArray<McpHealthRequest>(raw))
    }
  }

  async function submit() {
    if (!payloadInspection.valid || !confirmed) return
    setLoading(true)
    setError(null)
    setTechnicalError(null)
    setResult(null)
    try {
      setResult(await ingestionAction()())
      setConfirmed(false)
    } catch (caught) {
      const message = getErrorMessage(caught)
      if (message === 'JSON_OBJECT_REQUIRED') {
        setError(t('metricsIngestionPage.jsonObjectRequired'))
      } else if (message === 'JSON_ARRAY_REQUIRED') {
        setError(t('metricsIngestionPage.jsonArrayRequired'))
      }
      else {
        const resolved = resolveApiError(caught)
        const isMappedError = caught instanceof ApiError || caught instanceof NetworkError
        setError(
          isMappedError
            ? [resolved.message, resolved.hint].filter(Boolean).join(' ')
            : t('metricsIngestionPage.submitUnavailable'),
        )
        setTechnicalError(message)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page metric-ingestion-workspace">
      <PageHeader
        title={t('metricsIngestionPage.title')}
        description={t('metricsIngestionPage.description')}
      />

      <section className="metric-ingestion-workspace__notice" role="note">
        <strong>{t('metricsIngestionPage.warningTitle')}</strong>
        <p>{t('metricsIngestionPage.warning')}</p>
      </section>

      <section className="metric-ingestion-workspace__editor" aria-labelledby="metric-ingestion-editor-title">
        <div className="metric-ingestion-workspace__editor-header">
          <div>
            <h2 id="metric-ingestion-editor-title">{t('metricsIngestionPage.scenarioTitle')}</h2>
            <p>{t('metricsIngestionPage.chooseDescription')}</p>
          </div>
        </div>

        <div className="form-group metric-ingestion-workspace__type-field">
          <div className="metric-ingestion-workspace__label-row">
            <label htmlFor="metric-ingestion-type">{t('metricsIngestionPage.inputType')}</label>
            <HelpHint title={t('metricsIngestionPage.help.inputTypeTitle')} label={t('metricsIngestionPage.help.inputType')} />
          </div>
          <select
            id="metric-ingestion-type"
            value={activeType}
            onChange={(event) => selectType(event.target.value as IngestionType)}
          >
            {INGESTION_TYPES.map((type) => (
              <option key={type} value={type}>{t(`metricsIngestionPage.tabs.${type}`)}</option>
            ))}
          </select>
        </div>

        <div className="metric-ingestion-workspace__payload-section">
          <div className="metric-ingestion-workspace__payload-heading">
            <div>
              <h2>{t(`metricsIngestionPage.tabs.${activeType}`)}</h2>
              <p>{t(`metricsIngestionPage.typeDescriptions.${activeType}`)}</p>
            </div>
            <OperationButton variant="secondary" onClick={() => updatePayload(DEFAULT_PAYLOADS[activeType])}>
              {t('metricsIngestionPage.resetSample')}
            </OperationButton>
          </div>

          <div className="form-group metric-ingestion-workspace__payload">
            <div className="metric-ingestion-workspace__label-row">
              <label htmlFor="metric-ingestion-payload">{t('metricsIngestionPage.payload')}</label>
              <HelpHint title={t('metricsIngestionPage.help.jsonTitle')} label={t('metricsIngestionPage.help.json')} />
            </div>
            <textarea
              id="metric-ingestion-payload"
              rows={10}
              value={payloads[activeType]}
              onChange={(event) => updatePayload(event.target.value)}
              spellCheck={false}
              aria-invalid={!payloadInspection.valid}
              aria-describedby="metric-ingestion-payload-status"
            />
            <div
              id="metric-ingestion-payload-status"
              className={`metric-ingestion-workspace__payload-status${payloadInspection.valid ? '' : ' metric-ingestion-workspace__payload-status--invalid'}`}
              role={payloadInspection.valid ? 'status' : 'alert'}
            >
              {payloadInspection.valid
                ? t('metricsIngestionPage.payloadReady', { count: payloadInspection.recordCount })
                : t(`metricsIngestionPage.${payloadInspection.errorId}`)}
            </div>
          </div>

          <details className="metric-ingestion-workspace__technical">
            <summary>{t('metricsIngestionPage.technicalDetails')}</summary>
            <dl>
              <div>
                <dt>{t('metricsIngestionPage.targetEndpoint')}</dt>
                <dd><code>{ENDPOINTS[activeType]}</code></dd>
              </div>
              <div>
                <dt>{t('metricsIngestionPage.permission')}</dt>
                <dd>{t('metricsIngestionPage.permissionNotice')}</dd>
              </div>
            </dl>
          </details>
        </div>

        <div className="metric-ingestion-workspace__submit">
          <label className="metric-ingestion-workspace__confirmation">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            <span>{t('metricsIngestionPage.confirmSample')}</span>
          </label>
          <OperationButton onClick={() => void submit()} disabled={!payloadInspection.valid || !confirmed} isOperating={loading}>
            {t('metricsIngestionPage.submit')}
          </OperationButton>
          <span>{t('metricsIngestionPage.submitDescription')}</span>
        </div>
      </section>

      {(error != null || result != null) && (
        <section className="metric-ingestion-workspace__response" aria-live="polite">
          <h2>{error ? t('metricsIngestionPage.failedResponse') : t('metricsIngestionPage.lastResponse')}</h2>
          {error ? (
            <>
              <p role="alert">{error}</p>
              <div className="detail-actions metric-ingestion-workspace__response-actions">
                <OperationButton variant="secondary" onClick={() => void submit()} disabled={!payloadInspection.valid || !confirmed}>
                  {t('common.retry')}
                </OperationButton>
              </div>
              {technicalError ? (
                <details className="metric-ingestion-workspace__technical">
                  <summary>{t('metricsIngestionPage.technicalError')}</summary>
                  <p className="metric-ingestion-workspace__technical-error">{technicalError}</p>
                </details>
              ) : null}
            </>
          ) : (
            <>
              <p className="metric-ingestion-workspace__success">{t('metricsIngestionPage.successDescription')}</p>
              {resultEntries.length > 0 ? (
                <dl className="metric-ingestion-workspace__result-summary">
                  {resultEntries.slice(0, 4).map(([key, value]) => (
                    <div key={key}>
                      <dt>{t(`metricsIngestionPage.resultFields.${key}`)}</dt>
                      <dd>{formatResultValue(value)}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              <details className="metric-ingestion-workspace__technical">
                <summary>{t('metricsIngestionPage.rawResponse')}</summary>
                <pre className="code-block">{JSON.stringify(result, null, 2)}</pre>
              </details>
            </>
          )}
        </section>
      )}
    </div>
  )
}

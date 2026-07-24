import { useTranslation } from 'react-i18next'
import type { TraceSpan } from '../types'
import { strFromRecord, numFromRecord, formatCurrency, formatDuration, formatPercent } from '../../../shared/lib/formatters'
import {
  deriveSpanKind,
  localizeGuardAction,
  localizeGuardRule,
  localizeModelName,
  localizeServerName,
  localizeSpanError,
  localizeSpanKind,
  localizeStopReason,
  localizeToolName,
} from './spanLabels'

interface SpanDetailProps {
  span: TraceSpan
}

function ToolCallDetail({ attributes }: { attributes: Record<string, unknown> }) {
  const { t } = useTranslation()
  const toolName = strFromRecord(attributes, 'toolName')
  const mcpServer = strFromRecord(attributes, 'mcpServer')
  return (
    <div className="span-detail-content">
      <div className="span-detail-field">
        <span className="span-detail-label">{t('tracesPage.spanDetail.toolName')}</span>
        <span className="span-detail-value">{localizeToolName(t, toolName)}</span>
      </div>
      <div className="span-detail-field">
        <span className="span-detail-label">{t('tracesPage.spanDetail.mcpServer')}</span>
        <span className="span-detail-value">{localizeServerName(t, mcpServer)}</span>
      </div>
    </div>
  )
}

function LlmCallDetail({ attributes }: { attributes: Record<string, unknown> }) {
  const { t } = useTranslation()
  const model = strFromRecord(attributes, 'model')
  const inputTokens = numFromRecord(attributes, 'inputTokens')
  const outputTokens = numFromRecord(attributes, 'outputTokens')
  const costUsd = numFromRecord(attributes, 'costUsd')
  const stopReason = strFromRecord(attributes, 'stopReason')

  return (
    <div className="span-detail-content">
      <div className="span-detail-field">
        <span className="span-detail-label">{t('tracesPage.spanDetail.model')}</span>
        <span className="span-detail-value">{localizeModelName(t, model)}</span>
      </div>
      <div className="span-detail-field">
        <span className="span-detail-label">{t('tracesPage.spanDetail.tokens')}</span>
        <span className="span-detail-value mono">{inputTokens} / {outputTokens}</span>
      </div>
      <div className="span-detail-field">
        <span className="span-detail-label">{t('tracesPage.spanDetail.cost')}</span>
        <span className="span-detail-value mono">{formatCurrency(costUsd, { minDecimals: 4 })}</span>
      </div>
      <div className="span-detail-field">
        <span className="span-detail-label">{t('tracesPage.spanDetail.stopReason')}</span>
        <span className="span-detail-value">{localizeStopReason(t, stopReason)}</span>
      </div>
    </div>
  )
}

function GuardDetail({ attributes }: { attributes: Record<string, unknown> }) {
  const { t } = useTranslation()
  const action = strFromRecord(attributes, 'action')
  const matchedRule = strFromRecord(attributes, 'matchedRule')
  const confidence = numFromRecord(attributes, 'confidence')

  return (
    <div className="span-detail-content">
      <div className="span-detail-field">
        <span className="span-detail-label">{t('tracesPage.spanDetail.action')}</span>
        <span className="span-detail-value">{localizeGuardAction(t, action)}</span>
      </div>
      <div className="span-detail-field">
        <span className="span-detail-label">{t('tracesPage.spanDetail.matchedRule')}</span>
        <span className="span-detail-value">{localizeGuardRule(t, matchedRule)}</span>
      </div>
      <div className="span-detail-field">
        <span className="span-detail-label">{t('tracesPage.spanDetail.confidence')}</span>
        <span className="span-detail-value">{formatPercent(confidence)}</span>
      </div>
    </div>
  )
}

function TechnicalDetails({ span }: { span: TraceSpan }) {
  const { t } = useTranslation()
  const technicalRecord = {
    operationName: span.operationName,
    serviceName: span.serviceName,
    errorClass: span.errorClass,
    attributes: span.attributes,
  }

  return (
    <details className="span-technical-detail">
      <summary>{t('tracesPage.spanDetail.technicalDetails')}</summary>
      <pre className="span-detail-json">{JSON.stringify(technicalRecord, null, 2)}</pre>
    </details>
  )
}

export function SpanDetail({ span }: SpanDetailProps) {
  const { t } = useTranslation()
  const spanKind = deriveSpanKind(span.operationName)
  const attributeError = strFromRecord(span.attributes, 'error', '')
  const errorMessage = !span.success || span.errorClass || attributeError
    ? localizeSpanError(t, span.errorClass ?? attributeError)
    : null

  return (
    <div className="span-detail" data-testid="span-detail">
      <h4 className="span-detail-title">
        {localizeSpanKind(t, spanKind)}
      </h4>
      <div className="span-detail-meta">
        <span className={`span-detail-outcome is-${span.success ? 'success' : 'error'}`}>
          <span className="span-detail-outcome__dot" aria-hidden="true" />
          {t(span.success ? 'tracesPage.spanDetail.outcomeSuccess' : 'tracesPage.spanDetail.outcomeError')}
        </span>
        <span className="span-detail-duration">{formatDuration(span.durationMs)}</span>
      </div>

      {spanKind === 'tool_call' && <ToolCallDetail attributes={span.attributes} />}
      {spanKind === 'llm_call' && <LlmCallDetail attributes={span.attributes} />}
      {(spanKind === 'input_guard' || spanKind === 'output_guard') && (
        <GuardDetail attributes={span.attributes} />
      )}

      {errorMessage && (
        <div className="span-detail-content">
          <div className="span-detail-field">
            <span className="span-detail-label">{t('tracesPage.spanDetail.error')}</span>
            <span className="span-detail-value span-detail-error">{errorMessage}</span>
          </div>
        </div>
      )}

      <TechnicalDetails span={span} />
    </div>
  )
}

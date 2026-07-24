import { useTranslation } from 'react-i18next'
import { ChevronRight } from 'lucide-react'
import { HelpHint } from '../../../shared/ui'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import type { ChatResponse, ChatResponseMetadata } from '../types'
import { calculateCost, formatUsd, type ModelPrice } from '../cost'
import { ErrorDisplay } from './ErrorDisplay'
import { StatusBar } from './StatusBar'
import { formatModelName } from '../modelName'

interface ResponseDetailPanelProps {
  result: ChatResponse
  metadata: ChatResponseMetadata | null
  activeModelPrice: ModelPrice | null
  requestJson: string
  requestCollapsedByDefault: boolean
  rawResponseJson: string
  rawResponseCollapsedByDefault: boolean
}

function humanizeMetadataKey(key: string): string {
  const words = key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .trim()
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : key
}

function displayText(value: string | null | undefined): string {
  const normalized = value?.trim()
  if (!normalized) return '-'
  return normalized
}

function displayMetadataValue(value: unknown): string {
  if (value == null) return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value)
  }
  return '-'
}

/**
 * Renders the post-run response detail card: status bar + tokens + cost,
 * extended token breakdown (Gemini-aware fields), tools used, error display
 * (when unsuccessful), content body, trust details, and collapsible
 * request / response payload viewers.
 */
export function ResponseDetailPanel({
  result,
  metadata,
  activeModelPrice,
  requestJson,
  requestCollapsedByDefault,
  rawResponseJson,
  rawResponseCollapsedByDefault,
}: ResponseDetailPanelProps) {
  const { t } = useTranslation()

  const verifiedSources = metadata?.verifiedSources ?? []
  const toolSignals = metadata?.toolSignals ?? []
  const blockReason = typeof metadata?.blockReason === 'string' && metadata.blockReason.trim()
    ? metadata.blockReason
    : displayText(metadata?.outputGuard?.reason)
  const answerMode = typeof metadata?.answerMode === 'string' && metadata.answerMode.trim()
    ? metadata.answerMode
    : '-'
  const isGrounded = typeof metadata?.grounded === 'boolean' ? metadata.grounded : null
  const grounded = isGrounded != null
    ? (isGrounded ? t('common.yes') : t('common.no'))
    : '-'

  const totalTokens = metadata?.tokenUsage?.totalTokens ?? null
  const toolsUsed = result.toolsUsed ?? []

  return (
    <section className="chat-inspector-response">
      <h2 className="section-title">{t('chatInspector.response')}</h2>
      <StatusBar
        success={result.success}
        durationMs={result.durationMs}
        totalTokens={totalTokens}
      />

      <div className="chat-inspector-response__summary">
        <span>{t('chatInspector.responseSummary.modelApplied')}</span>
        <span>
          {toolsUsed.length > 0
            ? t('chatInspector.responseSummary.toolsUsed', { count: toolsUsed.length })
            : t('chatInspector.responseSummary.noToolsUsed')}
        </span>
        <span data-testid="chat-inspector-cost-indicator">
          {t('chatInspectorPage.cost.estimatedCostLabel')}
          <HelpHint title={t('chatInspector.help.tokenTitle')} label={t('chatInspector.help.token')} />
          :{' '}
          {totalTokens != null ? new Intl.NumberFormat().format(totalTokens) : '0'}
          {' · '}
          {activeModelPrice && totalTokens != null
            ? formatUsd(
                calculateCost(
                  {
                    inputTokens: metadata?.tokenUsage?.promptTokens ?? 0,
                    outputTokens: metadata?.tokenUsage?.completionTokens ?? 0,
                  },
                  activeModelPrice,
                ),
              )
            : '—'}
          {' USD'}
        </span>
      </div>

      {!result.success && (
        <ErrorDisplay
          errorCode={result.errorCode}
          errorMessage={result.errorMessage}
        />
      )}

      <div className="detail-section">
        <h3>{t('chatInspector.content')}</h3>
        <div className="chat-inspector-response__content" data-testid="chat-inspector-response-content">
          {displayText(result.content)}
        </div>
      </div>

      <section className="chat-inspector-response__evidence" aria-labelledby="chat-inspector-evidence-title">
        <h3 id="chat-inspector-evidence-title">{t('chatInspector.evidenceDetails')}</h3>
        <dl className="chat-inspector-response__definitions">
          <div>
            <dt>{t('chatInspector.grounded')}</dt>
            <dd>{grounded}</dd>
          </div>
          <div>
            <dt>{t('chatInspector.verifiedSources')}</dt>
            <dd>
              {verifiedSources.length > 0 ? (
                <ul className="chat-inspector-response__sources">
                  {verifiedSources.map((source) => (
                    <li key={`${source.url}-${source.title}`}>
                      <a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>
                    </li>
                  ))}
                </ul>
              ) : t('chatInspector.noVerifiedSources')}
            </dd>
          </div>
        </dl>
      </section>

      <details className="chat-inspector-response__technical-details">
        <summary className="chat-inspector-response__technical-summary">
          <ChevronRight className="chat-inspector-response__technical-chevron" aria-hidden="true" />
          <span>{t('chatInspector.technicalDetails')}</span>
        </summary>
        <div className="chat-inspector-response__technical-content">
          <dl className="chat-inspector-response__definitions">
            <div><dt>{t('chatInspector.model')}</dt><dd>{displayText(formatModelName(result.model))}</dd></div>
            <div><dt>{t('chatInspector.toolsUsed')}</dt><dd>{toolsUsed.length > 0 ? toolsUsed.join(', ') : '-'}</dd></div>
            <div><dt>{t('chatInspector.answerMode')}</dt><dd>{answerMode}</dd></div>
            <div><dt>{t('chatInspector.blockReason')}</dt><dd>{blockReason}</dd></div>
          </dl>

          {result.metadata?.tokenUsage && (
            <section className="chat-inspector-response__technical-section">
              <h3>{t('chatInspector.tokens.title')}</h3>
              <dl className="chat-inspector-response__definitions">
                <div><dt>{t('chatInspector.tokens.input')}</dt><dd>{new Intl.NumberFormat().format(result.metadata.tokenUsage.promptTokens)}</dd></div>
                <div><dt>{t('chatInspector.tokens.output')}</dt><dd>{new Intl.NumberFormat().format(result.metadata.tokenUsage.completionTokens)}</dd></div>
                {result.metadata.tokenUsage.thoughtsTokens != null && (
                  <div><dt>{t('chatInspector.tokens.reasoning')}</dt><dd>{new Intl.NumberFormat().format(result.metadata.tokenUsage.thoughtsTokens)}</dd></div>
                )}
                {result.metadata.tokenUsage.cachedContentTokens != null && (
                  <div><dt>{t('chatInspector.tokens.cached')}</dt><dd>{new Intl.NumberFormat().format(result.metadata.tokenUsage.cachedContentTokens)}</dd></div>
                )}
                {result.metadata.tokenUsage.toolUsePromptTokens != null && (
                  <div><dt>{t('chatInspector.tokens.toolContext')}</dt><dd>{new Intl.NumberFormat().format(result.metadata.tokenUsage.toolUsePromptTokens)}</dd></div>
                )}
                {result.metadata.tokenUsage.trafficType && (
                  <div><dt>{t('chatInspector.tokens.capacity')}</dt><dd>{result.metadata.tokenUsage.trafficType}</dd></div>
                )}
              </dl>
            </section>
          )}

        {metadata?.freshness && (
          <section className="chat-inspector-response__technical-section">
            <h3>{t('chatInspector.freshness')}</h3>
            <dl className="chat-inspector-response__definitions">
              {Object.entries(metadata.freshness).map(([key, value]) => (
                <div key={key}>
                  <dt>{t(`chatInspector.metadataLabels.${key}`, { defaultValue: humanizeMetadataKey(key) })}</dt>
                  <dd>{displayMetadataValue(value)}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}
        {metadata?.outputGuard && (
          <section className="chat-inspector-response__technical-section">
            <h3>{t('chatInspector.outputGuard')}</h3>
            <dl className="chat-inspector-response__definitions">
              <div><dt>{t('chatInspector.guard.action')}</dt><dd>{metadata.outputGuard.action}</dd></div>
              {metadata.outputGuard.stage && <div><dt>{t('chatInspector.guard.stage')}</dt><dd>{metadata.outputGuard.stage}</dd></div>}
              {metadata.outputGuard.reason && <div><dt>{t('chatInspector.guard.reason')}</dt><dd>{metadata.outputGuard.reason}</dd></div>}
            </dl>
          </section>
        )}
        {toolSignals.length > 0 && (
          <section className="chat-inspector-response__technical-section">
            <h3>{t('chatInspector.toolSignals')}</h3>
            <ul className="chat-inspector-response__signals">
              {toolSignals.map((signal) => (
                <li key={`${signal.toolName}-${signal.retrievedAt ?? ''}`}>
                  <strong>{signal.toolName}</strong>
                  <span>{t('chatInspector.grounded')}: {signal.grounded == null ? '-' : signal.grounded ? t('common.yes') : t('common.no')}</span>
                  {signal.answerMode && <span>{t('chatInspector.answerMode')}: {signal.answerMode}</span>}
                  {signal.retrievedAt && <span>{t('chatInspector.retrievedAt')}: {signal.retrievedAt}</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

          <details
            className="stream-event__details"
            open={!requestCollapsedByDefault}
            data-testid="chat-inspector-request-payload"
          >
            <summary className="stream-event__summary">
              <span className="stream-event__summary-closed">
                {t('chatInspectorPage.cost.payloadCollapsed')}
              </span>
              <span className="stream-event__summary-open">
                {t('chatInspectorPage.cost.payloadExpanded')}
              </span>
              <span className="stream-event__summary-size">
                {t('chatInspector.requestData')} · {formatLocaleNumber(requestJson.length)} B
              </span>
            </summary>
            <pre className="stream-event__payload">{requestJson}</pre>
          </details>

          <details
            className="stream-event__details"
            open={!rawResponseCollapsedByDefault}
            data-testid="chat-inspector-response-payload"
          >
            <summary className="stream-event__summary">
              <span className="stream-event__summary-closed">
                {t('chatInspectorPage.cost.payloadCollapsed')}
              </span>
              <span className="stream-event__summary-open">
                {t('chatInspectorPage.cost.payloadExpanded')}
              </span>
              <span className="stream-event__summary-size">
                {t('chatInspector.responseData')} · {formatLocaleNumber(rawResponseJson.length)} B
              </span>
            </summary>
            <pre className="stream-event__payload">{rawResponseJson}</pre>
          </details>
        </div>
      </details>
    </section>
  )
}

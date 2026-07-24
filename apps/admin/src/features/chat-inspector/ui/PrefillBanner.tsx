import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import type { ChatInspectorPrefill } from '../prefill'

interface PrefillBannerProps {
  prefill: ChatInspectorPrefill
}

function getEventTypeLabel(value: string | null | undefined, t: TFunction): string {
  switch (value) {
    case 'unverified_response':
      return t('chatInspector.prefill.eventTypeValues.unverifiedResponse')
    case 'guard_blocked':
      return t('chatInspector.prefill.eventTypeValues.guardBlocked')
    case 'tool_error':
      return t('chatInspector.prefill.eventTypeValues.toolError')
    default:
      return t('chatInspector.prefill.eventTypeValues.review')
  }
}

function getSeverityLabel(value: string | null | undefined, t: TFunction): string {
  switch (value) {
    case 'ERROR':
      return t('chatInspector.prefill.severityValues.error')
    case 'WARN':
      return t('chatInspector.prefill.severityValues.warning')
    case 'INFO':
      return t('chatInspector.prefill.severityValues.info')
    default:
      return t('chatInspector.prefill.severityValues.review')
  }
}

/**
 * Banner shown at the top of the inspector when the user navigated in via a
 * deep-link (e.g. an alert detail "Investigate in Inspector" button). Surfaces
 * the originating event metadata and provides a "clear" link to drop the
 * prefill state.
 */
export function PrefillBanner({ prefill }: PrefillBannerProps) {
  const { t } = useTranslation()

  return (
    <section className="chat-inspector-prefill">
      <div className="chat-inspector-prefill__heading">
        <h2>{t('chatInspector.prefill.title')}</h2>
        <Link className="btn btn-secondary" to="/chat-inspector">
          {t('chatInspector.prefill.clear')}
        </Link>
      </div>
      <p className="detail-note">{t('chatInspector.prefill.description')}</p>
      <dl className="chat-inspector-prefill__facts">
        <div>
          <dt>{t('chatInspector.prefill.eventType')}</dt>
          <dd>{getEventTypeLabel(prefill.eventType, t)}</dd>
        </div>
        <div>
          <dt>{t('chatInspector.prefill.severity')}</dt>
          <dd>{getSeverityLabel(prefill.severity, t)}</dd>
        </div>
      </dl>
      {(prefill.queryLabel || prefill.model || prefill.tools) ? (
        <details className="chat-inspector-prefill__technical">
          <summary>{t('chatInspector.technicalDetails')}</summary>
          <dl className="chat-inspector-response__definitions">
            {prefill.queryLabel ? <div><dt>{t('chatInspector.prefill.signal')}</dt><dd>{prefill.queryLabel}</dd></div> : null}
            {prefill.model ? <div><dt>{t('chatInspector.model')}</dt><dd>{prefill.model}</dd></div> : null}
            {prefill.tools ? <div><dt>{t('chatInspector.toolsUsed')}</dt><dd>{prefill.tools}</dd></div> : null}
          </dl>
        </details>
      ) : null}
    </section>
  )
}

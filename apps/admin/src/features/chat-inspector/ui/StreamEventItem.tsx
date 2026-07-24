import { useTranslation } from 'react-i18next'
import { ChevronRight } from 'lucide-react'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import type { StreamEventType } from '../types'
import { shouldCollapsePayload } from '../cost'
import './StreamEventItem.css'

interface StreamEventItemProps {
  event: string
  data: string
}

const EVENT_LABEL_KEY: Record<StreamEventType, string> = {
  message: 'chatInspector.streamEventTypes.message',
  tool_start: 'chatInspector.streamEventTypes.toolStart',
  tool_end: 'chatInspector.streamEventTypes.toolEnd',
  error: 'chatInspector.streamEventTypes.error',
  done: 'chatInspector.streamEventTypes.done',
}

const KNOWN_TYPES = new Set<string>(['message', 'tool_start', 'tool_end', 'error', 'done'])

/** Attempt to pretty-print a JSON payload; fall back to the raw string. */
function prettyPrint(data: string): string {
  if (!data) return ''
  const trimmed = data.trim()
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return data
  try {
    const parsed: unknown = JSON.parse(trimmed)
    return JSON.stringify(parsed, null, 2)
  } catch {
    return data
  }
}

export function StreamEventItem({ event, data }: StreamEventItemProps) {
  const { t } = useTranslation()
  const isKnown = KNOWN_TYPES.has(event)
  const label = isKnown
    ? t(EVENT_LABEL_KEY[event as StreamEventType])
    : t('chatInspector.streamEventTypes.unknown')
  const indicatorClass = isKnown ? event : 'unknown'

  const pretty = prettyPrint(data)
  const hasPayload = data.length > 0
  const collapsedByDefault = shouldCollapsePayload(data)
  // When the payload is small, render inline. When large, gate it behind
  // a <details> element so the events list stays compact by default.

  return (
    <div className={`stream-event ${isKnown ? `stream-event--${event}` : ''}`}>
      <span className={`stream-event__indicator stream-event__indicator--${indicatorClass}`} aria-hidden="true" />
      <span className="stream-event__label">{label}</span>
      {hasPayload && !collapsedByDefault && (
        <span className={`stream-event__data ${event === 'error' ? 'stream-event__data--error' : ''}`}>
          {data}
        </span>
      )}
      {hasPayload && collapsedByDefault && (
        <details className="stream-event__details">
          <summary className="stream-event__summary">
            <ChevronRight className="stream-event__chevron" aria-hidden="true" />
            <span className="stream-event__summary-closed">{t('chatInspectorPage.cost.payloadCollapsed')}</span>
            <span className="stream-event__summary-open">{t('chatInspectorPage.cost.payloadExpanded')}</span>
            <span className="stream-event__summary-size">{formatLocaleNumber(data.length)} B</span>
          </summary>
          <pre className="stream-event__payload">{pretty}</pre>
        </details>
      )}
    </div>
  )
}

import { useTranslation } from 'react-i18next'
import { ChevronRight } from 'lucide-react'
import type { StreamEvent } from '../types'
import { StreamEventItem } from './StreamEventItem'

interface StreamOutputPanelProps {
  streamMessage: string
  streamEvents: StreamEvent[]
}

const VISIBLE_EVENT_COUNT = 20

/**
 * Renders the streaming-mode output: the concatenated streamed message body
 * and a closed technical event record. The first visible events stay bounded
 * while the remainder is available on demand.
 */
export function StreamOutputPanel({ streamMessage, streamEvents }: StreamOutputPanelProps) {
  const { t } = useTranslation()

  return (
    <section className="chat-inspector-stream-output">
      <h2 className="section-title">{t('chatInspector.streamedMessage')}</h2>
      {streamMessage ? (
        <div className="chat-inspector-response__content">{streamMessage}</div>
      ) : (
        <p className="chat-inspector-stream-output__empty">{t('chatInspector.noStreamOutput')}</p>
      )}

      {streamEvents.length > 0 ? (
        <details className="chat-inspector-response__technical-details chat-inspector-stream-output__events">
          <summary className="chat-inspector-response__technical-summary">
            <ChevronRight className="chat-inspector-response__technical-chevron" aria-hidden="true" />
            <span>{t('chatInspector.streamEvents', { count: streamEvents.length })}</span>
          </summary>
          <div className="chat-inspector-response__technical-content">
            {streamEvents.slice(0, VISIBLE_EVENT_COUNT).map((evt, i) => (
              <StreamEventItem key={i} event={evt.event} data={evt.data} />
            ))}
            {streamEvents.length > VISIBLE_EVENT_COUNT && (
              <details className="chat-inspector-stream-output__more-events">
                <summary className="chat-inspector-response__technical-summary">
                  <ChevronRight className="chat-inspector-response__technical-chevron" aria-hidden="true" />
                  <span>{t('chatInspector.additionalEvents', { count: streamEvents.length - VISIBLE_EVENT_COUNT })}</span>
                </summary>
                {streamEvents.slice(VISIBLE_EVENT_COUNT).map((evt, i) => (
                  <StreamEventItem key={i + VISIBLE_EVENT_COUNT} event={evt.event} data={evt.data} />
                ))}
              </details>
            )}
          </div>
        </details>
      ) : null}
    </section>
  )
}

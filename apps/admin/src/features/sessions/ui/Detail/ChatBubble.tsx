import { useTranslation } from 'react-i18next'
import type { ChatMessage } from '../../types'
import type { MessageCost } from '../../../token-cost/types'
import { TokenCostBadge } from '../../../token-cost/ui/TokenCostBadge'

interface ChatBubbleProps {
  message: ChatMessage
  cost?: MessageCost
  showCost?: boolean
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
}

export function ChatBubble({ message, cost, showCost = false }: ChatBubbleProps) {
  const { t } = useTranslation()
  const { role, content, timestamp, model, durationMs, grounded, blockReason } = message
  const isBlocked = Boolean(blockReason)

  const className = [
    'session-chat-bubble',
    `session-chat-bubble--${role}`,
    isBlocked ? 'session-chat-bubble--blocked' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={className}>
      <div className="session-chat-bubble-content">
        {isBlocked ? (
          <div className="session-chat-bubble-blocked">
            <span>{t('sessions.blocked')}</span>
            <span>{t('sessions.blockReason')}: {blockReason}</span>
          </div>
        ) : (
          <p>{content}</p>
        )}
      </div>
      <div className="session-chat-bubble-footer">
        <span className="session-chat-bubble-role">{role}</span>
        <span className="session-chat-bubble-time">{formatTime(timestamp)}</span>
      </div>
      {role === 'assistant' && !isBlocked && (
        <div className="session-chat-bubble-meta">
          {model && <span>{model}</span>}
          {durationMs !== undefined && <span>{(durationMs / 1000).toFixed(1)}s</span>}
          {grounded !== undefined && (
            <span>{grounded ? t('sessions.grounded') : t('sessions.ungrounded')}</span>
          )}
          <TokenCostBadge cost={cost} visible={showCost} />
        </div>
      )}
      {role === 'assistant' && isBlocked && (
        <div className="session-chat-bubble-meta">
          {model && <span>{model}</span>}
          {durationMs !== undefined && <span>{(durationMs / 1000).toFixed(1)}s</span>}
          <span>{t('sessions.blockedLabel')}</span>
        </div>
      )}
    </div>
  )
}

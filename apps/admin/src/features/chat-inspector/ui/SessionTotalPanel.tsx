import { useTranslation } from 'react-i18next'
import { formatUsd, type SessionTotals } from '../cost'

interface SessionTotalPanelProps {
  sessionTotals: SessionTotals
  hasPrice: boolean
  budgetExceeded: boolean
}

/**
 * Compact running-total panel shown above the response detail. Surfaces
 * cumulative tokens + estimated USD cost across the current inspector
 * session, and flags when either budget threshold has been exceeded.
 */
export function SessionTotalPanel({ sessionTotals, hasPrice, budgetExceeded }: SessionTotalPanelProps) {
  const { t } = useTranslation()

  return (
    <section
      className="chat-inspector-session-total"
      data-testid="chat-inspector-session-total"
      aria-live="polite"
    >
      <div>
        <h2>
          {t('chatInspectorPage.cost.sessionTotal')}
        </h2>
        <span className="chat-inspector-session-total__value">
          {new Intl.NumberFormat().format(sessionTotals.totalTokens)}
          {' · '}
          {hasPrice ? formatUsd(sessionTotals.estimatedCostUsd) : '—'}
          {' USD'}
        </span>
        {budgetExceeded && (
          <span
            className="chat-inspector-session-total__warning"
            role="status"
            data-testid="chat-inspector-budget-exceeded"
          >
            {t('chatInspectorPage.cost.budgetExceeded')}
          </span>
        )}
      </div>
    </section>
  )
}

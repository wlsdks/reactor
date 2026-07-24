import { useTranslation } from 'react-i18next'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import type { MessageCost } from '../types'

interface TokenCostBadgeProps {
  cost: MessageCost | undefined
  visible: boolean
}

function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return formatLocaleNumber(n)
}

function formatCostUsd(usd: number): string {
  if (usd < 0.001) return `$${usd.toFixed(6)}`
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(3)}`
}

export function TokenCostBadge({ cost, visible }: TokenCostBadgeProps) {
  const { t } = useTranslation()

  if (!visible || !cost) return null

  return (
    <span
      className="token-cost-badge"
      title={t('tokenCost.badgeTooltip', {
        input: formatLocaleNumber(cost.promptTokens),
        output: formatLocaleNumber(cost.completionTokens),
        model: cost.model,
      })}
      aria-label={t('tokenCost.badgeLabel', {
        tokens: formatLocaleNumber(cost.totalTokens),
        cost: formatCostUsd(cost.estimatedCostUsd),
      })}
    >
      <span className="token-cost-badge-tokens">{formatTokenCount(cost.totalTokens)}</span>
      <span className="token-cost-badge-separator">{' · '}</span>
      <span className="token-cost-badge-cost">{formatCostUsd(cost.estimatedCostUsd)}</span>
    </span>
  )
}

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatLocaleNumber } from '../lib/intl'
import { budgetSeverity } from './CostCard.utils'
import './CostCard.css'

interface CostTrend {
  /** Percentage delta vs prior period (e.g. +12.3 means up 12.3%). */
  delta: number
  /** Period label (e.g. "어제 대비"). */
  period: string
}

interface CostTokens {
  input: number
  output: number
}

interface CostBudget {
  used: number
  limit: number
}

export interface CostCardProps {
  /** Card label (e.g. "오늘 비용"). */
  label: string
  /** Cost value in USD. */
  value: number
  /** Optional trend chip — semantic color follows direction (down=success, up=error). */
  trend?: CostTrend
  /** Optional input/output token breakdown (rendered in tooltip). */
  tokens?: CostTokens
  /** Optional budget bar (color shifts with utilisation). */
  budget?: CostBudget
  /** Optional click handler — renders the card as a button. */
  onClick?: () => void
}

function formatUsd(amount: number): string {
  if (!Number.isFinite(amount) || amount <= 0) return '$0.00'
  if (amount < 1) return `$${amount.toFixed(4)}`
  if (amount < 100) return `$${amount.toFixed(2)}`
  return `$${amount.toFixed(0)}`
}

function formatDelta(delta: number): string {
  const sign = delta > 0 ? '+' : ''
  return `${sign}${delta.toFixed(1)}%`
}

function formatTokens(n: number): string {
  return formatLocaleNumber(n)
}

export function CostCard({
  label,
  value,
  trend,
  tokens,
  budget,
  onClick,
}: CostCardProps) {
  const { t } = useTranslation()
  const [tooltipOpen, setTooltipOpen] = useState(false)

  const budgetRatio = budget && budget.limit > 0
    ? Math.min(budget.used / budget.limit, 1)
    : 0
  const budgetPct = Math.round(budgetRatio * 100)
  const severity = budget ? budgetSeverity(budgetRatio) : null

  // Trend colour intent: a falling cost is good (success); rising cost is bad (error).
  const trendIntent: 'success' | 'error' | 'neutral' = trend
    ? trend.delta > 0
      ? 'error'
      : trend.delta < 0
        ? 'success'
        : 'neutral'
    : 'neutral'

  const tokenLabel = tokens
    ? t('costCard.tokenBreakdown', {
        input: formatTokens(tokens.input),
        output: formatTokens(tokens.output),
      })
    : null

  const content = (
    <>
      <div className="cost-card__label">{label}</div>

      <div
        className="cost-card__value-row"
        onMouseEnter={tokens ? () => setTooltipOpen(true) : undefined}
        onMouseLeave={tokens ? () => setTooltipOpen(false) : undefined}
        onFocus={tokens ? () => setTooltipOpen(true) : undefined}
        onBlur={tokens ? () => setTooltipOpen(false) : undefined}
      >
        <span className="cost-card__value" data-testid="cost-card-value">
          {formatUsd(value)}
        </span>
        {trend && (
          <span
            className={`cost-card__trend cost-card__trend--${trendIntent}`}
            data-testid="cost-card-trend"
            title={t('metrics.delta.tooltipPattern', {
              value: formatDelta(trend.delta),
              period: trend.period,
            })}
            aria-label={t('costCard.trendAria', {
              delta: formatDelta(trend.delta),
              period: trend.period,
            })}
          >
            <span className="cost-card__trend-delta">{formatDelta(trend.delta)}</span>
            <span className="cost-card__trend-period">{trend.period}</span>
          </span>
        )}
        {tokens && tooltipOpen && tokenLabel && (
          <span
            className="cost-card__tooltip"
            role="tooltip"
            data-testid="cost-card-tooltip"
          >
            {tokenLabel}
          </span>
        )}
      </div>

      {budget && severity && (
        <div className="cost-card__budget" data-testid="cost-card-budget">
          <div
            className={`cost-card__budget-bar cost-card__budget-bar--${severity}`}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={budgetPct}
            aria-label={t('costCard.budgetAria', {
              used: formatUsd(budget.used),
              limit: formatUsd(budget.limit),
              percent: budgetPct,
            })}
          >
            <div
              className={`cost-card__budget-fill cost-card__budget-fill--${severity}`}
              style={{ width: `${budgetPct}%` }}
              data-testid="cost-card-budget-fill"
              data-severity={severity}
            />
          </div>
          <div className="cost-card__budget-meta">
            <span className="cost-card__budget-text">
              {formatUsd(budget.used)} / {formatUsd(budget.limit)}
            </span>
            <span className="cost-card__budget-pct">{budgetPct}%</span>
          </div>
        </div>
      )}
    </>
  )

  if (onClick) {
    return (
      <button
        type="button"
        className="cost-card cost-card--clickable"
        onClick={onClick}
        aria-label={`${label} ${formatUsd(value)}`}
      >
        {content}
      </button>
    )
  }

  return <div className="cost-card">{content}</div>
}

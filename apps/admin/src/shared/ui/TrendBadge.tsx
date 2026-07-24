import { useTranslation } from 'react-i18next'

export interface TrendBadgeProps {
  /**
   * Numeric delta value rendered inside the chip. Positive values render with
   * a leading `+`. A value of `0` renders an em-dash (no direction).
   */
  value: number
  /**
   * When `true`, the colour intent is inverted: a falling value is "good"
   * (success) and a rising value is "bad" (error). Use this for KPIs where
   * an increase is undesirable (e.g. open issues, rejected requests).
   */
  inverse?: boolean
  /**
   * Human-readable baseline window used as the comparison reference (for
   * example "어제 대비", "지난 주 대비"). Surfaced as a native `title`
   * tooltip and as an accessible label for screen readers.
   */
  baselineLabel?: string
  /**
   * When `true`, render `baselineLabel` as a small dim caption below the
   * chip in addition to the tooltip. Default `false` (tooltip-only).
   */
  showCaption?: boolean
}

/**
 * Compact +/- delta chip used by KPI cards. Colour intent follows the
 * direction of `value` (configurable via `inverse`). When `baselineLabel`
 * is provided, the chip exposes the baseline window as a tooltip and ARIA
 * label so reviewers can see what "yesterday / last week / etc." means
 * without leaving the dashboard.
 */
export function TrendBadge({
  value,
  inverse = false,
  baselineLabel,
  showCaption = false,
}: TrendBadgeProps) {
  const { t } = useTranslation()

  const isFlat = value === 0
  // Higher = good unless inverted (e.g. issue counts: more issues is bad).
  const isPositive = inverse ? value < 0 : value > 0
  const className = isFlat
    ? 'trend-badge trend-flat'
    : `trend-badge ${isPositive ? 'trend-good' : 'trend-bad'}`

  const display = isFlat ? '—' : `${value > 0 ? '+' : ''}${value}`
  const tooltip = baselineLabel
    ? t('metrics.delta.tooltipPattern', { value: display, period: baselineLabel })
    : undefined

  // The chip itself stays a single token so existing CSS layouts (sparkline
  // rows, stat-group-top) keep their alignment. The optional caption is
  // surfaced inside a wrapper so callers that don't request one don't gain
  // an extra DOM node.
  const chip = (
    <span
      className={className}
      title={tooltip}
      aria-label={tooltip}
      data-testid="trend-badge"
    >
      {display}
    </span>
  )

  if (showCaption && baselineLabel) {
    return (
      <span className="trend-badge-wrapper">
        {chip}
        <span className="trend-badge-caption" data-testid="trend-badge-caption">
          {baselineLabel}
        </span>
      </span>
    )
  }

  return chip
}

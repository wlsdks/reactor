import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: ReactNode
  sub?: string
  icon?: ReactNode
  change?: number
  /**
   * Optional baseline window for the `change` percentage (e.g. "어제 대비").
   * Surfaced as a native `title` tooltip on the change chip; if
   * `showBaselineCaption` is true, also rendered as a small italic caption.
   */
  changeBaselineLabel?: string
  /**
   * When `true`, render the baseline label as a dim italic caption beneath
   * the change chip in addition to the tooltip. Default `false` (tooltip-only).
   */
  showBaselineCaption?: boolean
  /**
   * Visual emphasis for the value. `'default'` renders the value in
   * `--text-primary`; `'hero'` opts into the product selection accent and should
   * be reserved for the single most important KPI per page so the accent
   * retains its "highlight" semantic. See BX audit P0-6.
   */
  tone?: 'default' | 'hero'
  onClick?: () => void
}

function formatChange(change: number): { text: string; className: string } {
  if (change > 0) {
    return { text: `+${change}%`, className: 'stat-card-change stat-card-change--positive' }
  }
  if (change < 0) {
    return { text: `${change}%`, className: 'stat-card-change stat-card-change--negative' }
  }
  return { text: '0%', className: 'stat-card-change stat-card-change--zero' }
}

export function StatCard({
  label,
  value,
  sub,
  icon,
  change,
  changeBaselineLabel,
  showBaselineCaption = false,
  tone = 'default',
  onClick,
}: StatCardProps) {
  const changeStyle = change !== undefined ? formatChange(change) : null
  const valueClassName =
    tone === 'hero' ? 'stat-card-value stat-card-value--hero' : 'stat-card-value'
  const content = (
    <>
      {icon && <div className="stat-card-icon">{icon}</div>}
      <div className="stat-card-label">{label}</div>
      <div className={valueClassName}>{value}</div>
      {changeStyle && (
        <div
          className={changeStyle.className}
          title={changeBaselineLabel}
          aria-label={changeBaselineLabel ? `${changeStyle.text} ${changeBaselineLabel}` : undefined}
        >
          {changeStyle.text}
        </div>
      )}
      {showBaselineCaption && changeBaselineLabel && (
        <div className="stat-card-baseline" data-testid="stat-card-baseline">
          {changeBaselineLabel}
        </div>
      )}
      {sub && <div className="stat-card-sub">{sub}</div>}
    </>
  )

  if (onClick) {
    return (
      <button
        className="stat-card stat-card--clickable"
        onClick={onClick}
        aria-label={label}
      >
        {content}
      </button>
    )
  }

  return <div className="stat-card">{content}</div>
}

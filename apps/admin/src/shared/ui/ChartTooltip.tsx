import type { TooltipProps } from 'recharts'
import { formatNumber } from '../lib/formatters'

interface ChartTooltipProps extends TooltipProps<number, string> {
  formatValue?: (value: number) => string
}

export function ChartTooltip({ active, payload, label, formatValue }: ChartTooltipProps) {
  if (!active || !payload?.length) return null

  return (
    <div className="chart-tooltip">
      {label && <div className="chart-tooltip-label">{label}</div>}
      {payload.map((entry, i) => (
        <div key={i} className="chart-tooltip-row">
          <span
            className="chart-tooltip-dot"
            style={{ background: entry.color }}
          />
          <span className="chart-tooltip-name">{entry.name}</span>
          <span className="chart-tooltip-value">
            {formatValue ? formatValue(entry.value as number) : formatNumber(entry.value as number)}
          </span>
        </div>
      ))}
    </div>
  )
}

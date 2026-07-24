import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts'
import { ChartTooltip } from './ChartTooltip'
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  paletteColor,
} from './ChartConfig'
import { computeTickInterval } from '../lib/chart-ticks'

export interface PercentileDataPoint {
  timestamp: number
  [key: string]: number
}

interface DataKeyConfig {
  key: string
  name: string
  stroke: string
  strokeWidth?: number
  gradientId: string
  gradientColor: string
  gradientOpacity: number
}

// Default series order (P99 → P95 → P50) maps to palette indices
// 0 (blue), 1 (emerald), 2 (amber) — non-adjacent on the CB-safe scale so
// percentiles stay distinguishable for protanopic / deuteranopic readers.
const DEFAULT_DATA_KEYS: DataKeyConfig[] = [
  {
    key: 'p99',
    name: 'P99',
    stroke: paletteColor(0),
    strokeWidth: 1.5,
    gradientId: 'percentileP99Grad',
    gradientColor: paletteColor(0),
    gradientOpacity: 0.15,
  },
  {
    key: 'p95',
    name: 'P95',
    stroke: paletteColor(1),
    strokeWidth: 1.5,
    gradientId: 'percentileP95Grad',
    gradientColor: paletteColor(1),
    gradientOpacity: 0.2,
  },
  {
    key: 'p50',
    name: 'P50',
    stroke: paletteColor(2),
    strokeWidth: 2,
    gradientId: 'percentileP50Grad',
    gradientColor: paletteColor(2),
    gradientOpacity: 0.3,
  },
]

interface PercentileChartProps {
  data: PercentileDataPoint[]
  slaThresholdMs?: number
  height?: number
  formatValue?: (ms: number) => string
  dataKeys?: DataKeyConfig[]
  showLegend?: boolean
}

function defaultFormatValue(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatTimestamp(ts: number): string {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function PercentileChart({
  data,
  slaThresholdMs,
  height = 180,
  formatValue,
  dataKeys = DEFAULT_DATA_KEYS,
  showLegend = false,
}: PercentileChartProps) {
  const fmt = formatValue ?? defaultFormatValue
  const tickInterval = computeTickInterval(data.length)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
        <defs>
          {dataKeys.map((dk) => (
            <linearGradient key={dk.gradientId} id={dk.gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={dk.gradientColor} stopOpacity={dk.gradientOpacity} />
              <stop offset="95%" stopColor={dk.gradientColor} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid {...CHART_GRID_STYLE} />
        <XAxis
          dataKey="timestamp"
          tick={CHART_AXIS_STYLE.tick}
          axisLine={false}
          tickLine={false}
          tickFormatter={formatTimestamp}
          interval={tickInterval}
          minTickGap={24}
        />
        <YAxis
          tick={CHART_AXIS_STYLE.tick}
          axisLine={false}
          tickLine={false}
          tickFormatter={fmt}
        />
        <Tooltip content={<ChartTooltip formatValue={fmt} />} />
        {showLegend && (
          <Legend
            verticalAlign="top"
            align="right"
            height={28}
            iconType="plainline"
            wrapperStyle={{ fontSize: 12, color: 'var(--text-muted)' }}
          />
        )}
        {dataKeys.map((dk) => (
          <Area
            key={dk.key}
            type="monotone"
            dataKey={dk.key}
            name={dk.name}
            stroke={dk.stroke}
            strokeWidth={dk.strokeWidth ?? 1.5}
            fill={`url(#${dk.gradientId})`}
            animationDuration={800}
          />
        ))}
        {slaThresholdMs != null && (
          <ReferenceLine
            y={slaThresholdMs}
            stroke={paletteColor(4)}
            strokeDasharray="6 4"
            strokeWidth={1.5}
            label={{
              value: `SLA ${fmt(slaThresholdMs)}`,
              fill: paletteColor(4),
              fontSize: 11,
              position: 'right',
            }}
          />
        )}
      </AreaChart>
    </ResponsiveContainer>
  )
}

import { LineChart, Line } from 'recharts'

interface SparkLineProps {
  data: number[]
  width?: number
  height?: number
  color?: string
  trend?: 'up' | 'down' | 'flat'
}

function getTrendColor(trend: 'up' | 'down' | 'flat' | undefined, fallback: string): string {
  if (trend === 'up') return 'var(--green)'
  if (trend === 'down') return 'var(--red)'
  return fallback
}

export function SparkLine({
  data,
  width = 60,
  height = 24,
  color = 'var(--accent)',
  trend,
}: SparkLineProps) {
  const chartData = data.map((value, index) => ({ index, value }))
  const strokeColor = getTrendColor(trend, color)

  return (
    <LineChart
      width={width}
      height={height}
      data={chartData}
      margin={{ top: 2, right: 2, bottom: 2, left: 2 }}
    >
      <Line
        type="monotone"
        dataKey="value"
        stroke={strokeColor}
        strokeWidth={1.5}
        dot={false}
        isAnimationActive={false}
      />
    </LineChart>
  )
}

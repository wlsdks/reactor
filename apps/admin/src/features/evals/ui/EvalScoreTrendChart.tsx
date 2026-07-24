import { useTranslation } from 'react-i18next'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { ChartTooltip } from '../../../shared/ui/ChartTooltip'
import {
  CHART_AXIS_STYLE,
  CHART_GRID_STYLE,
  getAreaSeriesProps,
  paletteColor,
} from '../../../shared/ui/ChartConfig'
import type { EvalPassRatePoint } from '../types'

interface EvalScoreTrendChartProps {
  data: EvalPassRatePoint[]
}

export function EvalScoreTrendChart({ data }: EvalScoreTrendChartProps) {
  const { t } = useTranslation()

  if (data.length < 2) {
    return (
      <div className="eval-trend-chart">
        <div className="eval-trend-chart__header">
          <h3 className="eval-trend-chart__title">{t('evalsPage.scoreTrend')}</h3>
        </div>
        <div className="eval-trend-chart__empty">{t('common.noData')}</div>
      </div>
    )
  }

  const chartData = data.map(point => ({
    date: point.day,
    score: Math.round(point.avgScore * 100) / 100,
    passRate: point.total > 0 ? Math.round((point.passed / point.total) * 100) : 0,
  }))

  return (
    <div
      className="eval-trend-chart"
      role="region"
      aria-label={t('evalsPage.scoreTrend')}
    >
      <div className="eval-trend-chart__header">
        <h3 className="eval-trend-chart__title">{t('evalsPage.scoreTrend')}</h3>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
          <defs>
            <linearGradient id="evalScoreGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={paletteColor(2)} stopOpacity={0.3} />
              <stop offset="95%" stopColor={paletteColor(2)} stopOpacity={0} />
            </linearGradient>
            <linearGradient id="evalPassRateGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={paletteColor(1)} stopOpacity={0.3} />
              <stop offset="95%" stopColor={paletteColor(1)} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid {...CHART_GRID_STYLE} />
          <XAxis
            dataKey="date"
            tick={CHART_AXIS_STYLE.tick}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            yAxisId="score"
            tick={CHART_AXIS_STYLE.tick}
            axisLine={false}
            tickLine={false}
            domain={[0, 1]}
            tickFormatter={(v: number) => v.toFixed(1)}
          />
          <YAxis
            yAxisId="passRate"
            orientation="right"
            tick={CHART_AXIS_STYLE.tick}
            axisLine={false}
            tickLine={false}
            domain={[0, 100]}
            tickFormatter={(v: number) => `${v}%`}
          />
          <Tooltip content={<ChartTooltip />} />
          <Area
            yAxisId="score"
            type="monotone"
            dataKey="score"
            name={t('evalsPage.avgScore')}
            {...getAreaSeriesProps(2)}
            fill="url(#evalScoreGrad)"
            animationDuration={800}
          />
          <Area
            yAxisId="passRate"
            type="monotone"
            dataKey="passRate"
            name={t('evalsPage.passRate')}
            {...getAreaSeriesProps(1)}
            fill="url(#evalPassRateGrad)"
            animationDuration={800}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

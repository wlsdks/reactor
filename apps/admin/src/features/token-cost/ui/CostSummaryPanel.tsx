import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import {
  ChartTooltip,
  getAreaSeriesProps,
  paletteColor,
  ReleaseWorkflowBacklink,
} from '../../../shared/ui'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import {
  RELEASE_WORKFLOW_PATHS_BY_ID,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../../shared/releaseWorkflow'
import type { MessageCost } from '../types'

interface CostSummaryPanelProps {
  costs: MessageCost[]
}

function formatCostUsd(usd: number): string {
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(3)}`
}

interface ModelBreakdown {
  model: string
  totalTokens: number
  costUsd: number
  count: number
}

function computeModelBreakdown(costs: MessageCost[]): ModelBreakdown[] {
  const map = new Map<string, ModelBreakdown>()
  for (const c of costs) {
    const existing = map.get(c.model)
    if (existing) {
      existing.totalTokens += c.totalTokens
      existing.costUsd += c.estimatedCostUsd
      existing.count += 1
    } else {
      map.set(c.model, {
        model: c.model,
        totalTokens: c.totalTokens,
        costUsd: c.estimatedCostUsd,
        count: 1,
      })
    }
  }
  return [...map.values()].sort((a, b) => b.costUsd - a.costUsd)
}

interface ChartPoint {
  index: number
  cost: number
}

function buildChartData(costs: MessageCost[]): ChartPoint[] {
  const sorted = [...costs].sort((a, b) => a.time - b.time)
  return sorted.map((c, i) => ({
    index: i + 1,
    cost: c.estimatedCostUsd,
  }))
}

export function CostSummaryPanel({ costs }: CostSummaryPanelProps) {
  const { t } = useTranslation()

  if (costs.length === 0) return null

  const totalCost = costs.reduce((sum, c) => sum + c.estimatedCostUsd, 0)
  const totalTokens = costs.reduce((sum, c) => sum + c.totalTokens, 0)
  const breakdown = computeModelBreakdown(costs)
  const chartData = buildChartData(costs)

  return (
    <div className="cost-summary-panel" data-testid="cost-summary-panel">
      <div className="cost-summary-header">
        <h3 className="cost-summary-title">{t('tokenCost.sessionSummary')}</h3>
        <div className="inline-actions">
          <ReleaseWorkflowBacklink stepId="provider" />
          <Link className="btn btn-secondary btn-sm" to={RELEASE_WORKFLOW_PATHS_BY_ID.provider}>
            <span className="data-mono">{RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.provider}</span>
            {t('tokenCost.openProviderSmoke')}
          </Link>
        </div>
      </div>

      <div className="cost-summary-stats">
        <div className="cost-summary-stat">
          <span className="cost-summary-stat-label">{t('tokenCost.totalCost')}</span>
          <span className="cost-summary-stat-value">{formatCostUsd(totalCost)}</span>
        </div>
        <div className="cost-summary-stat">
          <span className="cost-summary-stat-label">{t('tokenCost.totalTokens')}</span>
          <span className="cost-summary-stat-value">{formatLocaleNumber(totalTokens)}</span>
        </div>
        <div className="cost-summary-stat">
          <span className="cost-summary-stat-label">{t('tokenCost.messages')}</span>
          <span className="cost-summary-stat-value">{costs.length}</span>
        </div>
      </div>

      {breakdown.length > 0 && (
        <div className="cost-summary-breakdown">
          <h4 className="cost-summary-subtitle">{t('tokenCost.modelBreakdown')}</h4>
          <div className="cost-summary-breakdown-list">
            {breakdown.map((b) => (
              <div key={b.model} className="cost-summary-breakdown-row">
                <span className="cost-summary-breakdown-model">{b.model}</span>
                <span className="cost-summary-breakdown-detail">
                  {b.count} {t('tokenCost.calls')} · {formatLocaleNumber(b.totalTokens)} {t('tokenCost.tok')} · {formatCostUsd(b.costUsd)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {chartData.length > 1 && (
        <div className="cost-summary-chart">
          <h4 className="cost-summary-subtitle">{t('tokenCost.costPerMessage')}</h4>
          <ResponsiveContainer width="100%" height={120}>
            <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
              <defs>
                <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={paletteColor(2)} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={paletteColor(2)} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="index" hide />
              <YAxis hide />
              <Tooltip
                content={<ChartTooltip formatValue={formatCostUsd} />}
                labelFormatter={(label: number) => `${t('tokenCost.message')} #${label}`}
              />
              <Area
                type="monotone"
                dataKey="cost"
                name={t('tokenCost.cost')}
                {...getAreaSeriesProps(2)}
                fill="url(#costGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

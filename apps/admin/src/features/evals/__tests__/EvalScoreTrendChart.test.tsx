import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '../../../test/utils'
import { EvalScoreTrendChart } from '../ui/EvalScoreTrendChart'
import { CHART_PALETTE } from '../../../shared/ui/ChartConfig'
import type { EvalPassRatePoint } from '../types'

function buildPoint(overrides: Partial<EvalPassRatePoint> = {}): EvalPassRatePoint {
  return {
    day: '2026-04-01',
    total: 20,
    passed: 17,
    avgScore: 0.85,
    ...overrides,
  }
}

describe('EvalScoreTrendChart', () => {
  it('shows empty state when fewer than 2 data points', () => {
    render(<EvalScoreTrendChart data={[buildPoint()]} />)
    expect(screen.getByText('evalsPage.scoreTrend')).toBeInTheDocument()
    expect(screen.getByText('common.noData')).toBeInTheDocument()
  })

  it('shows empty state for zero data points', () => {
    render(<EvalScoreTrendChart data={[]} />)
    expect(screen.getByText('common.noData')).toBeInTheDocument()
  })

  it('renders chart title when data has 2+ points', () => {
    const data = [
      buildPoint({ day: '2026-04-01' }),
      buildPoint({ day: '2026-04-02' }),
    ]
    render(<EvalScoreTrendChart data={data} />)
    expect(screen.getByText('evalsPage.scoreTrend')).toBeInTheDocument()
    expect(screen.queryByText('common.noData')).not.toBeInTheDocument()
  })

  it('adds ARIA region to chart container', () => {
    const data = [
      buildPoint({ day: '2026-04-01' }),
      buildPoint({ day: '2026-04-02' }),
    ]
    render(<EvalScoreTrendChart data={data} />)
    expect(screen.getByRole('region', { name: 'evalsPage.scoreTrend' })).toBeInTheDocument()
  })

  it('sources its colors from the shared CHART_PALETTE / ChartConfig (CB-safe migration)', () => {
    // Recharts under jsdom does not lay out a `ResponsiveContainer` so the
    // SVG defs (gradient stops, axis ticks) never paint — DOM assertions on
    // them would always be empty. Instead verify the source-level migration
    // is intact: the component imports from ChartConfig and references the
    // shared palette helpers, with no remaining `chartColors` legacy module
    // references.
    const source = readFileSync(
      resolve(__dirname, '../ui/EvalScoreTrendChart.tsx'),
      'utf8',
    )
    expect(source).toMatch(/from ['"][^'"]*ChartConfig['"]/)
    expect(source).toContain('paletteColor(')
    expect(source).toContain('getAreaSeriesProps(')
    expect(source).toContain('CHART_GRID_STYLE')
    expect(source).toContain('CHART_AXIS_STYLE')
    // Legacy hex hardcoding must not creep back in.
    expect(source).not.toMatch(/chartColors\./)
    // Sanity: palette retains the colors the chart depends on.
    expect(CHART_PALETTE[1]).toBeTruthy()
    expect(CHART_PALETTE[2]).toBeTruthy()
  })
})

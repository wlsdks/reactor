import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render } from '../../../test/utils'
import { PercentileChart } from '../PercentileChart'
import type { PercentileDataPoint } from '../PercentileChart'
import { computeTickInterval } from '../../lib/chart-ticks'

// Mock recharts ResponsiveContainer since it needs actual DOM dimensions.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container">{children}</div>
    ),
  }
})

const mockData: PercentileDataPoint[] = [
  { timestamp: 1700000000000, p50: 100, p95: 200, p99: 350 },
  { timestamp: 1700003600000, p50: 120, p95: 250, p99: 400 },
  { timestamp: 1700007200000, p50: 90, p95: 180, p99: 300 },
]

describe('PercentileChart', () => {
  it('renders without crashing', () => {
    const { container } = render(<PercentileChart data={mockData} />)
    expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument()
  })

  it('renders with custom height', () => {
    const { container } = render(<PercentileChart data={mockData} height={300} />)
    expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument()
  })

  it('renders with SLA threshold', () => {
    const { container } = render(
      <PercentileChart data={mockData} slaThresholdMs={250} />,
    )
    expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument()
  })

  it('renders with empty data', () => {
    const { container } = render(<PercentileChart data={[]} />)
    expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument()
  })

  it('renders with custom formatValue', () => {
    const customFormat = (ms: number) => `${ms}ms`
    const { container } = render(
      <PercentileChart data={mockData} formatValue={customFormat} />,
    )
    expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument()
  })

  it('renders when showLegend is enabled', () => {
    const { container } = render(
      <PercentileChart data={mockData} showLegend />,
    )
    // Recharts under jsdom + mocked ResponsiveContainer does not paint an SVG,
    // so we only verify the component accepts and renders with the prop
    // without crashing. Legend visibility is covered by E2E / manual QA.
    expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument()
  })

  it('computes even tick intervals for common series lengths', () => {
    // 24 hourly points → interval 3 → 6 visible ticks (0, 4, 8, 12, 16, 20)
    expect(computeTickInterval(24)).toBe(3)
    // Small series under target → interval 0 (show all ticks)
    expect(computeTickInterval(4)).toBe(0)
    // Long series (7-day × 24h)
    expect(computeTickInterval(168)).toBe(27)
  })

  it('sources its colors from the shared CHART_PALETTE / ChartConfig (CB-safe migration)', () => {
    // PercentileChart's default keys (P99 → P95 → P50) and SLA reference line
    // must consume `paletteColor` + axis/grid presets from ChartConfig rather
    // than the legacy `chartColors` module — mirrors EvalScoreTrendChart guard.
    const source = readFileSync(
      resolve(__dirname, '../PercentileChart.tsx'),
      'utf8',
    )
    expect(source).toMatch(/from ['"][^'"]*ChartConfig['"]/)
    expect(source).toContain('paletteColor(')
    expect(source).toContain('CHART_GRID_STYLE')
    expect(source).toContain('CHART_AXIS_STYLE')
    expect(source).not.toMatch(/chartColors\./)
  })
})

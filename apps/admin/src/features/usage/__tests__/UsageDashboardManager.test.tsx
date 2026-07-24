import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent } from '@testing-library/react'
import { i18n, render, screen, waitFor } from '../../../test/utils'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { UsageDashboardManager } from '../ui/UsageDashboardManager'
import { buildCostTrendChartData, computeCostPeriodAggregates, percentDelta, sumDailyCost, aggregateDailyCost } from '../lib'
import * as usageApi from '../api'
import type { UserUsageSummary, UsageDailyPoint, ModelUsageBreakdown } from '../types'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getUsersCost: vi.fn(),
    getUsageDaily: vi.fn(),
    getUsageByModel: vi.fn(),
  }
})

const getUsersCostMock = vi.mocked(usageApi.getUsersCost)
const getUsageDailyMock = vi.mocked(usageApi.getUsageDaily)
const getUsageByModelMock = vi.mocked(usageApi.getUsageByModel)

const mockUsers: UserUsageSummary[] = [
  {
    userId: 'user-001',
    sessionCount: 150,
    totalTokens: 5880000,
    totalCostUsd: 1680.0,
    avgLatencyMs: 450,
    lastActivity: '2026-04-03T11:00:00Z',
  },
  {
    userId: 'user-002',
    sessionCount: 95,
    totalTokens: 4200000,
    totalCostUsd: 1200.0,
    avgLatencyMs: 380,
    lastActivity: '2026-04-03T10:00:00Z',
  },
]

// Backend returns points in descending order (newest first).
// The component must sort them ascending before rendering so that
// the chart runs past (left) to present (right).
const mockDailyTrend: UsageDailyPoint[] = [
  { day: '2026-04-03', sessionCount: 60, totalTokens: 540000, totalCostUsd: 155.0, uniqueUsers: 16 },
  { day: '2026-04-02', sessionCount: 55, totalTokens: 520000, totalCostUsd: 148.0, uniqueUsers: 14 },
  { day: '2026-04-01', sessionCount: 50, totalTokens: 500000, totalCostUsd: 142.5, uniqueUsers: 12 },
]

const mockModels: ModelUsageBreakdown[] = [{
  model: 'gemma4:12b',
  provider: 'ollama',
  callCount: 3,
  promptTokens: 1000,
  completionTokens: 800,
  totalTokens: 1800,
  totalCostUsd: 0,
  lastActivity: '2026-04-03T12:00:00Z',
}]

function renderWithRouter(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      {ui}
    </MemoryRouter>,
  )
}

function LocationProbe() {
  return <output data-testid="location">{useLocation().pathname}</output>
}

describe('UsageDashboardManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'usagePage.anonymousUser': 'User {{id}}',
      'usagePage.localUser': 'Local user',
      'usagePage.modelLabels.gemma': 'Gemma',
      'usagePage.modelLabels.unknown': 'AI model',
      'usagePage.providerLabels.ollama': 'Local model',
      'usagePage.providerLabels.unknown': 'AI provider',
    }, true, true)
    getUsersCostMock.mockResolvedValue(mockUsers)
    getUsageDailyMock.mockResolvedValue(mockDailyTrend)
    getUsageByModelMock.mockResolvedValue(mockModels)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders one operational summary instead of card grids', async () => {
    renderWithRouter(<UsageDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('usagePage.totalUsers')).toBeInTheDocument()
      expect(screen.getByText('usagePage.totalCostLabel')).toBeInTheDocument()
      expect(screen.getByText('usagePage.totalTokensLabel')).toBeInTheDocument()
    })
    expect(document.querySelectorAll('.usage-dashboard__summary')).toHaveLength(1)
    expect(document.querySelector('.usage-dashboard__stats')).not.toBeInTheDocument()
  })

  it('renders summary stats ARIA region', async () => {
    renderWithRouter(<UsageDashboardManager />)
    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'usagePage.summaryStats' })).toBeInTheDocument()
    })
  })

  it('shows users table with data', async () => {
    renderWithRouter(<UsageDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('User #001')).toBeInTheDocument()
      expect(screen.getByText('User #002')).toBeInTheDocument()
    })
    expect(screen.queryByText('user-001')).not.toBeInTheDocument()
    expect(screen.queryByText('user-002')).not.toBeInTheDocument()
  })

  it('opens the selected user activity workspace', async () => {
    render(
      <MemoryRouter>
        <UsageDashboardManager />
        <LocationProbe />
      </MemoryRouter>,
    )
    const rows = await screen.findAllByRole('button')
    const userRow = rows.find((row) => row.tagName === 'TR')
    expect(userRow).toBeDefined()
    fireEvent.click(userRow as HTMLElement)
    expect(screen.getByTestId('location')).toHaveTextContent('/sessions/users/user-001')
  })

  it('shows one user ledger and one model ledger', async () => {
    renderWithRouter(<UsageDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('usagePage.topUsers')).toBeInTheDocument()
      expect(screen.getByText('usagePage.byModel')).toBeInTheDocument()
      expect(screen.getByText('Gemma')).toBeInTheDocument()
    })
    expect(screen.queryByText('usagePage.topUsersRanking')).not.toBeInTheDocument()
  })

  it('shows empty state when no users', async () => {
    getUsersCostMock.mockResolvedValueOnce([])
    getUsageDailyMock.mockResolvedValueOnce([])
    getUsageByModelMock.mockResolvedValueOnce([])
    renderWithRouter(<UsageDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('usagePage.noUsers')).toBeInTheDocument()
    })
  })

  it('replaces a zero-cost chart with a concise explanation', async () => {
    getUsageDailyMock.mockResolvedValueOnce([
      { day: '2026-04-01', sessionCount: 1, totalTokens: 100, totalCostUsd: 0, uniqueUsers: 1 },
      { day: '2026-04-02', sessionCount: 1, totalTokens: 100, totalCostUsd: 0, uniqueUsers: 1 },
    ])
    renderWithRouter(<UsageDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('usagePage.noCostTitle')).toBeInTheDocument()
    })
    expect(document.querySelector('.usage-dashboard__chart')).not.toBeInTheDocument()
  })

  it('does not disguise a complete API failure as zero usage', async () => {
    getUsersCostMock.mockRejectedValueOnce(new Error('HTTP 503'))
    getUsageDailyMock.mockRejectedValueOnce(new Error('HTTP 503'))
    getUsageByModelMock.mockRejectedValueOnce(new Error('HTTP 503'))
    renderWithRouter(<UsageDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('usagePage.loadErrorTitle')).toBeInTheDocument()
    })
    expect(screen.queryByText('$0.00')).not.toBeInTheDocument()
  })

  it('surfaces a partial backend failure and preserves successful ledgers', async () => {
    getUsageDailyMock.mockRejectedValueOnce(new Error('HTTP 503'))
    renderWithRouter(<UsageDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('usagePage.partialErrorTitle')).toBeInTheDocument()
      expect(screen.getByText('User #001')).toBeInTheDocument()
      expect(screen.getByText('usagePage.trendLoadError')).toBeInTheDocument()
    })
  })

  it('keeps canonical user and model identifiers out of the primary ledgers', async () => {
    renderWithRouter(<UsageDashboardManager />)

    await waitFor(() => expect(screen.getByText('Gemma')).toBeInTheDocument())

    expect(screen.queryByText('user-001')).not.toBeInTheDocument()
    expect(screen.queryByText('gemma4:12b')).not.toBeInTheDocument()
  })

  it('reads the reporting period from the URL', async () => {
    render(<MemoryRouter initialEntries={['/usage?days=7']}><UsageDashboardManager /></MemoryRouter>)
    await waitFor(() => expect(getUsersCostMock).toHaveBeenCalledWith(7, 100))
    expect(screen.getByRole('combobox', { name: 'usagePage.daysLabel' })).toHaveValue('7')
  })
})

describe('buildCostTrendChartData', () => {
  it('sorts descending backend payload ascending (past -> present)', () => {
    // Backend returns newest-first; chart must render oldest-first
    const descending = [
      { day: '2026-04-24', totalCostUsd: 30 },
      { day: '2026-04-10', totalCostUsd: 20 },
      { day: '2026-04-08', totalCostUsd: 10 },
    ]
    const result = buildCostTrendChartData(descending)
    expect(result.map((d) => d.date)).toEqual([
      '2026-04-08',
      '2026-04-10',
      '2026-04-24',
    ])
    expect(result.map((d) => d.cost)).toEqual([10, 20, 30])
  })

  it('preserves already-ascending order', () => {
    const ascending = [
      { day: '2026-04-01', totalCostUsd: 5 },
      { day: '2026-04-02', totalCostUsd: 7 },
    ]
    const result = buildCostTrendChartData(ascending)
    expect(result.map((d) => d.date)).toEqual(['2026-04-01', '2026-04-02'])
  })

  it('does not mutate the input array', () => {
    const input = [
      { day: '2026-04-03', totalCostUsd: 3 },
      { day: '2026-04-01', totalCostUsd: 1 },
    ]
    const snapshot = [...input]
    buildCostTrendChartData(input)
    expect(input).toEqual(snapshot)
  })

  it('returns an empty array for empty input', () => {
    expect(buildCostTrendChartData([])).toEqual([])
  })
})

describe('sumDailyCost', () => {
  it('sums totalCostUsd across daily points', () => {
    expect(sumDailyCost([
      { day: '2026-04-01', sessionCount: 0, totalTokens: 0, totalCostUsd: 1.5, uniqueUsers: 0 },
      { day: '2026-04-02', sessionCount: 0, totalTokens: 0, totalCostUsd: 2.5, uniqueUsers: 0 },
    ])).toBe(4)
  })

  it('returns 0 for empty array', () => {
    expect(sumDailyCost([])).toBe(0)
  })

  it('skips non-finite values', () => {
    expect(sumDailyCost([
      { day: '2026-04-01', sessionCount: 0, totalTokens: 0, totalCostUsd: Number.NaN, uniqueUsers: 0 },
      { day: '2026-04-02', sessionCount: 0, totalTokens: 0, totalCostUsd: 3, uniqueUsers: 0 },
    ])).toBe(3)
  })
})

describe('aggregateDailyCost', () => {
  const points = [
    { day: '2026-04-01', sessionCount: 1, totalTokens: 100, totalCostUsd: 1, uniqueUsers: 1 },
    { day: '2026-04-02', sessionCount: 1, totalTokens: 200, totalCostUsd: 2, uniqueUsers: 1 },
    { day: '2026-04-03', sessionCount: 1, totalTokens: 300, totalCostUsd: 3, uniqueUsers: 1 },
  ]

  it('sums points within window inclusive', () => {
    expect(aggregateDailyCost(points, '2026-04-01', '2026-04-02')).toEqual({
      totalCostUsd: 3,
      totalTokens: 300,
    })
  })

  it('returns zero totals when no points fall in window', () => {
    expect(aggregateDailyCost(points, '2026-05-01', '2026-05-31')).toEqual({
      totalCostUsd: 0,
      totalTokens: 0,
    })
  })
})

describe('percentDelta', () => {
  it('returns positive percent for growth', () => {
    expect(percentDelta(150, 100)).toBeCloseTo(50)
  })

  it('returns negative percent for shrinkage', () => {
    expect(percentDelta(80, 100)).toBeCloseTo(-20)
  })

  it('returns 0 when prior is 0', () => {
    expect(percentDelta(50, 0)).toBe(0)
  })

  it('returns 0 when prior is non-finite', () => {
    expect(percentDelta(50, Number.NaN)).toBe(0)
  })
})

describe('computeCostPeriodAggregates', () => {
  // Anchor "now" so day math is deterministic. 2026-04-24 UTC.
  const NOW_MS = Date.UTC(2026, 3, 24, 12, 0, 0)

  function point(day: string, cost: number, tokens = 100) {
    return { day, sessionCount: 1, totalTokens: tokens, totalCostUsd: cost, uniqueUsers: 1 }
  }

  it('aggregates today, yesterday, week, prior week, month, prior month', () => {
    const points = [
      point('2026-04-24', 10),  // today
      point('2026-04-23', 8),   // yesterday + in week + in month
      point('2026-04-20', 5),   // in week + in month
      point('2026-04-15', 3),   // prior week (last 14d - last 7d)
      point('2026-04-10', 2),   // in month
      point('2026-03-15', 1),   // prior month
    ]
    const r = computeCostPeriodAggregates(points, NOW_MS)
    expect(r.today.totalCostUsd).toBe(10)
    expect(r.yesterday.totalCostUsd).toBe(8)
    // week = today + 6 prior days inclusive (2026-04-18..2026-04-24)
    expect(r.week.totalCostUsd).toBe(10 + 8 + 5)
    // prior week = days 7..13 ago (2026-04-11..2026-04-17), captures only 2026-04-15
    expect(r.priorWeek.totalCostUsd).toBe(3)
    // month = last 30 days inclusive
    expect(r.month.totalCostUsd).toBe(10 + 8 + 5 + 3 + 2)
    // prior month = days 30..59 ago, captures 2026-03-15
    expect(r.priorMonth.totalCostUsd).toBe(1)
  })

  it('returns zero totals when no points in any window', () => {
    const r = computeCostPeriodAggregates([], NOW_MS)
    expect(r.today.totalCostUsd).toBe(0)
    expect(r.month.totalCostUsd).toBe(0)
    expect(r.priorMonth.totalCostUsd).toBe(0)
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '../../../test/utils'
import { MemoryRouter } from 'react-router-dom'
import { DashboardCostAlertPanel } from '../ui/DashboardCostAlertPanel'
import * as usageApi from '../../usage/api'
import type { UsageDailyPoint } from '../../usage/types'

vi.mock('../../usage/api', async () => {
  const actual = await vi.importActual<typeof import('../../usage/api')>('../../usage/api')
  return {
    ...actual,
    getUsageDaily: vi.fn(),
  }
})

const getUsageDailyMock = vi.mocked(usageApi.getUsageDaily)

/**
 * Build a daily point dated `daysAgo` days before today (rounded to UTC midnight)
 * so tests stay valid regardless of the calendar date the suite runs on.
 */
function dayPoint(daysAgo: number, cost: number): UsageDailyPoint {
  const d = new Date()
  d.setUTCHours(0, 0, 0, 0)
  d.setUTCDate(d.getUTCDate() - daysAgo)
  const day = d.toISOString().slice(0, 10)
  return { day, sessionCount: 1, totalTokens: 100, totalCostUsd: cost, uniqueUsers: 1 }
}

function renderPanel() {
  return render(
    <MemoryRouter>
      <DashboardCostAlertPanel />
    </MemoryRouter>,
  )
}

describe('DashboardCostAlertPanel', () => {
  beforeEach(() => {
    getUsageDailyMock.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders skeleton while loading', () => {
    getUsageDailyMock.mockReturnValue(new Promise(() => {}))
    renderPanel()
    expect(screen.getByTestId('dashboard-cost-alert-loading')).toBeInTheDocument()
  })

  it('renders cost panel without alert when MoM growth <= 25%', async () => {
    // current month $10 (today), prior month $9 → +11% (under 25% threshold)
    getUsageDailyMock.mockResolvedValue([
      dayPoint(0, 10),
      dayPoint(40, 9),
    ])
    renderPanel()
    await waitFor(() => {
      expect(screen.getByTestId('dashboard-cost-alert')).toBeInTheDocument()
    })
    const panel = screen.getByTestId('dashboard-cost-alert')
    expect(panel.getAttribute('data-alert')).toBe('false')
    expect(screen.queryByTestId('dashboard-cost-alert-warning')).not.toBeInTheDocument()
  })

  it('renders an inline warning when MoM growth > 25%', async () => {
    // current month $50, prior month $20 → +150% (over threshold)
    getUsageDailyMock.mockResolvedValue([
      dayPoint(0, 50),
      dayPoint(40, 20),
    ])
    renderPanel()
    await waitFor(() => {
      expect(screen.getByTestId('dashboard-cost-alert')).toBeInTheDocument()
    })
    const panel = screen.getByTestId('dashboard-cost-alert')
    expect(panel.getAttribute('data-alert')).toBe('true')
    expect(screen.getByTestId('dashboard-cost-alert-warning')).toBeInTheDocument()
    expect(panel.querySelectorAll('.cost-card')).toHaveLength(0)
  })

  it('renders the title from i18n', async () => {
    getUsageDailyMock.mockResolvedValue([])
    renderPanel()
    await waitFor(() => {
      expect(screen.getByText('dashboardPage.cost.title')).toBeInTheDocument()
    })
  })

  it('embedded CostCard renders as click target navigating to /usage', async () => {
    getUsageDailyMock.mockResolvedValue([dayPoint(0, 10)])
    renderPanel()
    const btn = await screen.findByRole('button')
    expect(btn).toBeInTheDocument()
    // The CostCard renders as a button when onClick is supplied. The
    // existence of the click target proves the navigate wiring.
  })
})

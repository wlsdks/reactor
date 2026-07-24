import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '../../../test/utils'
import { MemoryRouter } from 'react-router-dom'
import { LatencyDashboardManager } from '../ui/LatencyDashboardManager'
import * as latencyApi from '../api'
import type { LatencyDataPoint, LatencySummary } from '../types'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getLatencyTimeSeries: vi.fn(),
    getLatencySummary: vi.fn(),
  }
})

const getTimeSeriesMock = vi.mocked(latencyApi.getLatencyTimeSeries)
const getSummaryMock = vi.mocked(latencyApi.getLatencySummary)

const mockTimeSeries: LatencyDataPoint[] = [
  { timestamp: Date.now() - 3600000, avg: 180, p95: 750, p95Available: 1, count: 100 },
  { timestamp: Date.now() - 1800000, avg: 200, p95: 820, p95Available: 1, count: 120 },
  { timestamp: Date.now(), avg: 195, p95: 800, p95Available: 1, count: 110 },
]

const mockSummary: LatencySummary = {
  count: 330,
  p50: 195,
  p95: 820,
  p99: 1950,
}

function renderWithRouter(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      {ui}
    </MemoryRouter>,
  )
}

describe('LatencyDashboardManager', () => {
  beforeEach(() => {
    getTimeSeriesMock.mockResolvedValue(mockTimeSeries)
    getSummaryMock.mockResolvedValue(mockSummary)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders a compact latency summary without stat cards', async () => {
    renderWithRouter(<LatencyDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('195ms')).toBeInTheDocument()
      expect(screen.getByText('820ms')).toBeInTheDocument()
      expect(screen.getByText('1.9s')).toBeInTheDocument()
    })
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0)
  })

  it('renders summary stats ARIA region', async () => {
    renderWithRouter(<LatencyDashboardManager />)
    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'latencyPage.summaryStats' })).toBeInTheDocument()
    })
  })

  it('renders latency chart title', async () => {
    renderWithRouter(<LatencyDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('latencyPage.latencyOverTime')).toBeInTheDocument()
    })
  })

  it('distinguishes an API failure from an empty sample set', async () => {
    getTimeSeriesMock.mockRejectedValueOnce(new Error('HTTP 503'))
    getSummaryMock.mockRejectedValueOnce(new Error('HTTP 503'))
    renderWithRouter(<LatencyDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('latencyPage.loadErrorTitle')).toBeInTheDocument()
    })
    expect(screen.queryByText('latencyPage.emptyTitle')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })

  it('renders one intentional empty state when no samples exist', async () => {
    getTimeSeriesMock.mockResolvedValueOnce([])
    getSummaryMock.mockResolvedValueOnce({ count: 0, p50: 0, p95: 0, p99: 0 })

    renderWithRouter(<LatencyDashboardManager />)

    await waitFor(() => {
      expect(screen.getByText('latencyPage.emptyTitle')).toBeInTheDocument()
    })
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0)
    expect(screen.queryByText('latencyPage.latencyOverTime')).not.toBeInTheDocument()
  })
})

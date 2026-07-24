import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'

import { i18n, render, screen, waitFor } from '../../test/utils'
import * as toolStatsApi from '../../features/tool-stats/api'
import * as latencyApi from '../../features/latency/api'
import { PerformancePage } from '../PerformancePage'

vi.mock('../../features/tool-stats/api', async () => {
  const actual =
    await vi.importActual<typeof import('../../features/tool-stats/api')>(
      '../../features/tool-stats/api',
    )
  return {
    ...actual,
    getToolStats: vi.fn(),
    getToolAccuracy: vi.fn(),
  }
})

vi.mock('../../features/latency/api', async () => {
  const actual =
    await vi.importActual<typeof import('../../features/latency/api')>(
      '../../features/latency/api',
    )
  return {
    ...actual,
    getLatencyTimeSeries: vi.fn(),
    getLatencySummary: vi.fn(),
  }
})

const getToolStatsMock = vi.mocked(toolStatsApi.getToolStats)
const getToolAccuracyMock = vi.mocked(toolStatsApi.getToolAccuracy)
const getLatencyTimeSeriesMock = vi.mocked(latencyApi.getLatencyTimeSeries)
const getLatencySummaryMock = vi.mocked(latencyApi.getLatencySummary)

function renderPage(initialEntries: string[] = ['/performance']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <PerformancePage />
    </MemoryRouter>,
  )
}

describe('PerformancePage', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'common.releaseWorkflowBacklink': 'Release workflow',
      'common.releaseWorkflowBacklinkStep': 'Release workflow step {{step}}',
    }, true, true)
    getToolStatsMock.mockReset()
    getToolAccuracyMock.mockReset()
    getLatencyTimeSeriesMock.mockReset()
    getLatencySummaryMock.mockReset()
    getLatencyTimeSeriesMock.mockResolvedValue([])
    getLatencySummaryMock.mockResolvedValue({ count: 10, p50: 100, p95: 250, p99: 400 })
    getToolStatsMock.mockResolvedValue({
      total: 0,
      byOutcome: {},
      byServer: {},
      byTool: [],
      accuracy: 0,
    })
    getToolAccuracyMock.mockResolvedValue({
      total: 0,
      ok: 0,
      accuracy: 0,
      invalidCallRate: 0,
      timeoutRate: 0,
      notFoundRate: 0,
    })
  })

  it('renders Latency segment as the default selected tab', () => {
    renderPage()

    const latencyTab = screen.getByRole('tab', {
      name: 'performancePage.segments.latency',
    })
    expect(latencyTab).toHaveAttribute('aria-selected', 'true')

    const toolsTab = screen.getByRole('tab', {
      name: 'performancePage.segments.tools',
    })
    expect(toolsTab).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('tab', {
      name: 'performancePage.segments.conversations',
    })).toHaveAttribute('aria-selected', 'false')
  })

  it('does not duplicate the release workflow inside analysis', () => {
    renderPage()
    expect(screen.queryByRole('link', { name: 'Release workflow step 1' })).not.toBeInTheDocument()
  })

  it('switches to the Tools segment when the Tools tab is clicked', async () => {
    const user = userEvent.setup()
    renderPage()

    const toolsTab = screen.getByRole('tab', {
      name: 'performancePage.segments.tools',
    })
    await user.click(toolsTab)

    expect(toolsTab).toHaveAttribute('aria-selected', 'true')
    // Tools segment surfaces the total-calls stat card label.
    await waitFor(() => {
      expect(getToolStatsMock).toHaveBeenCalled()
    })
  })

  it('renders the Tools segment when initial URL has ?seg=tools', async () => {
    renderPage(['/performance?seg=tools'])

    const toolsTab = screen.getByRole('tab', {
      name: 'performancePage.segments.tools',
    })
    expect(toolsTab).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => {
      expect(getToolStatsMock).toHaveBeenCalled()
    })
  })

  it('renders conversation analysis as one URL-addressable top-level segment', () => {
    renderPage(['/performance?seg=conversations'])

    expect(screen.getByRole('tab', {
      name: 'performancePage.segments.conversations',
    })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByRole('tablist')).toHaveLength(1)
  })

  it('falls back to Latency when ?seg has an unknown value', () => {
    renderPage(['/performance?seg=bogus'])

    const latencyTab = screen.getByRole('tab', {
      name: 'performancePage.segments.latency',
    })
    expect(latencyTab).toHaveAttribute('aria-selected', 'true')
  })
})

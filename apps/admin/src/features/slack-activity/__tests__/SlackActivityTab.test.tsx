import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor } from '../../../test/utils'
import {
  RELEASE_WORKFLOW_ANCHOR_PATH,
  RELEASE_SLACK_GATEWAY_PATH,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../../shared/releaseWorkflow'
import { SlackActivityTab } from '../ui/SlackActivityTab'
import * as api from '../api'
import type { SlackChannelStats, SlackDailyStats } from '../types'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getSlackChannels: vi.fn(),
    getSlackDaily: vi.fn(),
  }
})

const getChannelsMock = vi.mocked(api.getSlackChannels)
const getDailyMock = vi.mocked(api.getSlackDaily)

const mockChannels: SlackChannelStats[] = [
  { channel: '#general', sessionCount: 245, uniqueUsers: 42, totalTokens: 185000, totalCostUsd: 12.5, avgLatencyMs: 320 },
  { channel: '#support', sessionCount: 180, uniqueUsers: 28, totalTokens: 132000, totalCostUsd: 9.2, avgLatencyMs: 410 },
]

const mockDaily: SlackDailyStats[] = [
  { day: '2026-04-01', messageCount: 50, uniqueUsers: 15, successCount: 45, failureCount: 5 },
  { day: '2026-04-02', messageCount: 62, uniqueUsers: 18, successCount: 58, failureCount: 4 },
  { day: '2026-04-03', messageCount: 48, uniqueUsers: 12, successCount: 44, failureCount: 4 },
]

function renderSlackActivityTab() {
  return render(
    <MemoryRouter>
      <SlackActivityTab />
    </MemoryRouter>,
  )
}

describe('SlackActivityTab', () => {
  beforeEach(() => {
    getChannelsMock.mockResolvedValue(mockChannels)
    getDailyMock.mockResolvedValue(mockDaily)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders stat cards with aggregated values', async () => {
    renderSlackActivityTab()
    await waitFor(() => {
      const labels = Array.from(document.querySelectorAll('.stat-card-label'))
        .map((node) => node.textContent)
      expect(labels).toEqual([
        'slackActivityTab.totalSessions',
        'slackActivityTab.uniqueUsers',
        'slackActivityTab.totalTokens',
        'slackActivityTab.avgLatency',
      ])
    })
  })

  it('renders channel data in table', async () => {
    renderSlackActivityTab()
    await waitFor(() => {
      expect(screen.getByText('#general')).toBeInTheDocument()
      expect(screen.getByText('#support')).toBeInTheDocument()
    })
  })

  it('renders chart region', async () => {
    renderSlackActivityTab()
    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'slackActivityTab.dailyTrend' })).toBeInTheDocument()
    })
  })

  it('renders days selector buttons', async () => {
    renderSlackActivityTab()
    await waitFor(() => {
      const buttons = screen.getAllByText('tracesPage.filters.lastNDays')
      expect(buttons.length).toBeGreaterThanOrEqual(3)
    })
  })

  it('links Slack activity analytics back to Slack gateway smoke evidence', async () => {
    renderSlackActivityTab()
    await screen.findByText('#general')
    const smokeLink = screen.getByRole('link', {
      name: /integrationsPage\.releaseSmoke\.workflowSlack/,
    })
    expect(smokeLink).toHaveAttribute('href', RELEASE_SLACK_GATEWAY_PATH)
    expect(smokeLink)
      .toHaveTextContent(`${RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations}integrationsPage.releaseSmoke.workflowSlack`)
  })

  it('links Slack activity operations back to the release workflow cockpit', async () => {
    renderSlackActivityTab()
    await screen.findByText('#general')

    expect(screen.getByRole('link', { name: 'common.releaseWorkflowBacklinkStep' }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_ANCHOR_PATH)
  })

  it('sources its colors from the shared CHART_PALETTE / ChartConfig (CB-safe migration)', () => {
    // Recharts under jsdom does not lay out a `ResponsiveContainer` so the SVG
    // defs (gradient stops, axis ticks) never paint — DOM assertions on them
    // would always be empty. Instead verify the source-level migration is
    // intact: the component imports from the shared UI barrel and references
    // the ChartConfig palette helpers, with no remaining `chartColors` legacy
    // module references.
    const source = readFileSync(
      resolve(__dirname, '../ui/SlackActivityTab.tsx'),
      'utf8',
    )
    expect(source).toContain('paletteColor(')
    expect(source).toContain('getAreaSeriesProps(')
    expect(source).toContain('CHART_GRID_STYLE')
    expect(source).toContain('CHART_AXIS_STYLE')
    // Legacy hex hardcoding must not creep back in.
    expect(source).not.toMatch(/chartColors\./)
  })
})

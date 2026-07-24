import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen, waitFor } from '../../../test/utils'
import { RagAnalyticsTab } from '../ui/RagAnalyticsTab'
import * as api from '../api'
import type { RagStatusSummary, RagChannelStats } from '../types'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getRagStatus: vi.fn(),
    getRagByChannel: vi.fn(),
  }
})

const getStatusMock = vi.mocked(api.getRagStatus)
const getByChannelMock = vi.mocked(api.getRagByChannel)

const mockStatuses: RagStatusSummary[] = [
  { status: 'PENDING', count: 24, latestCaptured: '2026-04-05T12:00:00Z' },
  { status: 'INGESTED', count: 1832, latestCaptured: '2026-04-05T11:00:00Z' },
  { status: 'REJECTED', count: 47, latestCaptured: '2026-04-04T12:00:00Z' },
]

const mockByChannel: RagChannelStats[] = [
  { channel: '#support', candidateCount: 420, ingested: 380, pending: 15, rejected: 25 },
  { channel: '#engineering', candidateCount: 310, ingested: 290, pending: 8, rejected: 12 },
  { channel: '#general', candidateCount: 180, ingested: 162, pending: 1, rejected: 17 },
]

describe('RagAnalyticsTab', () => {
  beforeEach(() => {
    getStatusMock.mockResolvedValue(mockStatuses)
    getByChannelMock.mockResolvedValue(mockByChannel)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders one compact processing summary instead of stat cards', async () => {
    render(<RagAnalyticsTab />)
    await waitFor(() => {
      expect(screen.getByLabelText('Knowledge processing summary')).toBeInTheDocument()
    })
    expect(screen.queryByText('RAGANALYTICSTAB.PENDING')).not.toBeInTheDocument()
    expect(document.querySelector('.stat-grid')).toBeNull()
  })

  it('renders channel data in table', async () => {
    render(<RagAnalyticsTab />)
    await waitFor(() => {
      expect(screen.getByText('#support')).toBeInTheDocument()
      expect(screen.getByText('#engineering')).toBeInTheDocument()
      expect(screen.getByText('#general')).toBeInTheDocument()
    })
  })

  it('renders chart region', async () => {
    render(<RagAnalyticsTab />)
    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'Collection by channel' })).toBeInTheDocument()
    })
  })

  it('renders days selector', async () => {
    render(<RagAnalyticsTab />)
    await waitFor(() => {
      expect(screen.getByText('Knowledge collection overview')).toBeInTheDocument()
    })
  })

  it('uses the shared chart palette and a categorical bar chart', () => {
    const source = readFileSync(
      resolve(__dirname, '../ui/RagAnalyticsTab.tsx'),
      'utf8',
    )
    expect(source).toContain('paletteColor(')
    expect(source).toContain('<BarChart')
    expect(source).toContain('<Bar')
    expect(source).toContain('CHART_GRID_STYLE')
    expect(source).toContain('CHART_AXIS_STYLE')
    expect(source).not.toContain('<AreaChart')
    expect(source).not.toMatch(/chartColors\./)
  })
})

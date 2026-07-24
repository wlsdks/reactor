import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { render, screen, waitFor } from '../../../test/utils'
import * as api from '../api'
import { ToolsSegment } from '../ui/ToolsSegment'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getToolStats: vi.fn(),
    getToolAccuracy: vi.fn(),
  }
})

const sampleStats = {
  total: 100,
  byOutcome: { ok: 80, error: 15, timeout: 5 },
  byServer: { 'mcp-a': 63, 'mcp-b': 37 },
  byTool: [
    { tool: 'web.search', server: 'mcp-a', outcome: 'ok', count: 40 },
    { tool: 'web.search', server: 'mcp-a', outcome: 'error', count: 10 },
    { tool: 'web.search', server: 'mcp-b', outcome: 'ok', count: 20 },
    { tool: 'fs.read', server: 'mcp-b', outcome: 'ok', count: 30 },
  ],
  accuracy: 0.85,
}

const sampleAccuracy = {
  total: 100,
  ok: 85,
  accuracy: 0.85,
  invalidCallRate: 0.02,
  timeoutRate: 0.05,
  notFoundRate: 0.08,
}

const getToolStatsMock = vi.mocked(api.getToolStats)
const getToolAccuracyMock = vi.mocked(api.getToolAccuracy)

function renderSegment() {
  return render(
    <MemoryRouter>
      <ToolsSegment />
    </MemoryRouter>,
  )
}

describe('ToolsSegment', () => {
  beforeEach(() => {
    getToolStatsMock.mockReset()
    getToolAccuracyMock.mockReset()
  })

  it('renders headline stat cards once data loads', async () => {
    getToolStatsMock.mockResolvedValue(sampleStats)
    getToolAccuracyMock.mockResolvedValue(sampleAccuracy)

    renderSegment()

    // total calls
    await waitFor(() => {
      expect(screen.getByText('100')).toBeInTheDocument()
    })
    // success rate (80%)
    expect(screen.getByText('80%')).toBeInTheDocument()
    // error rate (15%)
    expect(screen.getByText('15%')).toBeInTheDocument()
    // timeout rate (5%)
    expect(screen.getByText('5%')).toBeInTheDocument()
    // accuracy gauge (85%)
    expect(screen.getByText('85%')).toBeInTheDocument()
  })

  it('renders friendly tool labels without exposing backend identifiers in the table', async () => {
    getToolStatsMock.mockResolvedValue(sampleStats)
    getToolAccuracyMock.mockResolvedValue(sampleAccuracy)

    renderSegment()

    // BE returned 4 tuples spanning 2 distinct tools — table shows two
    // human-facing labels while the original IDs stay behind HelpHint.
    await waitFor(() => {
      expect(screen.getByText('performancePage.tools.toolNames.webSearch')).toBeInTheDocument()
    })
    expect(screen.getByText('performancePage.tools.toolNames.fileRead')).toBeInTheDocument()
    expect(screen.queryByText('web.search')).not.toBeInTheDocument()
    expect(screen.queryByText('fs.read')).not.toBeInTheDocument()
  })

  it('shows empty state when no tool calls', async () => {
    getToolStatsMock.mockResolvedValue({ ...sampleStats, byTool: [], total: 0 })
    getToolAccuracyMock.mockResolvedValue({ ...sampleAccuracy, total: 0, ok: 0, accuracy: 0 })

    renderSegment()

    // The test-i18n returns the key as the translation when not predeclared,
    // so we assert against the i18n key (production renders the Korean copy).
    await waitFor(() => {
      expect(
        screen.getByText('performancePage.tools.emptyTitle'),
      ).toBeInTheDocument()
    })
  })

  it('renders a "View traces" link per row that points at /traces with tool filter', async () => {
    getToolStatsMock.mockResolvedValue(sampleStats)
    getToolAccuracyMock.mockResolvedValue(sampleAccuracy)

    renderSegment()

    await waitFor(() => {
      expect(screen.getByText('performancePage.tools.toolNames.webSearch')).toBeInTheDocument()
    })
    const links = screen.getAllByRole('link', {
      name: 'performancePage.tools.viewTracesAction',
    })
    expect(links.length).toBeGreaterThan(0)
    // Highest-traffic tool is web.search so it appears first.
    expect(links[0]).toHaveAttribute(
      'href',
      expect.stringContaining('/traces?tool=web.search'),
    )
  })

  it('shows loading skeletons while fetching', () => {
    getToolStatsMock.mockReturnValue(new Promise(() => {}))
    getToolAccuracyMock.mockReturnValue(new Promise(() => {}))

    renderSegment()

    expect(screen.getByTestId('tools-segment-loading')).toBeInTheDocument()
  })

  it('shows an error region when the stats query rejects', async () => {
    getToolStatsMock.mockRejectedValue(new Error('boom'))
    getToolAccuracyMock.mockResolvedValue(sampleAccuracy)

    renderSegment()

    await waitFor(() => {
      expect(screen.getByTestId('tools-segment-error')).toBeInTheDocument()
    })
  })
})

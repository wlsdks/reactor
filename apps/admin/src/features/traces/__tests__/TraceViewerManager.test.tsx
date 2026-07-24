import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, i18n, render, screen, waitFor } from '../../../test/utils'
import { setAuthToken, removeAuthToken } from '../../../shared/api/client'
import { TraceViewerManager } from '../ui/TraceViewerManager'
import * as tracesApi from '../api'
import type { TraceListItem } from '../types'

vi.mock('../api', () => ({
  listTraces: vi.fn(),
  getTraceSpans: vi.fn(),
  listToolCalls: vi.fn(),
  getToolCallRanking: vi.fn(),
}))

const listTracesMock = vi.mocked(tracesApi.listTraces)

function renderManager() {
  return render(
    <MemoryRouter>
      <TraceViewerManager />
    </MemoryRouter>,
  )
}

function buildTrace(overrides: Partial<TraceListItem> = {}): TraceListItem {
  return {
    traceId: 'trace_001',
    time: Date.now() - 3600000,
    totalDurationMs: 1200,
    spanCount: 5,
    success: true,
    runId: 'run_1',
    ...overrides,
  }
}

describe('TraceViewerManager', () => {
  beforeEach(() => {
    setAuthToken('test-token')
    i18n.addResourceBundle('en', 'translation', {
      'tracesPage.title': 'Execution Traces',
      'tracesPage.description': 'View span timelines, tool calls, and cost analysis for executions.',
      'tracesPage.traceCount': '{{count}} records',
      'tracesPage.stepCount': '{{count}} steps',
      'tracesPage.openLangsmithSync': 'Open LangSmith sync',
      'tracesPage.empty': 'No traces found for the selected filters',
      'tracesPage.unavailableTitle': 'Execution records unavailable',
      'tracesPage.unavailableDescription': 'The current execution records could not be verified.',
      'tracesPage.recoveryGuideTitle': 'Recovery steps',
      'tracesPage.recoveryCheckAccount': 'Check access.',
      'tracesPage.recoveryCheckConnection': 'Check connection.',
      'tracesPage.recoveryRetry': 'Try again.',
      'tracesPage.revalidationTitle': 'Latest execution records need another check',
      'tracesPage.revalidationDescription': 'Showing the last verified records.',
      'tracesPage.filters.statusLabel': 'Filter by status',
      'tracesPage.filters.daysLabel': 'Filter by days',
      'tracesPage.filters.allStatuses': 'All Statuses',
      'tracesPage.filters.error': 'Error',
      'tracesPage.filters.lastNDays': 'Last {{count}} days',
      'tracesPage.stats.totalTraces': 'Total Traces',
      'tracesPage.stats.summaryLabel': 'Trace summary',
      'tracesPage.stats.errorRate': 'Error Rate',
      'tracesPage.stats.avgDuration': 'Avg Duration',
      'tracesPage.stats.p95Duration': 'P95 Duration',
      'tracesPage.helpHints.p95': '95% of executions finish within this duration.',
      'tracesPage.columns.timestamp': 'Timestamp',
      'tracesPage.columns.status': 'Status',
      'tracesPage.columns.runId': 'Run ID',
      'tracesPage.columns.duration': 'Duration',
      'tracesPage.columns.spans': 'Spans',
      'tracesPage.statusLabels.success': 'Success',
      'tracesPage.statusLabels.error': 'Error',
      'tracesPage.statusLabels.partial': 'Partial',
      'tracesPage.statusLabels.timeout': 'Timeout',
      'tracesPage.statusLabels.unknown': 'Unknown',
      'tracesPage.helpHints.spans': 'Spans are the building blocks of a trace.',
      'tracesPage.helpHints.runId': 'Unique identifier for the execution instance.',
      'tracesPage.drawer.title': 'Trace Detail',
      'tracesPage.drawer.summary': 'Summary',
      'tracesPage.drawer.traceId': 'Trace ID',
      'tracesPage.drawer.spanCount': 'Span Count',
      'tracesPage.drawer.duration': 'Duration',
      'common.prev': 'PREV',
      'common.next': 'NEXT',
      'common.noData': 'No data',
      'common.aria.close': 'Close',
    }, true, true)

    listTracesMock.mockResolvedValue([
      buildTrace(),
      buildTrace({ traceId: 'trace_002', success: false }),
    ])
  })

  afterEach(() => {
    vi.clearAllMocks()
    removeAuthToken()
  })

  it('renders a compact trace summary and table after loading', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Timestamp')).toBeInTheDocument()
    })

    expect(screen.getByLabelText('Trace summary')).toBeInTheDocument()
    expect(screen.getByText('Total Traces')).toBeInTheDocument()
    expect(screen.getByText('Error Rate')).toBeInTheDocument()
    expect(screen.getByText('Avg Duration')).toBeInTheDocument()
    expect(screen.getByText('P95 Duration')).toBeInTheDocument()
    expect(document.querySelector('.trace-viewer-stats .stat-card')).not.toBeInTheDocument()
    expect(document.querySelectorAll('.trace-status')).toHaveLength(2)
    expect(document.querySelector('.trace-viewer tbody .badge')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '95% of executions finish within this duration.' })).toBeInTheDocument()
    expect(screen.getAllByText('5 steps')).toHaveLength(2)
  })

  it('keeps release workflow navigation out of the trace analysis header', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Timestamp')).toBeInTheDocument()
    })

    expect(screen.queryByRole('link', { name: /Open LangSmith sync/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
  })

  it('shows empty state when no traces match filters', async () => {
    listTracesMock.mockResolvedValue([])

    renderManager()

    await waitFor(() => {
      expect(screen.getByText('No traces found for the selected filters')).toBeInTheDocument()
    })
  })

  it('keeps the last verified records visible while a filter refresh is pending', async () => {
    listTracesMock.mockResolvedValue([buildTrace()])
    const { container } = renderManager()

    await waitFor(() => {
      expect(screen.getByText('Timestamp')).toBeInTheDocument()
    })

    let resolveFilterRequest: ((value: TraceListItem[]) => void) | undefined
    listTracesMock.mockImplementationOnce(() => new Promise<TraceListItem[]>((resolve) => {
      resolveFilterRequest = resolve
    }))

    fireEvent.change(screen.getByLabelText('Filter by status'), { target: { value: 'error' } })

    await waitFor(() => {
      expect(listTracesMock).toHaveBeenCalledTimes(2)
    })
    expect(screen.getByText('Timestamp')).toBeInTheDocument()
    expect(container.querySelector('.skeleton-table')).not.toBeInTheDocument()

    resolveFilterRequest?.([])
  })

  it('fails closed when the initial execution record request fails', async () => {
    listTracesMock.mockRejectedValue(new Error('Network error'))

    renderManager()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Execution records unavailable')
    })

    expect(screen.queryByLabelText('Trace summary')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Filter by status')).not.toBeInTheDocument()
    expect(document.querySelector('.alert-red')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(listTracesMock).toHaveBeenCalledTimes(2)
  })

  it('computes P95 using nearest-rank formula and renders both avg and P95 values', async () => {
    // 20 traces: 19 at 100ms, 1 at 2000ms.
    // avg = (19*100 + 2000) / 20 = 195ms
    // nearest-rank P95 with ceil(0.95*20)-1 = 18 → sortedDurations[18] = 100ms
    const durations = [
      ...Array.from({ length: 19 }, () => 100),
      2000,
    ]
    listTracesMock.mockResolvedValue(
      durations.map((d, i) =>
        buildTrace({ traceId: `trace_${i}`, totalDurationMs: d }),
      ),
    )

    const { container } = renderManager()

    // Wait until the trace table has rendered (data has loaded).
    await waitFor(() => {
      expect(screen.getByText('Timestamp')).toBeInTheDocument()
    })

    await waitFor(() => {
      const statCards = container.querySelectorAll('.trace-viewer-stats dd')
      const statValues = Array.from(statCards).map((el) => el.textContent)
      // Order: total traces, error rate, avg duration, P95 duration
      expect(statValues[2]).toBe('195ms')
      expect(statValues[3]).toBe('100ms')
    })
  })

  it('renders a heavy-tail distribution without treating it as an application error', async () => {
    const durations = [
      ...Array.from({ length: 19 }, () => 10),
      ...Array.from({ length: 1 }, () => 4000),
    ]
    listTracesMock.mockResolvedValue(
      durations.map((d, i) =>
        buildTrace({ traceId: `trace_${i}`, totalDurationMs: d }),
      ),
    )

    renderManager()

    await waitFor(() => {
      expect(screen.getByText('Timestamp')).toBeInTheDocument()
    })
  })

  it('does not crash on a single trace (edge case)', async () => {
    listTracesMock.mockResolvedValue([
      buildTrace({ traceId: 'solo', totalDurationMs: 500 }),
    ])

    const { container } = renderManager()

    await waitFor(() => {
      expect(screen.getByText('Timestamp')).toBeInTheDocument()
    })

    // For n = 1, both avg and P95 should equal the single data point (500ms).
    // Previously, Math.floor(1 * 0.95) = 0 returned the minimum as P95, which
    // is fine for a single data point but wrong for degenerate cases; the new
    // formula Math.ceil(1 * 0.95) - 1 = 0 also returns index 0, and stays
    // safely clamped into [0, n-1] for any n.
    const statCards = container.querySelectorAll('.trace-viewer-stats dd')
    const statValues = Array.from(statCards).map((el) => el.textContent)
    expect(statValues[2]).toBe('500ms') // avg
    expect(statValues[3]).toBe('500ms') // P95
  })
})

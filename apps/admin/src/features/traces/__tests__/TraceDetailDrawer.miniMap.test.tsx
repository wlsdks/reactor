import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n, render, screen, waitFor } from '../../../test/utils'
import { setAuthToken, removeAuthToken } from '../../../shared/api/client'
import { TraceDetailDrawer } from '../ui/TraceDetailDrawer'
import * as tracesApi from '../api'
import type { TraceSpan } from '../types'

vi.mock('../api', () => ({
  getTraceSpans: vi.fn(),
}))

const getSpansMock = vi.mocked(tracesApi.getTraceSpans)

beforeEach(() => {
  setAuthToken('test-token')
  i18n.addResourceBundle(
    'en',
    'translation',
    {
      'tracesPage.drawer.title': 'Trace Detail',
      'tracesPage.drawer.summary': 'Summary',
      'tracesPage.drawer.traceId': 'Trace ID',
      'tracesPage.drawer.spanCount': 'Span Count',
      'tracesPage.drawer.duration': 'Duration',
      'tracesPage.stepCount': '{{count}} steps',
      'tracesPage.drawer.spanTree': 'Span Tree',
      'tracesPage.drawer.spanDetail': 'Span Detail',
      'tracesPage.drawer.spanTreeAria': 'Span tree',
      'tracesPage.drawer.expand': 'Expand',
      'tracesPage.drawer.collapse': 'Collapse',
      'tracesPage.drawer.statusOk': 'OK',
      'tracesPage.drawer.statusError': 'Error',
      'tracesPage.drawer.errorReason': 'Error reason',
      'common.miniMap.aria': 'Page navigation',
      'common.miniMap.expand': 'Expand TOC',
      'common.miniMap.collapse': 'Collapse TOC',
      'common.modal.closeAriaLabel': 'Close',
    },
    true,
    true,
  )

  const baseTime = Date.now()
  const spans: TraceSpan[] = [
    {
      spanId: 'sp-1',
      parentSpanId: null,
      operationName: 'request',
      serviceName: 'reactor',
      time: baseTime,
      durationMs: 100,
      success: true,
      errorClass: null,
      attributes: {},
    },
    {
      spanId: 'sp-2',
      parentSpanId: 'sp-1',
      operationName: 'llm:call',
      serviceName: 'reactor',
      time: baseTime + 10,
      durationMs: 80,
      success: true,
      errorClass: null,
      attributes: {},
    },
  ]
  getSpansMock.mockResolvedValue(spans)
})

afterEach(() => {
  removeAuthToken()
  vi.clearAllMocks()
})

describe('TraceDetailDrawer information hierarchy', () => {
  it('uses one wide processing-step flow without duplicate timeline navigation', async () => {
    render(
      <TraceDetailDrawer traceId="run_trace001234" open={true} onClose={() => {}} />,
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Span Tree' })).toBeInTheDocument()
    })

    expect(screen.getByRole('heading', { name: 'Summary' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Timeline' })).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Page navigation' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('run_trace001234')).toHaveTextContent('#TRACE001')
    expect(document.body.querySelector('.drawer')).toHaveClass('drawer--wide')
  })
})

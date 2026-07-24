import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { fireEvent, i18n, render, screen } from '../../test/utils'
import { HealthPage } from '../HealthPage'
import { useHealthOperations } from '../../features/health/useHealthOperations'

vi.mock('../../features/health/useHealthOperations', () => ({ useHealthOperations: vi.fn() }))

const refresh = vi.fn()
const evaluateAlerts = vi.fn()
const invalidateCache = vi.fn()

function query<T>(data: T | undefined, options: { isError?: boolean; isLoading?: boolean } = {}) {
  return {
    data,
    isError: options.isError ?? false,
    isLoading: options.isLoading ?? false,
  }
}

describe('HealthPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useHealthOperations).mockReturnValue({
      doctorQuery: query({
        generatedAt: '2026-07-11T13:43:13Z',
        status: 'OK',
        allHealthy: true,
        summary: '3 sections',
        sections: [{ name: 'FastAPI Runtime', status: 'OK', message: 'runtime available', checks: [{ name: 'application', status: 'OK', detail: 'FastAPI router is responding' }] }],
      }) as never,
      platformQuery: query({ pipelineBufferUsage: 0, pipelineDropRate: 0, pipelineWriteLatencyMs: 12, pipelineMetricsAvailable: true, responseCacheEnabled: true, activeAlerts: 0, cacheExactHits: 2, cacheSemanticHits: 1, cacheMisses: 4 }) as never,
      refresh,
      evaluateAlerts,
      invalidateCache,
      actionPending: false,
      actionError: null,
    })
  })

  it('renders backend doctor checks and platform metrics in one workspace', () => {
    i18n.addResourceBundle('en', 'translation', {
      'healthPage.title': 'Health',
      'healthPage.summaryLabel': 'Platform health summary',
      'healthPage.diagnosticsTitle': 'Core diagnostics',
      'healthPage.pipelineTitle': 'Pipeline and cache',
      'healthPage.cacheHits': 'Cache hits',
      'healthPage.alertCount': '{{value}} alerts',
      'healthPage.signals.cacheDetail': 'Fast {{hits}} · source {{misses}}',
      'common.refresh': 'Refresh',
    }, true, true)

    render(<MemoryRouter><HealthPage /></MemoryRouter>)

    expect(screen.getByRole('heading', { level: 1, name: 'Health' })).toBeInTheDocument()
    expect(screen.getByLabelText('Platform health summary')).toBeInTheDocument()
    expect(screen.getByText('서비스 응답')).toBeInTheDocument()
    expect(screen.getByText('관리 화면이 사용하는 서버가 정상적으로 응답합니다.')).toBeInTheDocument()
    expect(screen.getByText('1/1')).toBeInTheDocument()
    expect(screen.queryByText('platformAdminPage.noConnectedServices')).not.toBeInTheDocument()
    expect(screen.queryByText('platformAdminPage.viewRawJson')).not.toBeInTheDocument()
  })

  it('fails closed when both operational APIs fail', () => {
    vi.mocked(useHealthOperations).mockReturnValue({
      doctorQuery: query(undefined, { isError: true }) as never,
      platformQuery: query(undefined, { isError: true }) as never,
      refresh,
      evaluateAlerts,
      invalidateCache,
      actionPending: false,
      actionError: null,
    })

    render(<MemoryRouter><HealthPage /></MemoryRouter>)

    expect(screen.getByRole('alert')).toHaveTextContent('healthPage.loadErrorTitle')
    expect(screen.queryByText('platformAdminPage.healthy')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'common.refresh' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(document.querySelector('.empty-state-icon')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(refresh).toHaveBeenCalledOnce()
  })

  it('shows partial failure without hiding successful doctor diagnostics', () => {
    const current = vi.mocked(useHealthOperations).getMockImplementation()?.()
    vi.mocked(useHealthOperations).mockReturnValue({
      ...current!,
      platformQuery: query(undefined, { isError: true }) as never,
    })

    render(<MemoryRouter><HealthPage /></MemoryRouter>)

    expect(screen.getByText('healthPage.partialErrorTitle')).toBeInTheDocument()
    expect(screen.getByText('서비스 응답')).toBeInTheDocument()
    expect(screen.getByText('healthPage.platformLoadError')).toBeInTheDocument()
    expect(screen.getAllByText('정상').length).toBeGreaterThan(0)
    expect(screen.queryByText('healthPage.unknownSummary')).not.toBeInTheDocument()
  })

  it('does not report an outage or healthy state when diagnostic evidence is empty', () => {
    const current = vi.mocked(useHealthOperations).getMockImplementation()?.()
    vi.mocked(useHealthOperations).mockReturnValue({
      ...current!,
      doctorQuery: query({
        generatedAt: '2026-07-11T13:43:13Z',
        status: 'ERROR',
        allHealthy: false,
        summary: '0 sections',
        sections: [],
      }) as never,
    })

    const { container } = render(<MemoryRouter><HealthPage /></MemoryRouter>)

    expect(screen.getByText('healthPage.statusUnknown')).toBeInTheDocument()
    expect(screen.getByText('healthPage.unknownSummary')).toBeInTheDocument()
    expect(screen.getByText('healthPage.noDiagnostics')).toBeInTheDocument()
    expect(screen.queryByText('healthPage.healthySummary')).not.toBeInTheDocument()
    expect(container.querySelector('.health-summary.is-unknown')).toBeInTheDocument()
    expect(container.querySelector('.empty-state-icon')).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'healthPage.retryStatus' })).toHaveLength(1)
  })

  it('prioritizes failing diagnostics and renders pipeline signals as a status list', () => {
    const current = vi.mocked(useHealthOperations).getMockImplementation()?.()
    vi.mocked(useHealthOperations).mockReturnValue({
      ...current!,
      doctorQuery: query({
        generatedAt: '2026-07-11T13:43:13Z',
        status: 'ERROR',
        allHealthy: false,
        summary: '2 sections',
        sections: [
          { name: 'FastAPI Runtime', status: 'OK', message: 'runtime available', checks: [{ name: 'application', status: 'OK', detail: 'FastAPI router is responding' }] },
          { name: 'Critical Store', status: 'ERROR', message: 'unavailable', checks: [{ name: 'store', status: 'ERROR', detail: 'connection failed' }] },
        ],
      }) as never,
    })

    const { container } = render(<MemoryRouter><HealthPage /></MemoryRouter>)
    const diagnosticHeadings = container.querySelectorAll('.health-diagnostics h3')

    expect(diagnosticHeadings[0]).toHaveTextContent('추가 연결 상태')
    expect(screen.getAllByRole('listitem')).toHaveLength(4)
    expect(screen.getByText('healthPage.cacheHitRate')).toBeInTheDocument()
    expect(container.querySelector('.health-summary.is-error')).toBeInTheDocument()
  })

  it('does not report healthy when dependencies are skipped or unconfigured', () => {
    const current = vi.mocked(useHealthOperations).getMockImplementation()?.()
    vi.mocked(useHealthOperations).mockReturnValue({
      ...current!,
      doctorQuery: query({
        generatedAt: '2026-07-11T13:43:13Z',
        status: 'OK',
        allHealthy: true,
        summary: '3 sections',
        sections: [
          { name: 'FastAPI Runtime', status: 'OK', message: 'runtime available', checks: [{ name: 'application', status: 'OK', detail: 'FastAPI router is responding' }] },
          { name: 'Runtime Settings', status: 'SKIPPED', message: 'not configured', checks: [] },
          { name: 'RAG Store', status: 'SKIPPED', message: 'not configured', checks: [] },
        ],
      }) as never,
    })

    const { container } = render(<MemoryRouter><HealthPage /></MemoryRouter>)

    expect(container.querySelector('.health-summary.is-warn')).toBeInTheDocument()
    expect(screen.getByText('주의')).toBeInTheDocument()
    expect(screen.getByText('1/3')).toBeInTheDocument()
    expect(screen.queryByText('healthPage.healthySummary')).not.toBeInTheDocument()
  })

  it('formats the pipeline drop rate as an operator-readable percentage', () => {
    const current = vi.mocked(useHealthOperations).getMockImplementation()?.()
    vi.mocked(useHealthOperations).mockReturnValue({
      ...current!,
      platformQuery: query({ pipelineBufferUsage: 0.23, pipelineDropRate: 0.001, pipelineWriteLatencyMs: 12, pipelineMetricsAvailable: true, responseCacheEnabled: true, activeAlerts: 1, cacheExactHits: 2, cacheSemanticHits: 1, cacheMisses: 4 }) as never,
    })

    render(<MemoryRouter><HealthPage /></MemoryRouter>)

    expect(screen.getByText('0.1%')).toBeInTheDocument()
  })

  it('does not present placeholder pipeline values as a live operational signal', () => {
    const current = vi.mocked(useHealthOperations).getMockImplementation()?.()
    vi.mocked(useHealthOperations).mockReturnValue({
      ...current!,
      platformQuery: query({
        pipelineBufferUsage: 0.23,
        pipelineDropRate: 0.001,
        pipelineWriteLatencyMs: 12,
        pipelineMetricsAvailable: false,
        responseCacheEnabled: true,
        activeAlerts: 0,
        cacheExactHits: 2,
        cacheSemanticHits: 1,
        cacheMisses: 4,
      }) as never,
    })

    render(<MemoryRouter><HealthPage /></MemoryRouter>)

    expect(screen.getByText('healthPage.pipelineUnavailableTitle')).toBeInTheDocument()
    expect(screen.queryByText('0.23%')).not.toBeInTheDocument()
    expect(screen.queryByText('12ms')).not.toBeInTheDocument()
  })

  it('keeps unrecognized backend diagnostic identifiers out of the primary operator view', () => {
    const current = vi.mocked(useHealthOperations).getMockImplementation()?.()
    vi.mocked(useHealthOperations).mockReturnValue({
      ...current!,
      doctorQuery: query({
        generatedAt: '2026-07-11T13:43:13Z',
        status: 'WARN',
        allHealthy: false,
        summary: '1 section',
        sections: [{
          name: 'queue_recovery_v2',
          status: 'WARN',
          message: 'untrusted-backend-token=do-not-show',
          checks: [{
            name: 'lease_owner',
            status: 'WARN',
            detail: 'untrusted-backend-token=do-not-show',
          }],
        }],
      }) as never,
    })

    render(<MemoryRouter><HealthPage /></MemoryRouter>)

    expect(screen.getByText('추가 연결 상태')).toBeInTheDocument()
    expect(screen.getByText('확인 결과')).toBeInTheDocument()
    expect(screen.queryByText('queue_recovery_v2')).not.toBeInTheDocument()
    expect(screen.queryByText('untrusted-backend-token=do-not-show')).not.toBeInTheDocument()
  })

  it('formats live operational counts without implying a clickable diagnostic action', () => {
    const current = vi.mocked(useHealthOperations).getMockImplementation()?.()
    vi.mocked(useHealthOperations).mockReturnValue({
      ...current!,
      doctorQuery: query({
        generatedAt: '2026-07-11T13:43:13Z',
        status: 'WARN',
        allHealthy: false,
        summary: '1 section',
        sections: [{ name: 'Runtime Settings', status: 'SKIPPED', message: 'not configured', checks: [] }],
      }) as never,
      platformQuery: query({ pipelineBufferUsage: 0, pipelineDropRate: 0, pipelineWriteLatencyMs: 12, pipelineMetricsAvailable: true, responseCacheEnabled: true, activeAlerts: 1200, cacheExactHits: 1600, cacheSemanticHits: 20, cacheMisses: 220 }) as never,
    })

    render(<MemoryRouter><HealthPage /></MemoryRouter>)

    expect(screen.getByText('연결 상태')).toBeInTheDocument()
    expect(screen.getByText('1,200 alerts')).toBeInTheDocument()
    expect(screen.getByText('Fast 1,620 · source 220')).toBeInTheDocument()
  })
})

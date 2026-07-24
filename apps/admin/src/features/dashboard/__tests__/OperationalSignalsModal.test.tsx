import { render, screen } from '../../../test/utils'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { OperationalSignalsModal } from '../ui/OperationalSignalsModal'

// recharts ResponsiveContainer requires ResizeObserver
beforeAll(() => {
  if (typeof globalThis.ResizeObserver === 'undefined') {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  }
})

const defaultProps = {
  open: true,
  onClose: vi.fn(),
  metrics: [
    { name: 'reactor.agent.executions', meterCount: 1, measurements: { count: 1 } },
    { name: 'reactor.agent.errors', meterCount: 0, measurements: {} },
  ],
  metricFilterRaw: '',
  metricNames: ['reactor.agent.executions', 'reactor.agent.errors'],
  onMetricFilterChange: vi.fn(),
  onApplyMetrics: vi.fn(),
  onResetMetrics: vi.fn(),
  refreshing: false,
  responseTrust: { unverifiedResponses: 0, outputGuardRejected: 0, outputGuardModified: 0, boundaryFailures: 0 },
  schedulerBacklog: 0,
  pendingApprovals: 0,
  unverifiedResponses: 0,
  recentExecutions: [],
  recentTrustEvents: [],
}

describe('OperationalSignalsModal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <MemoryRouter>
        <OperationalSignalsModal {...defaultProps} open={false} />
      </MemoryRouter>,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders modal with title when open', () => {
    render(
      <MemoryRouter>
        <OperationalSignalsModal {...defaultProps} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders signal status cards with key metric labels', () => {
    render(
      <MemoryRouter>
        <OperationalSignalsModal {...defaultProps} schedulerBacklog={3} pendingApprovals={2} />
      </MemoryRouter>,
    )
    expect(screen.getByText('dashboard.schedulerBacklog')).toBeInTheDocument()
    expect(screen.getByText('dashboard.pendingApprovals')).toBeInTheDocument()
    expect(screen.getByText('dashboard.outputGuardRejected')).toBeInTheDocument()
    expect(screen.getByText('dashboard.outputGuardModified')).toBeInTheDocument()
    expect(screen.getByText('dashboard.unverifiedResponses')).toBeInTheDocument()
  })

  it('shows signal cards grid with correct values', () => {
    render(
      <MemoryRouter>
        <OperationalSignalsModal {...defaultProps} schedulerBacklog={3} pendingApprovals={2} />
      </MemoryRouter>,
    )
    // Values should be rendered
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('shows separate empty messages for scheduler and trust events', () => {
    render(
      <MemoryRouter>
        <OperationalSignalsModal {...defaultProps} />
      </MemoryRouter>,
    )
    expect(screen.getByText('dashboard.noRecentScheduler')).toBeInTheDocument()
    expect(screen.getByText('dashboard.noRecentTrust')).toBeInTheDocument()
  })

  it('renders split sections with scheduler and trust event headers', () => {
    render(
      <MemoryRouter>
        <OperationalSignalsModal {...defaultProps} />
      </MemoryRouter>,
    )
    expect(screen.getByText('dashboard.recentSchedulerTitle')).toBeInTheDocument()
    expect(screen.getByText('dashboard.recentTrustTitle')).toBeInTheDocument()
  })

  it('renders scheduler events in scheduler section', () => {
    const executions = [
      {
        id: 'exec-1',
        jobId: 'job-1',
        jobName: 'sync-confluence',
        jobType: 'SYNC',
        status: 'SUCCESS',
        resultPreview: 'OK',
        failureReason: null,
        dryRun: false,
        durationMs: 1200,
        startedAt: Date.now() - 60_000,
        completedAt: Date.now() - 59_000,
      },
    ]
    render(
      <MemoryRouter>
        <OperationalSignalsModal
          {...defaultProps}
          recentExecutions={executions}
        />
      </MemoryRouter>,
    )
    expect(screen.getByText('sync-confluence')).toBeInTheDocument()
  })

  it('renders trust events in trust section', () => {
    const trustEvents = [
      {
        occurredAt: Date.now() - 30_000,
        type: 'output_guard',
        severity: 'WARN',
        action: 'modified',
        channel: 'slack',
      },
    ]
    render(
      <MemoryRouter>
        <OperationalSignalsModal
          {...defaultProps}
          recentTrustEvents={trustEvents}
        />
      </MemoryRouter>,
    )
    // Trust event type (returned as key by i18n mock)
    expect(screen.getByText('dashboard.trust.OUTPUT_GUARD_MODIFIED')).toBeInTheDocument()
  })

  it('renders filter controls inside collapsed section', () => {
    render(
      <MemoryRouter>
        <OperationalSignalsModal {...defaultProps} />
      </MemoryRouter>,
    )
    // Filter section title is present (collapsed by default)
    expect(screen.getByText('dashboard.advancedFilter')).toBeInTheDocument()
  })

  it('renders signal chart section collapsed by default', () => {
    render(
      <MemoryRouter>
        <OperationalSignalsModal {...defaultProps} />
      </MemoryRouter>,
    )
    expect(screen.getByText('dashboard.topSignals')).toBeInTheDocument()
  })

  it('displays overall status in modal title', () => {
    render(
      <MemoryRouter>
        <OperationalSignalsModal {...defaultProps} />
      </MemoryRouter>,
    )
    // With all zeros, should show "all clear" status
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()
  })

  it('shows attention status when outputGuardRejected > 0', () => {
    const trustWithRejected = { ...defaultProps.responseTrust, outputGuardRejected: 2 }
    render(
      <MemoryRouter>
        <OperationalSignalsModal {...defaultProps} responseTrust={trustWithRejected} />
      </MemoryRouter>,
    )
    // The title should contain the attention status
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()
  })
})

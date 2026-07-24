import type { ComponentProps } from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor, within, fireEvent } from '../../../test/utils'
import { ModelRegistryManager } from '../ui/ModelRegistryManager'
import * as modelApi from '../api'
import * as platformAdminApi from '../../platform-admin/api'
import * as dashboardApi from '../../dashboard/api'
import {
  RELEASE_PROVIDER_SMOKE_ANCHOR_ID,
} from '../../../shared/releaseWorkflow'
import type { ModelEntry } from '../types'

vi.mock('../api', () => ({
  listModels: vi.fn(),
  runProviderSmoke: vi.fn(),
}))

vi.mock('../../platform-admin/api', () => ({
  listAlertRules: vi.fn(),
}))

vi.mock('../../dashboard/api', () => ({
  getDashboard: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    Link: ({ to, ...props }: ComponentProps<typeof actual.Link>) => (
      <a {...props} href={typeof to === 'string' ? to : String(to)} data-router-link="true" />
    ),
  }
})

const listModelsMock = vi.mocked(modelApi.listModels)
const runProviderSmokeMock = vi.mocked(modelApi.runProviderSmoke)
const listAlertRulesMock = vi.mocked(platformAdminApi.listAlertRules)
const getDashboardMock = vi.mocked(dashboardApi.getDashboard)

function buildModel(overrides: Partial<ModelEntry> = {}): ModelEntry {
  return {
    name: 'gpt-4o',
    inputPricePerMillionTokens: 2.50,
    outputPricePerMillionTokens: 10.00,
    isDefault: true,
    ...overrides,
  }
}

describe('ModelRegistryManager', () => {
  const model1 = buildModel()
  const model2 = buildModel({
    name: 'claude-sonnet-4-20250514',
    inputPricePerMillionTokens: 3.00,
    outputPricePerMillionTokens: 15.00,
    isDefault: false,
  })

  beforeEach(() => {
    listModelsMock.mockResolvedValue([model1, model2])
    listAlertRulesMock.mockResolvedValue([])
    getDashboardMock.mockResolvedValue({
      generatedAt: 0,
      ragEnabled: true,
      mcp: { total: 0, statusCounts: {} },
      scheduler: {
        totalJobs: 0,
        enabledJobs: 0,
        runningJobs: 0,
        failedJobs: 0,
        attentionBacklog: 0,
        agentJobs: 0,
      },
      recentSchedulerExecutions: [],
      approvals: { pendingCount: 0 },
      responseTrust: {
        unverifiedResponses: 0,
        outputGuardRejected: 0,
        outputGuardModified: 0,
        boundaryFailures: 0,
      },
      employeeValue: {
        observedResponses: 0,
        groundedResponses: 0,
        groundedRatePercent: 0,
        blockedResponses: 0,
        interactiveResponses: 0,
        scheduledResponses: 0,
        answerModes: {},
        channels: [],
        lanes: [],
        toolFamilies: [],
        topMissingQueries: [],
      },
      recentTrustEvents: [],
      metrics: [],
      releaseReadiness: {
        status: 'passed',
        syncedAt: '2026-07-10T00:00:00Z',
        items: [
          {
            name: 'provider_smoke',
            status: 'passed',
            mode: 'live_smoke',
            scope: 'backend_provider_integration',
            artifact: 'reports/release-smoke-run.json',
          },
        ],
        tagRecommendation: {
          releaseReadinessCommand: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
        },
        backendProviderIntegration: {
          status: 'verified',
          provider: 'ollama',
          model: 'gemma4:12b',
          requiredChecks: ['required_env', 'tracing_config', 'chat_model_invoke', 'usage_metadata'],
          usageMetadata: {
            source: 'LangChain AIMessage.usage_metadata',
            present: true,
            inputTokens: 20,
            outputTokens: 63,
            totalTokens: 83,
            totalMatchesBreakdown: true,
          },
        },
      },
    })
    // Force wide viewport so provider/context columns render when present.
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      value: 1400,
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders compact model summary without duplicating the page-owned title', async () => {
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0)
    })
    expect(screen.queryByText('modelsPage.title')).not.toBeInTheDocument()
    expect(screen.getByText('modelsPage.totalModels')).toBeInTheDocument()
    expect(screen.getByText('modelsPage.defaultModel')).toBeInTheDocument()
    expect(screen.getByLabelText('modelsPage.summaryLabel')).toBeInTheDocument()
  })

  it('displays the model list before the optional response test', async () => {
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('claude-sonnet-4-20250514')).toBeInTheDocument()
    const table = screen.getByRole('table')
    const responseTest = screen.getByLabelText('modelsPage.providerSmoke.title')
    expect(table.compareDocumentPosition(responseTest) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows pricing columns', async () => {
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('$2.50')).toBeInTheDocument()
    expect(screen.getByText('$10.00')).toBeInTheDocument()
    expect(screen.getByText('$3.00')).toBeInTheDocument()
    expect(screen.getByText('$15.00')).toBeInTheDocument()
  })

  it('shows empty state when no models', async () => {
    listModelsMock.mockResolvedValueOnce([])
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('modelsPage.noModels')).toBeInTheDocument()
    })
  })

  it('does not treat an unavailable model list as an empty registry', async () => {
    listModelsMock.mockRejectedValueOnce(new Error('Model service unavailable'))
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByText('modelsPage.loadErrorTitle')).toBeInTheDocument()
    })
    expect(screen.getByText('modelsPage.loadErrorDescription')).toBeInTheDocument()
    expect(screen.queryByText('modelsPage.noModels')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    const details = document.querySelector('.model-registry__unavailable details')
    expect(details).not.toHaveAttribute('open')
  })

  it('displays the default model as supporting text instead of a badge', async () => {
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0)
    })
    const defaultLabel = screen.getByText('modelsPage.default')
    expect(defaultLabel).toHaveClass('model-default-label')
    expect(defaultLabel).not.toHaveClass('badge')
  })

  it('shows default model name in stat card', async () => {
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0)
    })
    const matches = screen.getAllByText('gpt-4o')
    expect(matches.length).toBe(2) // stat card + table row
  })

  it('opens detail drawer on row click and shows pricing section', async () => {
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0)
    })

    const row = screen.getByText('claude-sonnet-4-20250514').closest('tr') as HTMLElement
    expect(row).not.toBeNull()
    fireEvent.click(row)

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getAllByText('claude-sonnet-4-20250514').length).toBeGreaterThan(0)
    expect(within(dialog).getByText('modelsPage.drawer.pricingSection')).toBeInTheDocument()
    expect(within(dialog).getByText('$3.00')).toBeInTheDocument()
    expect(within(dialog).getByText('$15.00')).toBeInTheDocument()
  })

  it('shows provider column when models report provider on wide viewport', async () => {
    listModelsMock.mockResolvedValueOnce([
      buildModel({ provider: 'openai' }),
      buildModel({ name: 'mistral-large', provider: 'mistral', isDefault: false }),
    ])
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('modelsPage.providerSmoke.providerLabels.openai')).toBeInTheDocument()
    expect(screen.getByText('modelsPage.providerSmoke.providerLabels.unknown')).toBeInTheDocument()
    expect(screen.queryByText('openai')).not.toBeInTheDocument()
    expect(screen.queryByText('mistral')).not.toBeInTheDocument()
  })

  it('keeps provider evidence closed and the everyday response test readable', async () => {
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('modelsPage.providerSmoke.title')).toBeInTheDocument()
    })
    const providerSmoke = screen.getByLabelText('modelsPage.providerSmoke.title')
    expect(document.querySelector(`#${RELEASE_PROVIDER_SMOKE_ANCHOR_ID}`)).toBeInTheDocument()
    expect(providerSmoke.querySelector('.model-provider-smoke__handoff')).not.toBeInTheDocument()
    expect(providerSmoke.querySelector('.model-provider-smoke__workflow')).not.toBeInTheDocument()
    const evidence = providerSmoke.querySelector('.model-provider-smoke__evidence')
    expect(evidence?.tagName).toBe('DETAILS')
    expect(evidence).not.toHaveAttribute('open')
    expect(evidence).toHaveTextContent('modelsPage.providerSmoke.evidenceTitle')
    expect(screen.getByText('modelsPage.providerSmoke.providerLabels.local')).toBeInTheDocument()
    expect(screen.getByText('modelsPage.providerSmoke.modelLabels.gemma')).toBeInTheDocument()
    expect(screen.queryByText('ollama')).not.toBeInTheDocument()
    expect(screen.queryByText('gemma4:12b')).not.toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.localProviderNoKey')).toBeInTheDocument()
    expect(within(providerSmoke).queryByText('OPENAI_API_KEY')).not.toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.gateStatus')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('통과')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.gateReports')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.gateMissingEnv')).toBeInTheDocument()
    expect(within(providerSmoke).getAllByText('modelsPage.providerSmoke.noneMissing').length)
      .toBeGreaterThanOrEqual(2)
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.gateMode')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('실시간 점검')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.gateScope')).toBeInTheDocument()
    expect(within(providerSmoke).getByText(/AI 모델 연결/)).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.gateArtifact')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('reports/release-smoke-run.json')).toBeInTheDocument()
    expect(screen.getByText(
      'modelsPage.providerSmoke.inputTokens: 20, modelsPage.providerSmoke.outputTokens: 63, modelsPage.providerSmoke.totalTokens: 83',
    )).toBeInTheDocument()
    expect(screen.getByText('modelsPage.providerSmoke.usageSourceLabels.recorded')).toBeInTheDocument()
    expect(screen.queryByText('LangChain AIMessage.usage_metadata')).not.toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.usagePresent')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.breakdown')).toBeInTheDocument()
    expect(within(providerSmoke).getAllByText('Yes')).toHaveLength(2)
    expect(screen.getByText('환경 설정, 추적 설정, 모델 호출, 사용량 메타데이터')).toBeInTheDocument()
    expect(screen.getByText('modelsPage.providerSmoke.contract')).toBeInTheDocument()
    expect(screen.getByText('modelsPage.providerSmoke.contractReady')).toBeInTheDocument()
    expect(screen.queryByText('uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json')).not.toBeInTheDocument()
    expect(providerSmoke.querySelector('.status-badge')).not.toBeInTheDocument()
  })

  it('uses a safe label for unrecognized provider evidence values', async () => {
    getDashboardMock.mockResolvedValueOnce({
      releaseReadiness: {
        status: 'unexpected_status',
        items: [{
          name: 'provider_smoke',
          status: 'raw_gate_status',
          mode: 'raw_gate_mode',
          scope: 'raw_gate_scope',
          artifact: 'reports/provider.json',
        }],
        backendProviderIntegration: {
          status: 'raw_integration_status',
          requiredChecks: ['raw_required_check'],
        },
      },
    } as never)

    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)

    const providerSmoke = await screen.findByLabelText('modelsPage.providerSmoke.title')
    expect(within(providerSmoke).getAllByText('modelsPage.providerSmoke.unknownEvidence').length)
      .toBeGreaterThanOrEqual(3)
    expect(within(providerSmoke).queryByText('raw_required_check')).not.toBeInTheDocument()
    expect(within(providerSmoke).queryByText('raw_gate_mode')).not.toBeInTheDocument()
    expect(within(providerSmoke).queryByText('raw_gate_scope')).not.toBeInTheDocument()
  })

  it('runs configured provider smoke and keeps readiness pending until a fresh aggregate exists', async () => {
    runProviderSmokeMock.mockResolvedValue({
      ok: true,
      status: 'passed',
      scope: 'live',
      provider: 'ollama',
      model: 'qwen3:8b',
      evidence: {
        backendProviderIntegration: {
          status: 'verified',
          provider: 'ollama',
          model: 'qwen3:8b',
          requiredChecks: ['chat_model_invoke', 'usage_metadata'],
          usageMetadata: {
            source: 'LangChain AIMessage.usage_metadata',
            present: true,
            inputTokens: 4,
            outputTokens: 2,
            totalTokens: 6,
            totalMatchesBreakdown: true,
          },
        },
      },
      checks: {
        chat_model_invoke: { status: 'passed', content_length: 4 },
        usage_metadata: { status: 'passed' },
      },
    })
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)

    const providerSmoke = await screen.findByLabelText('modelsPage.providerSmoke.title')
    fireEvent.click(within(providerSmoke).getByRole('button', {
      name: 'modelsPage.providerSmoke.runLive',
    }))

    await waitFor(() => {
      expect(runProviderSmokeMock).toHaveBeenCalledTimes(1)
    })
    const liveResult = within(providerSmoke).getByRole('region', {
      name: 'modelsPage.providerSmoke.liveResultTitle',
    })
    expect(liveResult).toHaveTextContent('modelsPage.providerSmoke.providerLabels.local')
    expect(liveResult).toHaveTextContent('modelsPage.providerSmoke.modelLabels.qwen')
    expect(liveResult).toHaveTextContent('4 / 2 / 6')
    expect(liveResult).toHaveTextContent('modelsPage.providerSmoke.usageSourceLabels.recorded')
    expect(liveResult).not.toHaveTextContent('ollama')
    expect(liveResult).not.toHaveTextContent('qwen3:8b')
    expect(liveResult).not.toHaveTextContent('LangChain AIMessage.usage_metadata')
    expect(liveResult).toHaveTextContent('modelsPage.providerSmoke.readinessPending')
  })

  it('keeps the provider smoke release anchor visible when provider evidence is missing', async () => {
    listModelsMock.mockResolvedValueOnce([
      buildModel({
        name: 'gemma4:12b',
        provider: 'ollama',
      }),
    ])
    getDashboardMock.mockResolvedValueOnce({
      generatedAt: 0,
      ragEnabled: true,
      mcp: { total: 0, statusCounts: {} },
      scheduler: {
        totalJobs: 0,
        enabledJobs: 0,
        runningJobs: 0,
        failedJobs: 0,
        attentionBacklog: 0,
        agentJobs: 0,
      },
      recentSchedulerExecutions: [],
      approvals: { pendingCount: 0 },
      responseTrust: {
        unverifiedResponses: 0,
        outputGuardRejected: 0,
        outputGuardModified: 0,
        boundaryFailures: 0,
      },
      employeeValue: {
        observedResponses: 0,
        groundedResponses: 0,
        groundedRatePercent: 0,
        blockedResponses: 0,
        interactiveResponses: 0,
        scheduledResponses: 0,
        answerModes: {},
        channels: [],
        lanes: [],
        toolFamilies: [],
        topMissingQueries: [],
      },
      recentTrustEvents: [],
      metrics: [],
      releaseReadiness: {
        status: 'blocked',
        blockingReports: ['provider_smoke'],
        warningReports: ['backend_provider_integration'],
        tagRecommendation: {
          missingEnv: ['OPENAI_API_KEY'],
          releaseReadinessCommand: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
        },
      },
    })

    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)

    const providerSmoke = await screen.findByLabelText('modelsPage.providerSmoke.title')
    expect(providerSmoke).toHaveAttribute('id', RELEASE_PROVIDER_SMOKE_ANCHOR_ID)
    const evidence = providerSmoke.querySelector('.model-provider-smoke__evidence')
    expect(evidence?.tagName).toBe('DETAILS')
    expect(evidence).not.toHaveAttribute('open')
    expect(within(providerSmoke).getAllByText('modelsPage.providerSmoke.missing').length)
      .toBeGreaterThanOrEqual(1)
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.localProviderNoKey')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.configuredProvider')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.providerLabels.local')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.configuredModel')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.modelLabels.gemma')).toBeInTheDocument()
    expect(within(providerSmoke).queryByText('OPENAI_API_KEY')).not.toBeInTheDocument()
    expect(within(providerSmoke).getByText('AI 모델 응답 시험')).toBeInTheDocument()
    expect(within(providerSmoke).getByText(/AI 모델 연결/)).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.gateMissingEnv')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.noneMissing')).toBeInTheDocument()
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.contractMissing')).toBeInTheDocument()
    const remediation = within(providerSmoke).getByLabelText('modelsPage.providerSmoke.remediationTitle')
    expect(within(remediation).getByText('modelsPage.providerSmoke.remediationDesc')).toBeInTheDocument()
    expect(within(remediation).getByText('modelsPage.providerSmoke.remediationMissing')).toBeInTheDocument()
    expect(within(remediation).getByText('modelsPage.providerSmoke.usage')).toBeInTheDocument()
    expect(within(remediation).queryByRole('link')).not.toBeInTheDocument()
    expect(within(providerSmoke).queryByText('uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json')).not.toBeInTheDocument()
    expect(providerSmoke.querySelector('.model-provider-smoke__workflow')).not.toBeInTheDocument()
  })

  it('keeps release aggregation failure distinct from a completed response test', async () => {
    getDashboardMock.mockRejectedValueOnce(new Error('Readiness service unavailable'))
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)

    const providerSmoke = await screen.findByLabelText('modelsPage.providerSmoke.title')
    expect(within(providerSmoke).getByRole('alert')).toHaveTextContent('modelsPage.providerSmoke.readinessUnavailableTitle')
    expect(within(providerSmoke).getByText('modelsPage.providerSmoke.readinessUnavailableDescription')).toBeInTheDocument()
    expect(within(providerSmoke).queryByRole('button', { name: 'modelsPage.providerSmoke.runLive' })).not.toBeInTheDocument()
    const details = providerSmoke.querySelector('.model-provider-smoke__unavailable details')
    expect(details).not.toHaveAttribute('open')
  })

  it('renders readable capability labels in the drawer', async () => {
    listModelsMock.mockResolvedValueOnce([
      buildModel({ capabilities: ['tools', 'vision', 'streaming'] }),
    ])
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0)
    })
    const matches = screen.getAllByText('gpt-4o')
    const row = matches.map(m => m.closest('tr')).find(el => el !== null) as HTMLElement
    expect(row).toBeTruthy()
    fireEvent.click(row)

    const dialog = await screen.findByRole('dialog')
    const chips = within(dialog).getAllByTestId('model-capability-chip')
    expect(chips).toHaveLength(3)
    expect(chips[0]).toHaveTextContent('modelsPage.drawer.capabilityLabels.tools')
    expect(chips[1]).toHaveTextContent('modelsPage.drawer.capabilityLabels.vision')
    expect(chips[2]).toHaveTextContent('modelsPage.drawer.capabilityLabels.streaming')
  })

  it('shows muted empty state when capabilities are absent', async () => {
    render(<MemoryRouter><ModelRegistryManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getAllByText('gpt-4o').length).toBeGreaterThan(0)
    })
    const matches = screen.getAllByText('gpt-4o')
    const row = matches.map(m => m.closest('tr')).find(el => el !== null) as HTMLElement
    expect(row).toBeTruthy()
    fireEvent.click(row)

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('modelsPage.drawer.noCapabilities')).toBeInTheDocument()
  })
})

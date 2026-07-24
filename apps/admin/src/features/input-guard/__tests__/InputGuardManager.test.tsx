import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { i18n, render, screen, waitFor, fireEvent } from '../../../test/utils'
import {
  RELEASE_WORKFLOW_ANCHOR_PATH,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../../shared/releaseWorkflow'
import { InputGuardManager } from '../ui/InputGuardManager'
import * as inputGuardApi from '../api'
import type { GuardStageConfig, InputGuardPipelineConfig } from '../types'

vi.mock('../api', () => ({
  getPipelineConfig: vi.fn(),
  updateGuardSettings: vi.fn(),
  getStageConfig: vi.fn(),
  listInputGuardRules: vi.fn(),
  getInputGuardStats: vi.fn(),
  listInputGuardAudits: vi.fn(),
}))

const getPipelineMock = vi.mocked(inputGuardApi.getPipelineConfig)
const updateSettingsMock = vi.mocked(inputGuardApi.updateGuardSettings)
const getStageConfigMock = vi.mocked(inputGuardApi.getStageConfig)

function buildStage(overrides: Partial<GuardStageConfig> = {}): GuardStageConfig {
  return {
    name: 'injection-detection',
    order: 3,
    enabled: true,
    className: 'com.example.reactor.guard.InjectionDetectStage',
    runtimeOverride: false,
    ...overrides,
  }
}

const mockPipeline: InputGuardPipelineConfig = {
  stages: [
    buildStage({ name: 'rate-limit', order: 1, className: 'com.example.reactor.guard.RateLimitStage' }),
    buildStage({ name: 'injection-detection', order: 3, className: 'com.example.reactor.guard.InjectionDetectStage' }),
    buildStage({ name: 'llm-classification', order: 5, enabled: false, className: 'com.example.reactor.guard.LlmClassStage', runtimeOverride: true }),
  ],
}

function renderWithRouter() {
  const router = createMemoryRouter(
    [{ path: '/', element: <InputGuardManager /> }],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

function renderEmbeddedWithRouter() {
  const router = createMemoryRouter(
    [{ path: '/', element: <InputGuardManager embedded /> }],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

describe('InputGuardManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'inputGuard.title': 'Input Guard',
      'inputGuard.subtitle': 'Configure the 7-stage input processing pipeline.',
      'inputGuard.pipelineTitle': 'Pipeline Stages',
      'inputGuard.stageConfig.title': 'Tunable parameters',
      'inputGuard.stageConfig.empty': 'This stage exposes no tunable parameters.',
      'inputGuard.className': 'Class',
      'inputGuard.runtimeOverride': 'Runtime Override',
      'inputGuard.technicalDetails': 'Technical details',
      'inputGuard.tabPipeline': 'Pipeline',
      'inputGuard.tabRules': 'Rules',
      'inputGuard.tabStats': 'Stats',
      'inputGuard.tabSimulate': 'Simulate',
      'inputGuard.tabAudit': 'Audit',
      'inputGuard.reorderButton': 'Reorder',
      'common.yes': 'Yes',
      'common.no': 'No',
      'common.releaseWorkflowBacklink': 'Release workflow',
      'common.releaseWorkflowBacklinkStep': 'Release workflow step {{step}}',
      'inputGuard.stages.rate-limit': 'Rate Limit',
      'inputGuard.stages.injection-detection': 'Injection Detection',
      'inputGuard.stages.llm-classification': 'LLM Classification',
      'common.status': 'Status',
      'common.toggle': 'Toggle',
      'common.pipeline': 'Pipeline stages',
      'common.enabled': 'Enabled',
      'common.inactive': 'Disabled',
      'inputGuard.stageCount': '{{count}} stages · {{enabled}} enabled',
      'inputGuard.unavailableTitle': 'Request checks unavailable',
      'inputGuard.unavailableDescription': 'Changes are paused until the current order can be verified.',
      'inputGuard.recoveryTitle': 'How to check',
      'inputGuard.recoveryAccount': 'Check account access.',
      'inputGuard.recoveryConnection': 'Check Reactor status.',
      'common.openStatusPage': 'Open status',
      'common.toast.updated': 'Updated',
      'inputGuard.stageDescriptions.rate-limit': 'Limits the number of requests per minute to prevent abuse.',
      'inputGuard.stageDescriptions.injection-detection': 'Detects prompt injection attempts and blocks malicious inputs.',
      'inputGuard.stageDescriptions.llm-classification': 'Uses an LLM to classify ambiguous or complex inputs.',
    }, true, true)

    getPipelineMock.mockResolvedValue(mockPipeline)
    updateSettingsMock.mockResolvedValue({ updated: 1, note: 'Applied' })
    getStageConfigMock.mockResolvedValue({
      stageName: 'injection-detection',
      className: 'com.example.reactor.guard.InjectionDetectStage',
      enabled: true,
      order: 3,
      config: {},
      note: null,
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders pipeline stages from API', async () => {
    renderWithRouter()

    await waitFor(() => {
      expect(screen.getByText('Rate Limit')).toBeInTheDocument()
    })
    expect(screen.getByText('Injection Detection')).toBeInTheDocument()
    expect(screen.getByText('LLM Classification')).toBeInTheDocument()
  })

  it('renders page title and subtitle', async () => {
    renderWithRouter()

    await waitFor(() => {
      expect(screen.getByText('Input Guard')).toBeInTheDocument()
    })
    expect(screen.getByText(/Configure the 7-stage/)).toBeInTheDocument()
  })

  it('links input guard operations back to the release cockpit step', async () => {
    renderWithRouter()

    await waitFor(() => {
      expect(screen.getByText('Input Guard')).toBeInTheDocument()
    })

    const workflowLink = screen.getByRole('link', { name: 'Release workflow step 1' })
    expect(workflowLink).toHaveAttribute('href', RELEASE_WORKFLOW_ANCHOR_PATH)
    expect(workflowLink).toHaveTextContent(String(RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit))
  })

  it('does not duplicate release navigation when embedded in safety rules', async () => {
    renderEmbeddedWithRouter()

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Pipeline' })).toBeInTheDocument()
    })

    expect(screen.queryByRole('link', { name: 'Release workflow step 1' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Input Guard' })).not.toBeInTheDocument()
  })

  it('renders stage descriptions from i18n keys', async () => {
    renderWithRouter()

    await waitFor(() => {
      expect(screen.getByText('Limits the number of requests per minute to prevent abuse.')).toBeInTheDocument()
    })
    expect(screen.getByText('Detects prompt injection attempts and blocks malicious inputs.')).toBeInTheDocument()
    expect(screen.getByText('Uses an LLM to classify ambiguous or complex inputs.')).toBeInTheDocument()
  })

  it('opens side drawer with stage config when stage is clicked', async () => {
    renderWithRouter()

    await waitFor(() => {
      expect(screen.getByText('Injection Detection')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Injection Detection'))

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    // Should show tunable parameters section heading + className
    expect(screen.getByText('Tunable parameters')).toBeInTheDocument()
    expect(screen.getByText('com.example.reactor.guard.InjectionDetectStage')).toBeInTheDocument()
  })

  it('toggles stage enabled state via settings API', async () => {
    renderWithRouter()

    await waitFor(() => {
      expect(screen.getByText('Rate Limit')).toBeInTheDocument()
    })

    const toggles = screen.getAllByRole('switch')
    expect(toggles.length).toBeGreaterThan(0)

    fireEvent.click(toggles[0])

    await waitFor(() => {
      expect(updateSettingsMock).toHaveBeenCalledWith({
        'guard.stage.rate-limit.enabled': 'false',
      })
    })
  })

  it('fails closed when the current request-check order cannot be verified', async () => {
    getPipelineMock.mockRejectedValueOnce(new Error('HTTP 503'))

    renderWithRouter()

    expect(await screen.findByRole('heading', { name: 'Request checks unavailable' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Reorder' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open status' })).toHaveAttribute('href', '/health')
  })
})

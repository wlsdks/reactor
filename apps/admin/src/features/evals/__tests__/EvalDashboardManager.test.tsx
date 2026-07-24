import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '../../../test/utils'
import { MemoryRouter } from 'react-router-dom'
import { EvalDashboardManager } from '../ui/EvalDashboardManager'
import {
  RELEASE_EVAL_REGRESSION_ANCHOR_ID,
  RELEASE_A2A_PROTOCOL_PATH,
  RELEASE_LANGSMITH_SYNC_ANCHOR_ID,
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_SLACK_GATEWAY_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../../shared/releaseWorkflow'
import * as evalsApi from '../api'
import * as dashboardApi from '../../dashboard/api'
import type { EvalRun, EvalPassRatePoint } from '../types'

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api')
  return {
    ...actual,
    getEvalRuns: vi.fn(),
    getEvalPassRate: vi.fn(),
    getPersistedEvalCases: vi.fn(),
    syncPersistedEvalCases: vi.fn(),
  }
})

vi.mock('../../dashboard/api', () => ({
  getDashboard: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    Link: ({ to, ...props }: React.ComponentProps<typeof actual.Link>) => (
      <a {...props} href={typeof to === 'string' ? to : String(to)} data-router-link="true" />
    ),
  }
})

const getEvalRunsMock = vi.mocked(evalsApi.getEvalRuns)
const getEvalPassRateMock = vi.mocked(evalsApi.getEvalPassRate)
const getPersistedEvalCasesMock = vi.mocked(evalsApi.getPersistedEvalCases)
const syncPersistedEvalCasesMock = vi.mocked(evalsApi.syncPersistedEvalCases)
const getDashboardMock = vi.mocked(dashboardApi.getDashboard)

const mockRuns: EvalRun[] = [
  {
    evalRunId: 'run-1',
    totalCases: 20,
    passCount: 16,
    avgScore: 0.85,
    avgLatencyMs: 1200,
    totalTokens: 45000,
    totalCost: 0.045,
    startedAt: '2026-04-01T10:00:00Z',
    endedAt: '2026-04-01T10:30:00Z',
  },
  {
    evalRunId: 'run-2',
    totalCases: 15,
    passCount: 12,
    avgScore: 0.78,
    avgLatencyMs: 1100,
    totalTokens: 35000,
    totalCost: 0.035,
    startedAt: '2026-04-02T10:00:00Z',
    endedAt: '2026-04-02T10:25:00Z',
  },
]

const mockPassRate: EvalPassRatePoint[] = [
  { day: '2026-04-01', total: 20, passed: 16, avgScore: 0.85 },
  { day: '2026-04-02', total: 15, passed: 12, avgScore: 0.78 },
]

function renderWithRouter(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      {ui}
    </MemoryRouter>,
  )
}

describe('EvalDashboardManager', () => {
  beforeEach(() => {
    getEvalRunsMock.mockResolvedValue(mockRuns)
    getEvalPassRateMock.mockResolvedValue(mockPassRate)
    getPersistedEvalCasesMock.mockResolvedValue([
      {
        id: 'case-1',
        name: 'Case 1',
        enabled: true,
        tags: ['regression'],
        sourceRunId: 'run-1',
        assertionCount: 1,
        updatedAt: '2026-07-10T10:00:00Z',
      },
      {
        id: 'case-rag-weak-answer',
        name: 'RAG weak answer',
        enabled: true,
        tags: ['rag'],
        sourceRunId: 'run-feedback-weak-1',
        assertionCount: 2,
        updatedAt: '2026-07-10T10:05:00Z',
      },
    ])
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
        status: 'eligible_with_warnings',
        requiredReports: ['hardening_suite', 'langsmith_eval_sync'],
        missingReports: [],
        blockingReports: ['langsmith_eval_sync', 'release_readiness', 'backend_provider_integration'],
        readyNextActionIds: ['rerun-release-readiness'],
        nextActionStates: {
          'sync-langsmith': 'blocked',
        },
        items: [
          {
            name: 'langsmith_eval_sync',
            status: 'blocked',
            mode: 'langsmith_dataset_sync',
            scope: 'langsmith_eval_dataset_sync',
            artifact: 'reports/langsmith-eval-sync.json',
            nextActions: [
              {
                id: 'sync-langsmith',
                label: 'Sync promoted feedback cases to LangSmith',
                remediationCommand: 'reactor-langsmith-eval-sync --suite rag-candidates',
              },
              {
                id: 'rerun-release-readiness',
                label: 'Rerun release readiness after LangSmith sync',
                command: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
              },
            ],
          },
        ],
        requiredEnvAnyOf: [['LANGSMITH_API_KEY', 'REACTOR_OBSERVABILITY_LANGSMITH_API_KEY']],
        missingEnvAnyOf: ['LANGSMITH_API_KEY'],
        recommendedEnv: ['LANGSMITH_API_KEY'],
        tagRecommendation: {
          releaseReadinessCommand: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
        },
        productCapabilityBoundary: {
          capability: 'rag_ingest_to_feedback_eval_langsmith_readiness',
          minorEligible: false,
          evidence: [
            'feedback_promotion.reviewed_feedback',
            'langsmith_eval_sync',
            'release_readiness_command',
          ],
          missingEvidence: ['rag_ingestion_lifecycle'],
        },
        feedbackReviewQueue: {
          status: 'passed',
          reviewStatus: 'done',
          reviewNote: 'Weak answer promoted from feedback review.',
          candidateTag: 'rag-candidate:grounded_citation',
          caseIds: ['case-1', 'case-rag-weak-answer'],
          reviewTags: ['promoted', 'langsmith'],
          feedbackRatingCounts: { thumbs_down: 1 },
          feedbackSourceCounts: { slack_button: 1 },
          workflowTagCounts: { rag: 1 },
          expectedCitationCounts: { 'case-1': 2 },
          promotionProvenance: [
            {
              caseId: 'case-rag-weak-answer',
              sourceRunId: 'run-feedback-weak-1',
              runFile: 'reports/runs/run-feedback-weak-1.json',
              caseFile: 'reports/evals/cases/case_rag_weak_answer.json',
              diagnosticsApi: '/admin/rag/candidates/cand-weak-1/diagnostics',
              remediationCommand: 'reactor-langsmith-eval-sync --suite rag-candidates',
              promotionCoverage: {
                requiredContextDiagnostics: true,
                runContextDiagnosticsPresent: true,
                sourceRunIdPresent: true,
              },
              citationMarkerContract: {
                citationMarkersRequired: true,
                citationWorkflowTags: ['rag-candidate:grounded_citation'],
              },
            },
          ],
        },
        langsmithSync: {
          datasetName: 'reactor-release-regression',
          exampleCount: 12,
          caseCount: 12,
          exampleIds: ['example-1', 'example-2'],
          caseIds: ['case-1', 'case-2'],
          metadataCaseIds: ['case-1', 'case-2'],
          splitCounts: { regression: 12 },
          secretFree: true,
          sdkContract: 'Client.create_dataset/create_example',
          sdkContractFields: {
            datasetApi: 'Client.create_dataset',
            exampleApi: 'Client.create_example',
            metadataApi: 'Client.create_example.metadata',
          },
          exampleContract: {
            metadataOnly: true,
            secretScan: 'passed',
            requiredMetadata: ['case_id', 'split', 'source_suite'],
          },
        },
      },
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders a compact summary definition row', async () => {
    const { container } = renderWithRouter(<EvalDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('evalsPage.latestPassRate')).toBeInTheDocument()
      expect(screen.getByText('evalsPage.savedCases')).toBeInTheDocument()
      expect(screen.getByText('evalsPage.recentRuns')).toBeInTheDocument()
      expect(screen.getByText('16 / 20')).toBeInTheDocument()
    })
    expect(container.querySelectorAll('.eval-dashboard-stats .stat-card')).toHaveLength(0)
    expect(container.querySelectorAll('.eval-dashboard-stats > div')).toHaveLength(3)
  })

  it('syncs all enabled persisted cases and marks readiness evidence pending aggregation', async () => {
    syncPersistedEvalCasesMock.mockResolvedValue({
      ok: true,
      status: 'passed',
      scope: 'langsmith_persisted_eval_dataset_sync',
      mode: 'langsmith_dataset_sync',
      datasetName: 'reactor-admin-persisted-eval-cases',
      created: true,
      examples: 2,
      exampleIds: ['example-live-1', 'example-live-2'],
      caseIds: ['case-1', 'case-rag-weak-answer'],
      metadataCaseIds: ['case-1', 'case-rag-weak-answer'],
      sourceRunIds: ['run-1', 'run-feedback-weak-1'],
      caseSourceRunIds: {
        'case-1': 'run-1',
        'case-rag-weak-answer': 'run-feedback-weak-1',
      },
      splitCounts: { regression: 2 },
      secretFree: true,
      exampleContract: { secretScan: 'passed' },
      sdkContract: { datasetApi: 'Client.create_dataset' },
    })
    renderWithRouter(<EvalDashboardManager />)

    const operations = await screen.findByRole('region', {
      name: 'evalsPage.langsmith.operationsTitle',
    })
    expect(operations).toHaveTextContent('evalsPage.langsmith.enabledPersistedCases')
    await waitFor(() => {
      expect(operations).toHaveTextContent('2')
    })

    screen.getByRole('button', { name: 'evalsPage.langsmith.syncAllEnabled' }).click()

    await waitFor(() => {
      expect(syncPersistedEvalCasesMock).toHaveBeenCalledWith('reactor-admin-persisted-eval-cases')
    })
    expect(operations).toHaveTextContent('evalsPage.langsmith.liveSyncPassed')
    expect(operations).toHaveTextContent('example-live-1, example-live-2')
    expect(operations).toHaveTextContent('case-1, case-rag-weak-answer')
    const liveResult = operations.querySelector('details.eval-langsmith-panel__live-result') as HTMLDetailsElement
    expect(liveResult).toBeTruthy()
    expect(liveResult).not.toHaveAttribute('open')
    expect(within(liveResult).getByText('evalsPage.langsmith.liveSyncVerified')).toHaveClass('eval-inline-status')
    expect(operations).toHaveTextContent('evalsPage.langsmith.readinessAggregationPending')
    expect(within(operations).getByRole('link', {
      name: /evalsPage\.langsmith\.openReleaseCockpit/,
    })).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.cockpit)
  })

  it('shows runs table after loading', async () => {
    renderWithRouter(<EvalDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('evalsPage.runHistory')).toBeInTheDocument()
      expect(screen.getByText('evalsPage.runCount')).toBeInTheDocument()
      expect(screen.getAllByText('evalsPage.runLabel')).toHaveLength(2)
      expect(screen.getAllByRole('button', {
        name: 'evalsPage.technicalRunIdDescription',
      })).toHaveLength(2)
      expect(screen.queryByText('run-1')).not.toBeInTheDocument()
      expect(screen.queryByText('run-2')).not.toBeInTheDocument()
    })
  })

  it('shows empty state when no runs', async () => {
    getEvalRunsMock.mockResolvedValueOnce([])
    renderWithRouter(<EvalDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('evalsPage.noExperiments')).toBeInTheDocument()
    })
  })

  it('renders the run-history section title', async () => {
    renderWithRouter(<EvalDashboardManager />)
    await waitFor(() => {
      expect(screen.getByText('evalsPage.runHistory')).toBeInTheDocument()
    })
  })

  it('fails closed when the evaluation run snapshot cannot be loaded', async () => {
    getEvalRunsMock.mockRejectedValueOnce(new Error('HTTP 503'))
    const { container } = renderWithRouter(<EvalDashboardManager />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('evalsPage.unavailableTitle')
      expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    })
    expect(container.querySelector('.eval-dashboard-stats')).not.toBeInTheDocument()
    expect(screen.queryByText('evalsPage.noExperiments')).not.toBeInTheDocument()
  })

  it('explains a denied evaluation snapshot as a permission issue', async () => {
    getEvalRunsMock.mockRejectedValueOnce(new Error('HTTP 403 Forbidden'))
    renderWithRouter(<EvalDashboardManager />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('evalsPage.permissionUnavailableTitle')
      expect(screen.getByRole('alert')).toHaveTextContent('evalsPage.permissionUnavailableDescription')
    })
  })

  it('fails closed when the saved evaluation-case roster cannot be loaded', async () => {
    getPersistedEvalCasesMock.mockRejectedValueOnce(new Error('HTTP 503'))
    const { container } = renderWithRouter(<EvalDashboardManager />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('evalsPage.unavailableTitle')
    })
    expect(container.querySelector('.eval-dashboard-stats')).not.toBeInTheDocument()
  })

  it('collapses secondary run fields into row details on narrow screens', async () => {
    const originalMatchMedia = window.matchMedia
    const originalInnerWidth = window.innerWidth
    const mediaQuery = {
      matches: true,
      media: '(max-width: 900px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      onchange: null,
      dispatchEvent: vi.fn(() => true),
    }
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => mediaQuery),
    })
    Object.defineProperty(window, 'innerWidth', {
      configurable: true,
      value: 560,
    })

    try {
      const { container } = renderWithRouter(<EvalDashboardManager />)
      await screen.findAllByText('evalsPage.runLabel')
      const detailButton = container.querySelector<HTMLButtonElement>('.data-table-expander')
      expect(container.querySelector('.data-table-expander-col')).toBeInTheDocument()
      expect(detailButton).toBeInTheDocument()
      if (detailButton) fireEvent.click(detailButton)
      expect(await screen.findByText('evalsPage.cost')).toBeInTheDocument()
      expect(screen.getByText('evalsPage.startedAt')).toBeInTheDocument()
    } finally {
      Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        value: originalMatchMedia,
      })
      Object.defineProperty(window, 'innerWidth', {
        configurable: true,
        value: originalInnerWidth,
      })
    }
  })

  it('renders summary stats ARIA region', async () => {
    renderWithRouter(<EvalDashboardManager />)
    await waitFor(() => {
      expect(screen.getByRole('region', { name: 'evalsPage.summaryStats' })).toBeInTheDocument()
    })
  })

  it('renders LangSmith sync readiness evidence from release readiness', async () => {
    renderWithRouter(<EvalDashboardManager />)

    await waitFor(() => {
      expect(screen.getByText('reactor-release-regression')).toBeInTheDocument()
    })
    const workflow = screen.getByLabelText('evalsPage.langsmith.workflowLabel')
    expect(workflow).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /evalsPage\.langsmith\.workflowRegression/ }))
      .toHaveAttribute('href', `#${RELEASE_EVAL_REGRESSION_ANCHOR_ID}`)
    expect(screen.getByRole('link', { name: /evalsPage\.langsmith\.workflowSync/ }))
      .toHaveAttribute('href', `#${RELEASE_LANGSMITH_SYNC_ANCHOR_ID}`)
    const workflowReadinessLink = screen.getAllByRole('link', {
      name: /evalsPage\.langsmith\.workflowReadiness/,
    })[0]
    expect(workflowReadinessLink).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.cockpit)
    expect(workflowReadinessLink).toHaveAttribute('data-router-link', 'true')
    const workflowStepNumbers = Array.from(workflow.querySelectorAll('.eval-langsmith-panel__workflow-index'))
      .map((node) => node.textContent)
    expect(workflowStepNumbers).toEqual(['1', '2', '3'])
    expect(screen.getByText('regression: 12')).toBeInTheDocument()
    expect(screen.getByText('evalsPage.langsmith.gateStatus')).toBeInTheDocument()
    expect(screen.getByText('blocked')).toBeInTheDocument()
    expect(screen.getByText('evalsPage.langsmith.gateMode')).toBeInTheDocument()
    expect(screen.getByText('langsmith_dataset_sync')).toBeInTheDocument()
    expect(screen.getByText('evalsPage.langsmith.gateScope')).toBeInTheDocument()
    expect(screen.getByText('langsmith_eval_dataset_sync')).toBeInTheDocument()
    expect(screen.getByText('evalsPage.langsmith.gateArtifact')).toBeInTheDocument()
    expect(screen.getByText('reports/langsmith-eval-sync.json')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'evalsPage.langsmith.title' }))
      .queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' }))
      .not.toBeInTheDocument()
    expect(screen.getByText('Client.create_dataset/create_example')).toBeInTheDocument()
    expect(screen.getByText(/"datasetApi": "Client.create_dataset"/)).toBeInTheDocument()
    expect(screen.getByText(/"secretScan": "passed"/)).toBeInTheDocument()
    expect(screen.getByText(/"requiredMetadata"/)).toBeInTheDocument()
    expect(screen.getByText('example-1, example-2')).toBeInTheDocument()
    expect(screen.getAllByText('case-1, case-2').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('evalsPage.langsmith.syncContract')).toBeInTheDocument()
    expect(screen.getByText('evalsPage.langsmith.contractReady')).toBeInTheDocument()
    const boundaryFlow = within(screen.getByRole('region', { name: 'evalsPage.langsmith.title' }))
      .getByRole('list', { name: 'evalsPage.langsmith.productBoundaryFlow' })
    expect(boundaryFlow).toHaveTextContent('dashboard.release.productBoundaryFlow.ingest')
    expect(boundaryFlow).toHaveTextContent('dashboard.release.productBoundaryFlow.feedback')
    expect(boundaryFlow).toHaveTextContent('dashboard.release.productBoundaryFlow.langsmith')
    expect(boundaryFlow).toHaveTextContent('dashboard.release.productBoundaryFlow.readiness')
    expect(boundaryFlow).toHaveTextContent('dashboard.release.productBoundaryFlow.missing')
    expect(boundaryFlow).toHaveTextContent('dashboard.release.productBoundaryFlow.passed')
    expect(within(boundaryFlow).getByRole('link', {
      name: /dashboard\.release\.productBoundaryFlow\.ingest/,
    })).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.ingest)
    expect(within(boundaryFlow).getByRole('link', {
      name: /dashboard\.release\.productBoundaryFlow\.feedback/,
    })).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.feedback)
    expect(within(boundaryFlow).getByRole('link', {
      name: /dashboard\.release\.productBoundaryFlow\.langsmith/,
    })).toHaveAttribute('href', RELEASE_LANGSMITH_SYNC_PATH)
    expect(within(boundaryFlow).getByRole('link', {
      name: /dashboard\.release\.productBoundaryFlow\.readiness/,
    })).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.cockpit)
    const liveSmokeDisclosure = within(screen.getByRole('region', { name: 'evalsPage.langsmith.title' }))
      .getByRole('group', { name: 'evalsPage.langsmith.liveSmokeChain' })
    expect(liveSmokeDisclosure).toHaveTextContent('evalsPage.langsmith.liveSmokeChain')
    expect(liveSmokeDisclosure).toHaveTextContent('evalsPage.langsmith.liveSmokeChainDesc')
    const liveSmokeChain = within(liveSmokeDisclosure).getByRole('list', {
      name: 'evalsPage.langsmith.liveSmokeChain',
    })
    expect(within(liveSmokeChain).getByRole('link', {
      name: /evalsPage\.langsmith\.liveSmokeLangsmith/,
    })).toHaveAttribute('href', RELEASE_LANGSMITH_SYNC_PATH)
    expect(within(liveSmokeChain).getByRole('link', {
      name: /evalsPage\.langsmith\.liveSmokeSlack/,
    })).toHaveAttribute('href', RELEASE_SLACK_GATEWAY_PATH)
    expect(within(liveSmokeChain).getByRole('link', {
      name: /evalsPage\.langsmith\.liveSmokeA2a/,
    })).toHaveAttribute('href', RELEASE_A2A_PROTOCOL_PATH)
    expect(within(liveSmokeChain).getByRole('link', {
      name: /evalsPage\.langsmith\.liveSmokeProvider/,
    })).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.provider)
    expect(within(liveSmokeChain).getByRole('link', {
      name: /evalsPage\.langsmith\.liveSmokeReadiness/,
    })).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.cockpit)
    expect(liveSmokeChain.querySelectorAll('.eval-langsmith-panel__live-smoke-index')).toHaveLength(0)
    const feedbackCoverage = screen.getByRole('region', {
      name: 'evalsPage.langsmith.feedbackPromotionCoverage',
    })
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackPromotedCases')
    expect(feedbackCoverage).toHaveTextContent('case-1, case-rag-weak-answer')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackReviewStatus')
    expect(feedbackCoverage).toHaveTextContent('done')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackReviewNote')
    expect(feedbackCoverage).toHaveTextContent('Weak answer promoted from feedback review.')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackReviewTags')
    expect(feedbackCoverage).toHaveTextContent('promoted, langsmith')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackExpectedCitations')
    expect(feedbackCoverage).toHaveTextContent('case-1: 2')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackSyncedCases')
    expect(feedbackCoverage).toHaveTextContent('case-1')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackUnsyncedCases')
    expect(feedbackCoverage).toHaveTextContent('case-rag-weak-answer')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackMetadataMissingCases')
    expect(feedbackCoverage).toHaveTextContent('case-rag-weak-answer')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackDiagnosticsCoverage')
    expect(feedbackCoverage).toHaveTextContent('1/1')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackPromotionProvenance')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackSourceRun')
    expect(feedbackCoverage).toHaveTextContent('run-feedback-weak-1')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackRunFile')
    expect(feedbackCoverage).toHaveTextContent('reports/runs/run-feedback-weak-1.json')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackCaseFile')
    expect(feedbackCoverage).toHaveTextContent('reports/evals/cases/case_rag_weak_answer.json')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackDiagnosticsApi')
    expect(feedbackCoverage).toHaveTextContent('/admin/rag/candidates/cand-weak-1/diagnostics')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackRemediationCommand')
    expect(feedbackCoverage).toHaveTextContent('reactor-langsmith-eval-sync --suite rag-candidates')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackPromotionCoverageContract')
    expect(feedbackCoverage)
      .toHaveTextContent('requiredContextDiagnostics: true, runContextDiagnosticsPresent: true, sourceRunIdPresent: true')
    expect(feedbackCoverage).toHaveTextContent('evalsPage.langsmith.feedbackCitationMarkerContract')
    expect(feedbackCoverage)
      .toHaveTextContent('citationMarkersRequired: true, citationWorkflowTags: rag-candidate:grounded_citation')
    expect(within(feedbackCoverage).getAllByRole('link', {
      name: /evalsPage\.langsmith\.openFeedbackPromotion/,
    })[0]).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.feedback)
    const remediation = within(feedbackCoverage).getByRole('region', {
      name: 'evalsPage.langsmith.feedbackSyncRemediation',
    })
    expect(remediation).toHaveTextContent('evalsPage.langsmith.feedbackSyncRemediationDesc')
    expect(remediation).toHaveTextContent('evalsPage.langsmith.feedbackUnsyncedCases')
    expect(remediation).toHaveTextContent('case-rag-weak-answer')
    expect(remediation).toHaveTextContent('evalsPage.langsmith.feedbackMetadataMissingCases')
    expect(within(remediation).getByRole('link', {
      name: /evalsPage\.langsmith\.openFeedbackPromotion/,
    })).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.feedback)
    expect(within(remediation).getByRole('link', {
      name: /evalsPage\.langsmith\.openReleaseCockpit/,
    })).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.cockpit)
    expect(screen.getByRole('region', { name: 'evalsPage.langsmith.title' }))
      .toHaveAttribute('id', RELEASE_EVAL_REGRESSION_ANCHOR_ID)
    expect(document.getElementById(RELEASE_LANGSMITH_SYNC_ANCHOR_ID)).toBeInTheDocument()
    expect(screen.queryByLabelText('evalsPage.langsmith.surfaceLinksLabel')).not.toBeInTheDocument()
    expect(RELEASE_LANGSMITH_SYNC_PATH).toBe(`/evals#${RELEASE_LANGSMITH_SYNC_ANCHOR_ID}`)
    expect(RELEASE_WORKFLOW_PATHS_BY_ID.evals).toBe(`/evals#${RELEASE_EVAL_REGRESSION_ANCHOR_ID}`)
    expect(screen.getAllByText('Hardening Suite').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Langsmith Eval Sync').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('langsmith_eval_sync')).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Open Langsmith Eval Sync' }).length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByRole('link', { name: 'Open Langsmith Eval Sync' })[0]).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
    expect(screen.getAllByRole('link', { name: 'Open Langsmith Eval Sync' })[0]).toHaveAttribute(
      'data-router-link',
      'true',
    )
    expect(screen.getAllByText('LANGSMITH_API_KEY or REACTOR_OBSERVABILITY_LANGSMITH_API_KEY').length)
      .toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('LANGSMITH_API_KEY').length).toBeGreaterThanOrEqual(1)
    const unblockHandoff = screen.getByLabelText('evalsPage.langsmith.unblockHandoff')
    expect(unblockHandoff).toHaveTextContent('evalsPage.langsmith.unblockCredentialGroup')
    expect(unblockHandoff).toHaveTextContent('LANGSMITH_API_KEY or REACTOR_OBSERVABILITY_LANGSMITH_API_KEY')
    expect(unblockHandoff).toHaveTextContent('evalsPage.langsmith.unblockMissingEnv')
    expect(unblockHandoff).toHaveTextContent('LANGSMITH_API_KEY')
    expect(unblockHandoff).toHaveTextContent('evalsPage.langsmith.unblockBlockingReports')
    expect(unblockHandoff).not.toHaveTextContent('langsmith_eval_sync')
    expect(within(unblockHandoff).getAllByRole('link', {
      name: 'Open Langsmith Eval Sync',
    })[0]).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
    expect(within(unblockHandoff).getByRole('link', {
      name: 'Open Release Readiness',
    })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
    )
    expect(within(unblockHandoff).getByRole('link', {
      name: 'Open Backend Provider Integration',
    })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.provider,
    )
    expect(unblockHandoff).toHaveTextContent('evalsPage.langsmith.unblockCommand')
    expect(screen.getAllByText('uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json').length)
      .toBeGreaterThanOrEqual(1)
    expect(within(unblockHandoff).getAllByText('reactor-langsmith-eval-sync --suite rag-candidates').length)
      .toBeGreaterThanOrEqual(2)
    expect(within(unblockHandoff).getByText('evalsPage.langsmith.feedbackRemediationCommand')).toBeInTheDocument()
    expect(unblockHandoff).toHaveTextContent('evalsPage.langsmith.nextActionStates')
    expect(unblockHandoff).toHaveTextContent('sync-langsmith')
    expect(unblockHandoff).toHaveTextContent('evalsPage.langsmith.actionState: blocked')
    expect(unblockHandoff).toHaveTextContent('Sync promoted feedback cases to LangSmith')
    expect(unblockHandoff).toHaveTextContent('rerun-release-readiness')
    expect(unblockHandoff).toHaveTextContent('evalsPage.langsmith.actionState: ready')
    expect(unblockHandoff).toHaveTextContent('Rerun release readiness after LangSmith sync')
    expect(within(unblockHandoff).getAllByRole('link', { name: 'Open Langsmith Eval Sync' }).length)
      .toBeGreaterThanOrEqual(1)
    expect(within(unblockHandoff).getAllByRole('button', { name: 'common.copy.aria' })).toHaveLength(4)
    const readinessLinks = screen.getAllByRole('link', { name: /evalsPage\.langsmith\.openReleaseCockpit/ })
    const commandReadinessLink = readinessLinks[readinessLinks.length - 1]
    expect(commandReadinessLink).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.cockpit)
    expect(commandReadinessLink)
      .toHaveTextContent(`${RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit}evalsPage.langsmith.openReleaseCockpit`)
    expect(screen.getAllByRole('button', { name: 'common.copy.aria' }).length).toBeGreaterThanOrEqual(3)
  })
})

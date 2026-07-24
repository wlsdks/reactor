import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { render, screen, waitFor, fireEvent, i18n } from '../../../test/utils'
import { FeedbackManager } from '../ui/FeedbackManager'
import * as feedbackApi from '../api'
import { getEvalRuns } from '../../evals/api'
import { getDashboard } from '../../dashboard/api'
import {
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_WORKFLOW_GATE_PATHS,
} from '../../../shared/releaseWorkflow'
import { usePageHelpStore } from '../../../shared/lib/usePageHelp'
import type { FeedbackEntry, FeedbackStats, CursorPage } from '../types'

const useRoleVisibilityMock = vi.hoisted(() =>
  vi.fn(() => ({
    role: 'ADMIN' as const,
    effectiveRole: 'ADMIN' as const,
    viewAsManager: false,
    canToggleViewAs: true,
    toggleViewAsManager: vi.fn(),
    isRouteVisible: () => true,
    getVisibleNavGroups: () => [],
  })),
)

vi.mock('../api', () => ({
  listFeedback: vi.fn(),
  getFeedback: vi.fn(),
  deleteFeedback: vi.fn(),
  submitFeedback: vi.fn(),
  exportFeedback: vi.fn(),
  fetchFeedbackStats: vi.fn(),
  fetchUnreviewedCount: vi.fn(),
  updateReview: vi.fn(),
  bulkUpdateReview: vi.fn(),
}))

vi.mock('../../evals/api', () => ({
  getEvalRuns: vi.fn(),
}))

vi.mock('../../dashboard/api', () => ({
  getDashboard: vi.fn(),
}))

vi.mock('../../workspace/RoleVisibilityProvider', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../workspace/RoleVisibilityProvider')>()
  return {
    ...actual,
    useRoleVisibility: useRoleVisibilityMock,
  }
})

const listFeedbackMock = vi.mocked(feedbackApi.listFeedback)
const getFeedbackMock = vi.mocked(feedbackApi.getFeedback)
const fetchFeedbackStatsMock = vi.mocked(feedbackApi.fetchFeedbackStats)
const fetchUnreviewedCountMock = vi.mocked(feedbackApi.fetchUnreviewedCount)
const getEvalRunsMock = vi.mocked(getEvalRuns)
const getDashboardMock = vi.mocked(getDashboard)

function buildEntry(overrides: Partial<FeedbackEntry> = {}): FeedbackEntry {
  return {
    feedbackId: 'fb-1',
    query: 'How do I use this feature?',
    response: 'Navigate to the settings page.',
    rating: 'thumbs_up',
    timestamp: '2024-01-01T10:00:00Z',
    comment: 'Very helpful!',
    runId: 'run-1',
    intent: null,
    domain: null,
    model: 'gpt-4o',
    promptVersion: null,
    toolsUsed: null,
    durationMs: null,
    tags: null,
    templateId: null,
    reviewStatus: 'inbox',
    reviewTags: [],
    reviewedBy: null,
    reviewedAt: null,
    reviewNote: null,
    version: 1,
    updatedAt: '2024-01-01T10:00:00Z',
    ...overrides,
  }
}

function buildPage(items: FeedbackEntry[]): CursorPage<FeedbackEntry> {
  return {
    items,
    nextCursor: null,
    prevCursor: null,
    approximateTotal: items.length,
  }
}

const emptyStats: FeedbackStats = {
  period: { from: '', to: '' },
  total: 0, positive: 0, negative: 0,
  negativeThisPeriod: 0, previousPeriodNegative: 0, negativeChange: 0,
  positiveRate: 0, previousPeriodRate: 0, commentRate: 0,
  byDay: [], topNegativeDomains: [], topNegativeIntents: [], topNegativeTools: [],
  inboxCount: 0, doneCount: 0,
}

describe('FeedbackManager', () => {
  beforeEach(() => {
    useRoleVisibilityMock.mockReturnValue({
      role: 'ADMIN',
      effectiveRole: 'ADMIN',
      viewAsManager: false,
      canToggleViewAs: true,
      toggleViewAsManager: vi.fn(),
      isRouteVisible: () => true,
      getVisibleNavGroups: () => [],
    })
    i18n.addResourceBundle(
      'en',
      'translation',
      {
        'feedbackPage.promotion.title': 'Feedback to eval promotion',
        'feedbackPage.promotion.description': 'Review feedback and promote to regression evidence.',
        'feedbackPage.helpOverlay': [
          'Feedback release starts in the inbox and ends in reviewed/promoted regression evidence.',
          'Weak RAG answers preserve source run, case file, and diagnostics before feedback/eval promotion.',
          'Promoted cases must appear in langsmith_eval_sync caseIds and metadataCaseIds before readiness regeneration.',
          'Slack feedback actions, LangSmith sync, and provider/live smoke close the v1.1 boundary.',
        ],
        'feedbackPage.promotion.summary': 'Feedback/eval promotion checks',
        'feedbackPage.promotion.inbox': 'Inbox',
        'feedbackPage.promotion.reviewed': 'Reviewed',
        'feedbackPage.promotion.latestEvalCases': 'Latest eval cases',
        'feedbackPage.promotion.latestEvalPass': 'Latest pass',
        'feedbackPage.promotion.inboxClosed': 'Inbox closed',
        'feedbackPage.promotion.inboxClosedDesc': '{{count}} inbox items remain.',
        'feedbackPage.promotion.reviewedEvidence': 'Reviewed evidence',
        'feedbackPage.promotion.reviewedEvidenceDesc': '{{count}} feedback items reviewed.',
        'feedbackPage.promotion.evalSuite': 'Eval suite',
        'feedbackPage.promotion.evalSuiteDesc': '{{count}} cases in latest eval run.',
        'feedbackPage.promotion.evalResult': 'Regression result',
        'feedbackPage.promotion.evalResultDesc': '{{pass}}/{{total}} passed, {{failed}} failed.',
        'feedbackPage.promotion.releaseGateEvidence': 'Release gate evidence',
        'feedbackPage.promotion.candidateTag': 'Candidate tag',
        'feedbackPage.promotion.caseIds': 'Eval case ID',
        'feedbackPage.promotion.reviewTags': 'Review tags',
        'feedbackPage.promotion.ratingCounts': 'Rating counts',
        'feedbackPage.promotion.sourceCounts': 'Source counts',
        'feedbackPage.promotion.workflowCounts': 'Workflow tags',
        'feedbackPage.promotion.expectedCitationCounts': 'Expected citations',
        'feedbackPage.promotion.workflowLabel': 'Feedback promotion workflow',
        'feedbackPage.promotion.workflowInbox': 'Review inbox',
        'feedbackPage.promotion.workflowInboxDesc': '{{count}} inbox items remain.',
        'feedbackPage.promotion.workflowReviewed': 'Promote reviewed feedback',
        'feedbackPage.promotion.workflowReviewedDesc': '{{count}} reviewed items connected.',
        'feedbackPage.promotion.workflowEval': 'Regression suite',
        'feedbackPage.promotion.workflowEvalDesc': '{{count}} eval cases in latest run.',
        'feedbackPage.promotion.workflowLangSmith': 'LangSmith sync',
        'feedbackPage.promotion.workflowLangSmithDesc': '{{coverage}} synced cases covered.',
        'feedbackPage.promotion.workflowLiveSmoke': 'Live smoke',
        'feedbackPage.promotion.workflowLiveSmokeDesc': 'Verify Slack and A2A release smoke evidence.',
        'feedbackPage.promotion.workflowProviderSmoke': 'Provider smoke',
        'feedbackPage.promotion.workflowProviderSmokeDesc': 'Verify live provider and usage metadata evidence.',
        'feedbackPage.promotion.workflowReadiness': 'Release readiness',
        'feedbackPage.promotion.workflowReadinessDesc': 'Confirm blockers, warnings, and tag recommendation.',
        'feedbackPage.promotion.boundaryChain': 'Feedback boundary chain',
        'feedbackPage.promotion.boundaryChainDesc': 'RAG candidates, reviewed feedback, eval regression, LangSmith sync, and readiness.',
        'feedbackPage.promotion.boundaryRagCandidates': 'RAG candidates',
        'feedbackPage.promotion.boundaryFeedbackReview': 'Feedback review',
        'feedbackPage.promotion.boundaryEvalRegression': 'Eval regression',
        'feedbackPage.promotion.boundaryLangsmithSync': 'LangSmith sync',
        'feedbackPage.promotion.boundaryReadiness': 'Release readiness',
        'feedbackPage.promotion.handoffQueue': 'Promotion handoff queue',
        'feedbackPage.promotion.handoffQueueDesc': 'Track reviewed feedback into eval cases, LangSmith sync, and readiness regeneration.',
        'feedbackPage.promotion.handoffReviewed': 'Reviewed evidence',
        'feedbackPage.promotion.handoffReviewedDesc': 'Confirm inbox feedback is closed as reviewed promotion evidence.',
        'feedbackPage.promotion.handoffEvalCase': 'Eval case',
        'feedbackPage.promotion.handoffEvalCaseDesc': 'Confirm promoted findings are covered by the regression suite.',
        'feedbackPage.promotion.handoffLangSmith': 'LangSmith sync',
        'feedbackPage.promotion.handoffLangSmithDesc': 'Confirm promoted case IDs and metadata case IDs are synced.',
        'feedbackPage.promotion.handoffReadiness': 'Readiness regeneration',
        'feedbackPage.promotion.handoffReadinessDesc': 'Confirm release readiness is regenerated after sync.',
        'feedbackPage.promotion.handoffEvidence': 'Connected evidence',
        'feedbackPage.promotion.handoffMissing': 'Missing evidence',
        'feedbackPage.promotion.handoffNone': 'None',
        'feedbackPage.promotion.handoffMissingReviewQueue': 'feedbackReviewQueue',
        'feedbackPage.promotion.handoffMissingReviewedFeedback': 'reviewed feedback',
        'feedbackPage.promotion.handoffMissingEvalCase': 'eval case ID',
        'feedbackPage.promotion.handoffMissingEvalRun': 'eval run',
        'feedbackPage.promotion.handoffMissingEvalCases': 'eval cases',
        'feedbackPage.promotion.handoffMissingLangSmithSync': 'langsmith_eval_sync',
        'feedbackPage.promotion.handoffMissingReadiness': 'release readiness',
        'feedbackPage.promotion.handoffMissingReadinessCommand': 'readiness command',
        'feedbackPage.promotion.handoffReadinessStatus': 'readiness status: {{status}}',
        'feedbackPage.releaseHandoff': 'Release handoff',
        'feedbackPage.openFeedbackPromotion': 'Open feedback promotion',
        'feedbackPage.openLangsmithSync': 'Open LangSmith sync',
        'nav.releaseCockpit': 'Release cockpit',
        'feedbackPage.feedbackId': 'Feedback ID',
        'feedbackPage.sourceRun': 'Source run',
        'feedbackPage.candidateTag': 'Candidate tag',
        'feedbackPage.subjectUserId': 'Subject user',
        'feedbackPage.dataset': 'Dataset',
        'feedbackPage.feedbackSource': 'Feedback source',
        'feedbackPage.feedbackTags': 'Feedback tags',
        'feedbackPage.preflightFile': 'Preflight file',
        'feedbackPage.preflightEnvTemplate': 'Preflight env template',
        'feedbackPage.replatformReadinessFile': 'Replatform readiness file',
        'feedbackPage.smokePlanFile': 'Smoke plan file',
        'feedbackPage.releaseEvidenceFile': 'Release evidence file',
        'feedbackPage.readinessFile': 'Readiness file',
        'feedbackPage.reportFile': 'Report file',
        'feedbackPage.caseFile': 'Case file',
        'feedbackPage.runFile': 'Run file',
        'feedbackPage.suiteFile': 'Suite file',
        'feedbackPage.remediationCommand': 'Remediation command',
        'feedbackPage.envFileCommand': 'Env file command',
        'feedbackPage.readinessReportArg': 'Readiness report arg',
        'feedbackPage.requiredReadinessReports': 'Required readiness reports',
        'feedbackPage.readinessReports': 'Readiness reports',
        'feedbackPage.requiredEnvAnyOf': 'Required env any-of',
        'feedbackPage.missingEnvAnyOf': 'Missing env any-of',
        'feedbackPage.recommendedEnv': 'Recommended env',
        'feedbackPage.versionBump': 'Version bump',
        'feedbackPage.tagPattern': 'Tag pattern',
        'feedbackPage.latestTagCommand': 'Latest tag command',
        'feedbackPage.recommendedTagSource': 'Recommended tag source',
        'feedbackPage.minorBoundaryReports': 'Minor boundary reports',
        'feedbackPage.dependsOnActionIds': 'Depends on actions',
        'feedbackPage.evalLifecycle.column': 'Eval stage',
        'feedbackPage.evalLifecycle.bulkCloseBlocked': 'Close after LangSmith sync',
        'feedbackPage.evalLifecycle.bulkDeleteBlocked': 'Delete after LangSmith sync',
        'feedbackPage.evalLifecycle.stage.ready': 'Ready to promote',
        'feedbackPage.evalLifecycle.stage.sync_pending': 'Sync pending',
        'feedbackPage.evalLifecycle.stage.closed': 'Synced',
        'feedbackPage.evalLifecycle.stage.blocked': 'Promotion blocked',
      },
      true,
      true,
    )

    listFeedbackMock.mockResolvedValue(buildPage([
      buildEntry(),
      buildEntry({
        feedbackId: 'fb-2', rating: 'thumbs_down',
        comment: 'Not helpful', query: 'Why is this slow?',
      }),
    ]))
    getFeedbackMock.mockImplementation((id) =>
      Promise.resolve(buildEntry({ feedbackId: id })),
    )
    fetchFeedbackStatsMock.mockResolvedValue(emptyStats)
    fetchUnreviewedCountMock.mockResolvedValue({ count: 0 })
    getEvalRunsMock.mockResolvedValue([])
    getDashboardMock.mockResolvedValue({
      generatedAt: 1700000000000,
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
        feedbackReviewQueue: {
          status: 'passed',
          reviewStatus: 'done',
          reviewNote: 'Promoted to regression eval and reviewed.',
          candidateTag: 'rag-candidate:grounded_citation',
          caseIds: ['case_rag_candidate_grounded_citation'],
          reviewTags: ['promoted', 'langsmith'],
          feedbackRatingCounts: { thumbs_down: 1 },
          feedbackSourceCounts: { slack_button: 1 },
          workflowTagCounts: { rag: 1 },
          expectedCitationCounts: { 'case_rag_candidate_grounded_citation': 2 },
        },
      },
    })
  })

  afterEach(() => vi.clearAllMocks())

  it('registers release feedback page help for the global help overlay', async () => {
    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)

    await waitFor(() => {
      expect(usePageHelpStore.getState().helpKey).toBe('feedbackPage.helpOverlay')
    })

    const help = i18n.t('feedbackPage.helpOverlay', { returnObjects: true }) as string[]
    expect(help).toEqual(expect.arrayContaining([
      expect.stringContaining('feedback/eval promotion'),
      expect.stringContaining('langsmith_eval_sync'),
      expect.stringContaining('provider/live smoke'),
    ]))
  })

  it('renders page title and controls', () => {
    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)
    expect(screen.getByText('Feedback')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument()
  })

  it('hides the release workflow backlink for manager role', () => {
    useRoleVisibilityMock.mockReturnValue({
      role: 'ADMIN_MANAGER',
      effectiveRole: 'ADMIN_MANAGER',
      viewAsManager: false,
      canToggleViewAs: false,
      toggleViewAsManager: vi.fn(),
      isRouteVisible: (path: string) => path !== '/rag-cache',
      getVisibleNavGroups: () => [],
    })

    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)

    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklink' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
  })

  it('shows feedback rows after loading', async () => {
    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('How do I use this feature?')).toBeInTheDocument()
      expect(screen.getByText('Why is this slow?')).toBeInTheDocument()
    })
  })

  it('uses flat definition summaries instead of statistic card tiles', async () => {
    const { container } = render(<MemoryRouter><FeedbackManager /></MemoryRouter>)

    await waitFor(() => {
      expect(container.querySelectorAll('.feedback-stats-summary > div')).toHaveLength(6)
    })
    expect(container.querySelectorAll('.fb-stats-surface .stat-card')).toHaveLength(0)
    expect(container.querySelectorAll('.fb-top-panel')).toHaveLength(3)
  })

  it('humanizes domain and intent identifiers in the feedback table', async () => {
    listFeedbackMock.mockResolvedValue(buildPage([
      buildEntry({ domain: 'project_management', intent: 'jira_create' }),
    ]))

    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)

    expect(await screen.findByText('프로젝트 관리')).not.toHaveAttribute('title')
    expect(screen.getByText('Jira 이슈 만들기')).not.toHaveAttribute('title')
    expect(screen.queryByText('project_management')).not.toBeInTheDocument()
    expect(screen.queryByText('jira_create')).not.toBeInTheDocument()
  })

  it('uses safe labels when feedback classification values are not recognized', async () => {
    listFeedbackMock.mockResolvedValue(buildPage([
      buildEntry({ domain: 'internal_label', intent: 'repair_workflow', reviewTags: ['SYSTEM-ONLY'] }),
    ]))

    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)

    expect(await screen.findByText('feedbackPage.classificationLabels.unknownDomain')).toBeVisible()
    expect(screen.getByText('feedbackPage.classificationLabels.unknownIntent')).toBeVisible()
    expect(screen.getByText('feedbackPage.classificationLabels.unknownTag')).toBeVisible()
    expect(screen.queryByText('internal_label')).not.toBeInTheDocument()
    expect(screen.queryByText('repair_workflow')).not.toBeInTheDocument()
    expect(screen.queryByText('SYSTEM-ONLY')).not.toBeInTheDocument()
  })

  it('reduces the narrow feedback table to one readable question column', async () => {
    const previousWidth = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })

    const { unmount } = render(<MemoryRouter><FeedbackManager /></MemoryRouter>)

    try {
      expect(await screen.findByText('How do I use this feature?', {}, { timeout: 3000 })).toBeVisible()
      expect(screen.getByRole('columnheader', { name: 'Query' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Rating' })).not.toBeInTheDocument()
      expect(screen.getAllByText('feedbackPage.ratingLabels.thumbsUp · feedbackPage.statusLabels.inbox')).not.toHaveLength(0)
    } finally {
      unmount()
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: previousWidth })
      window.dispatchEvent(new Event('resize'))
    }
  })

  it('shows empty state when no feedback exists', async () => {
    listFeedbackMock.mockResolvedValue(buildPage([]))
    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.queryByText('No feedback', { exact: true })).toBeInTheDocument()
    }, { timeout: 3000 })
  })

  it('shows rating and status filter dropdowns', () => {
    const { container } = render(<MemoryRouter><FeedbackManager /></MemoryRouter>)
    // Rating dropdown still exposes thumbs_up/thumbs_down values; the visible
    // label is now driven by i18n (`ratingLabels.thumbsUp/thumbsDown`).
    const ratingSelect = container.querySelector('#fb-rating') as HTMLSelectElement
    expect(ratingSelect).toBeTruthy()
    const values = Array.from(ratingSelect.querySelectorAll('option')).map(o => o.value)
    expect(values).toEqual(expect.arrayContaining(['', 'thumbs_up', 'thumbs_down']))
  })

  it('shows results summary with counts', async () => {
    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText(/2 of 2/)).toBeInTheDocument()
    })
  })

  it('shows feedback to eval promotion readiness', async () => {
    fetchFeedbackStatsMock.mockResolvedValue({
      ...emptyStats,
      inboxCount: 1,
      doneCount: 3,
    })
    getEvalRunsMock.mockResolvedValue([
      {
        evalRunId: 'eval-1',
        totalCases: 5,
        passCount: 4,
        avgScore: 0.82,
        avgLatencyMs: 1000,
        totalTokens: 100,
        totalCost: 0.01,
        startedAt: '2026-07-07T00:00:00Z',
        endedAt: '2026-07-07T00:01:00Z',
      },
    ])
    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByText('Feedback to eval promotion')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('3 reviewed items connected.')).toBeInTheDocument()
    })
    expect(screen.getByText('5 eval cases in latest run.')).toBeInTheDocument()
    expect(screen.getByText('Expected citations')).toBeInTheDocument()
    expect(screen.getByText('case_rag_candidate_grounded_citation: 2')).toBeInTheDocument()
  })

  it('shows filtered empty state with summary chip and clear button when a filter has been applied', async () => {
    // Initial load returns rows so the filter dropdown becomes interactive.
    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('Why is this slow?')).toBeInTheDocument()
    })

    // After the user picks a rating filter, the next list call returns 0 rows.
    listFeedbackMock.mockResolvedValueOnce(buildPage([]))
    const ratingSelect = screen.getByLabelText('Rating') as HTMLSelectElement
    fireEvent.change(ratingSelect, { target: { value: 'thumbs_down' } })

    // Filtered variant — title falls back to the shared filteredTitle key,
    // mono-font summary chip echoes the active filter, and a "Clear filters"
    // button is surfaced as the primary action.
    await waitFor(() => {
      expect(screen.getByText('No items match the filters')).toBeInTheDocument()
    })
    expect(screen.getByText('Rating: thumbs_down')).toBeInTheDocument()
    const clearBtn = screen.getByRole('button', { name: 'Clear filters' })
    expect(clearBtn).toBeInTheDocument()

    // Clicking "Clear filters" resets the rating filter — the next list call
    // returns rows again and the filtered empty state disappears.
    listFeedbackMock.mockResolvedValueOnce(buildPage([
      buildEntry({ feedbackId: 'fb-3', query: 'Cleared and reloaded' }),
    ]))
    fireEvent.click(clearBtn)
    await waitFor(() => {
      expect(ratingSelect.value).toBe('')
    })
  })

  it('opens detail on row click and shows review panel', async () => {
    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('Why is this slow?')).toBeInTheDocument()
    })
    // Click a row
    const row = screen.getByText('Why is this slow?').closest('tr')
    expect(row).toBeTruthy()
    await userEvent.click(row as HTMLTableRowElement)
    await waitFor(() => {
      expect(screen.getByText('Review')).toBeInTheDocument()
    })
  })

  it('shows eval promotion and release readiness handoff in detail', async () => {
    getFeedbackMock.mockResolvedValue(buildEntry({
      feedbackId: 'fb-2',
      rating: 'thumbs_down',
      query: 'Why is this slow?',
      runId: 'run-feedback-2',
      nextActions: [
        {
          id: 'sync-langsmith',
          label: 'Sync the promoted feedback regression case to LangSmith',
          feedbackId: 'fb-2',
          evalCaseId: 'case_rag_candidate_run_feedback_2',
          sourceRunId: 'run-feedback-2',
          candidateTag: 'feedback:fb-2',
          subjectUserId: 'slack-user-1',
          datasetName: 'reactor-release-regression',
          feedbackSource: 'slack',
          feedbackTags: ['thumbs_down', 'missing-citation'],
          preflightFile: 'reports/release-smoke-preflight.json',
          preflightEnvTemplate: 'reports/release-smoke.env.example',
          replatformReadinessFile: 'reports/replatform-readiness.json',
          smokePlanFile: 'reports/release-smoke-plan.json',
          releaseEvidenceFile: 'reports/release-evidence.json',
          reportFile: 'reports/langsmith-eval-sync.json',
          caseFile: 'reports/evals/cases/case_rag_candidate_run_feedback_2.json',
          runFile: 'reports/runs/run-feedback-2.json',
          suiteFile: 'reports/evals/feedback-promotions.json',
          releaseReadinessFile: 'reports/release-readiness.json',
          releaseReadinessCommand: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
          remediationCommand: 'reactor-admin feedback-review fb-2 --status done',
          envFileCommand: 'cp reports/release-smoke.env.example .env.release-smoke',
          readinessReportArg: '--readiness-output reports/release-readiness.json',
          requiredReadinessReports: ['hardening_suite', 'langsmith_eval_sync'],
          readinessReports: {
            hardening_suite: 'reports/hardening-suite.json',
            langsmith_eval_sync: 'reports/langsmith-eval-sync.json',
          },
          requiredEnvAnyOf: [['LANGSMITH_API_KEY', 'REACTOR_OBSERVABILITY_LANGSMITH_API_KEY']],
          missingEnvAnyOf: ['LANGSMITH_API_KEY'],
          recommendedEnv: ['LANGSMITH_API_KEY'],
          recommendedVersionBump: 'minor',
          recommendedTagPattern: 'v1.1.0',
          latestTagCommand: 'git describe --tags --abbrev=0',
          recommendedTagSource: 'release_readiness',
          minorBoundaryReports: ['feedback_promotion', 'langsmith_eval_sync'],
          dependsOnActionIds: ['review-feedback'],
        },
      ],
    }))

    render(<MemoryRouter><FeedbackManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('Why is this slow?')).toBeInTheDocument()
    })
    const row = screen.getByText('Why is this slow?').closest('tr')
    expect(row).toBeTruthy()
    await userEvent.click(row as HTMLTableRowElement)

    await waitFor(() => {
      expect(screen.getByText('Release handoff')).toBeInTheDocument()
    })
    expect(screen.getByText('sync-langsmith')).toBeInTheDocument()
    expect(screen.getByText('case_rag_candidate_run_feedback_2')).toBeInTheDocument()
    expect(screen.getAllByText('fb-2')).not.toHaveLength(0)
    expect(screen.getByText('run-feedback-2')).toBeInTheDocument()
    expect(screen.getByText('feedback:fb-2')).toBeInTheDocument()
    expect(screen.getByText('slack-user-1')).toBeInTheDocument()
    expect(screen.getByText('reactor-release-regression')).toBeInTheDocument()
    expect(screen.getByText('slack')).toBeInTheDocument()
    expect(screen.getByText('thumbs_down, missing-citation')).toBeInTheDocument()
    expect(screen.getByText('reports/release-smoke-preflight.json')).toBeInTheDocument()
    expect(screen.getByText('reports/release-smoke.env.example')).toBeInTheDocument()
    expect(screen.getByText('reports/replatform-readiness.json')).toBeInTheDocument()
    expect(screen.getByText('reports/release-smoke-plan.json')).toBeInTheDocument()
    expect(screen.getByText('reports/release-evidence.json')).toBeInTheDocument()
    expect(screen.getByText('reports/release-readiness.json')).toBeInTheDocument()
    expect(screen.getByText('reports/evals/cases/case_rag_candidate_run_feedback_2.json')).toBeInTheDocument()
    expect(screen.getByText('reports/runs/run-feedback-2.json')).toBeInTheDocument()
    expect(screen.getByText('reports/evals/feedback-promotions.json')).toBeInTheDocument()
    expect(document.querySelectorAll('details.feedback-technical-details')).toHaveLength(2)

    const releaseActionDetails = document.querySelector(
      'details.feedback-technical-details',
    )
    const releaseActionSummary = releaseActionDetails?.querySelector('summary')
    expect(releaseActionSummary).toBeInstanceOf(HTMLElement)
    await userEvent.click(releaseActionSummary as HTMLElement)

    expect(screen.getByText('reactor-admin feedback-review fb-2 --status done')).toBeInTheDocument()
    expect(screen.getByText('cp reports/release-smoke.env.example .env.release-smoke')).toBeInTheDocument()
    expect(screen.getByText('--readiness-output reports/release-readiness.json')).toBeInTheDocument()
    expect(screen.getAllByText('Hardening Suite')).not.toHaveLength(0)
    expect(screen.getByText(/reports\/hardening-suite\.json/)).toBeInTheDocument()
    expect(screen.getAllByText(/reports\/langsmith-eval-sync\.json/)).not.toHaveLength(0)
    expect(screen.getByText('LANGSMITH_API_KEY or REACTOR_OBSERVABILITY_LANGSMITH_API_KEY')).toBeInTheDocument()
    expect(screen.getAllByText('LANGSMITH_API_KEY')).not.toHaveLength(0)
    expect(screen.getByText('minor')).toBeInTheDocument()
    expect(screen.getByText('v1.1.0')).toBeInTheDocument()
    expect(screen.getByText('git describe --tags --abbrev=0')).toBeInTheDocument()
    expect(screen.getByText('release_readiness')).toBeInTheDocument()
    expect(screen.getByRole('link', {
      name: 'Open Feedback promotion',
    })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.feedback,
    )
    const langsmithReportLinks = screen.getAllByRole('link', {
      name: 'Open Langsmith Eval Sync',
    })
    expect(langsmithReportLinks).toHaveLength(3)
    langsmithReportLinks.forEach((link) => {
      expect(link).toHaveAttribute('href', RELEASE_LANGSMITH_SYNC_PATH)
      expect(link).toHaveTextContent('Langsmith Eval Sync')
    })
    expect(screen.getByText('review-feedback')).toBeInTheDocument()
    expect(screen.getByText('uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'common.copy.aria' })).not.toHaveLength(0)
  })

  it('exposes the DataTable bulk-action bar when a row checkbox is selected', async () => {
    const { container } = render(
      <MemoryRouter>
        <FeedbackManager />
      </MemoryRouter>,
    )
    await waitFor(() => {
      expect(screen.getByText('Why is this slow?')).toBeInTheDocument()
    })
    const cb = container.querySelector(
      '.data-table-select-cell input[type="checkbox"]',
    ) as HTMLInputElement
    expect(cb).toBeTruthy()
    fireEvent.click(cb)
    // The shared bulk bar appears with at least the "Mark as done" action.
    await waitFor(() => {
      expect(screen.getByText(/1 selected/)).toBeInTheDocument()
    })
    expect(
      screen.getByRole('button', { name: /Mark as done/i }),
    ).toBeInTheDocument()
  })

  it('shows eval lifecycle state and blocks generic bulk closure before LangSmith sync', async () => {
    listFeedbackMock.mockResolvedValue(buildPage([
      buildEntry({
        feedbackId: 'fb-eval-ready',
        rating: 'thumbs_down',
        query: 'Missing cited policy',
        runId: 'run-rag-1',
        readyNextActionIds: ['promote-eval'],
        blockedNextActionIds: [],
        nextActions: [{ id: 'promote-eval', label: 'Promote', evalCaseId: 'case-rag-1' }],
      }),
    ]))
    const { container } = render(
      <MemoryRouter>
        <FeedbackManager />
      </MemoryRouter>,
    )

    expect(await screen.findByText('Ready to promote')).toBeInTheDocument()
    const checkbox = container.querySelector(
      '.data-table-select-cell input[type="checkbox"]',
    ) as HTMLInputElement
    fireEvent.click(checkbox)

    expect(await screen.findByRole('button', { name: 'Close after LangSmith sync' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Delete after LangSmith sync' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: /Mark as done/i })).not.toBeInTheDocument()
  })
})

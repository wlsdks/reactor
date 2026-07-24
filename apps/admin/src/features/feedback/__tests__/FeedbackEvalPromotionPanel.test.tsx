import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within, i18n } from '../../../test/utils'
import { FeedbackEvalPromotionPanel } from '../ui/FeedbackEvalPromotionPanel'
import * as feedbackApi from '../api'
import { getEvalRuns } from '../../evals/api'
import { getDashboard } from '../../dashboard/api'
import {
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_RAG_CANDIDATES_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../../shared/releaseWorkflow'
import { FEEDBACK_PROMOTION_ANCHORS } from '../releasePromotionAnchors'
import type { FeedbackStats } from '../types'

vi.mock('../api', () => ({
  fetchFeedbackStats: vi.fn(),
}))

vi.mock('../../evals/api', () => ({
  getEvalRuns: vi.fn(),
}))

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

const fetchFeedbackStatsMock = vi.mocked(feedbackApi.fetchFeedbackStats)
const getEvalRunsMock = vi.mocked(getEvalRuns)
const getDashboardMock = vi.mocked(getDashboard)

function buildStats(overrides: Partial<FeedbackStats> = {}): FeedbackStats {
  return {
    period: { from: '', to: '' },
    total: 10,
    positive: 4,
    negative: 6,
    negativeThisPeriod: 6,
    previousPeriodNegative: 2,
    negativeChange: 4,
    positiveRate: 0.4,
    previousPeriodRate: 0.5,
    commentRate: 0.8,
    byDay: [],
    topNegativeDomains: [],
    topNegativeIntents: [],
    topNegativeTools: [],
    inboxCount: 0,
    doneCount: 8,
    ...overrides,
  }
}

describe('FeedbackEvalPromotionPanel', () => {
  beforeEach(() => {
    i18n.addResourceBundle(
      'en',
      'translation',
      {
        'common.readinessPassCount': '{{count}}/{{total}} passing',
        'common.copy.aria': 'Copy {{label}}',
        'feedbackPage.promotion.title': 'Feedback to eval promotion',
        'feedbackPage.promotion.description': 'Review feedback and promote to regression evidence.',
        'feedbackPage.promotion.summary': 'Feedback/eval promotion checks',
        'feedbackPage.promotion.inbox': 'Inbox',
        'feedbackPage.promotion.reviewed': 'Reviewed',
        'feedbackPage.promotion.attentionRequired': 'Needs attention',
        'feedbackPage.promotion.latestEvalCases': 'Latest eval cases',
        'feedbackPage.promotion.latestEvalPass': 'Latest pass',
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
        'feedbackPage.promotion.inboxClosed': 'Inbox closed',
        'feedbackPage.promotion.inboxClosedDesc': '{{count}} inbox items remain.',
        'feedbackPage.promotion.reviewedEvidence': 'Reviewed evidence',
        'feedbackPage.promotion.reviewedEvidenceDesc': '{{count}} feedback items reviewed.',
        'feedbackPage.promotion.evalSuite': 'Eval suite',
        'feedbackPage.promotion.evalSuiteDesc': '{{count}} cases in latest eval run.',
        'feedbackPage.promotion.evalResult': 'Regression result',
        'feedbackPage.promotion.evalResultDesc': '{{pass}}/{{total}} passed, {{failed}} failed.',
        'feedbackPage.promotion.releaseGateEvidence': 'Release gate evidence',
        'feedbackPage.promotion.releaseGateMissing': 'Feedback review evidence is missing from release readiness.',
        'feedbackPage.promotion.productBoundaryFlow': 'Product boundary flow',
        'feedbackPage.promotion.candidateTag': 'Candidate tag',
        'feedbackPage.promotion.openRagCandidates': 'Open RAG candidates',
        'feedbackPage.promotion.caseIds': 'Eval case ID',
        'feedbackPage.promotion.reviewTags': 'Review tags',
        'feedbackPage.promotion.ratingCounts': 'Rating counts',
        'feedbackPage.promotion.sourceCounts': 'Source counts',
        'feedbackPage.promotion.workflowCounts': 'Workflow tags',
        'feedbackPage.promotion.expectedCitationCounts': 'Expected citations',
        'feedbackPage.promotion.langsmithCoverage': 'LangSmith coverage',
        'feedbackPage.promotion.langsmithSyncHandoff': 'LangSmith sync handoff',
        'feedbackPage.promotion.syncedCases': 'Synced cases',
        'feedbackPage.promotion.unsyncedCases': 'Unsynced cases',
        'feedbackPage.promotion.openLangsmithSync': 'Open LangSmith sync',
        'feedbackPage.promotion.readinessCommand': 'Readiness command',
        'feedbackPage.promotion.copyReadinessCommand': 'Readiness command',
        'nav.releaseCockpit': 'Release cockpit',
        'feedbackPage.promotion.langsmithDataset': 'LangSmith dataset',
        'feedbackPage.promotion.langsmithExamples': 'LangSmith examples',
        'feedbackPage.promotion.langsmithMetadataCases': 'Metadata case IDs',
        'feedbackPage.promotion.langsmithMetadataCoverage': 'Metadata coverage',
        'feedbackPage.promotion.langsmithMetadataCoverageDesc': '{{coverage}} promoted cases have LangSmith metadata.',
        'feedbackPage.promotion.langsmithMetadataUnsyncedCases': 'Missing metadata cases',
        'feedbackPage.promotion.langsmithSplitCounts': 'Split counts',
        'feedbackPage.promotion.langsmithSecretScan': 'Secret scan',
        'feedbackPage.promotion.langsmithSdkContract': 'SDK contract',
        'feedbackPage.promotion.promotionProvenance': 'Promotion provenance',
        'feedbackPage.promotion.sourceRun': 'Source run',
        'feedbackPage.promotion.runFile': 'Run file',
        'feedbackPage.promotion.caseFile': 'Case file',
        'feedbackPage.promotion.diagnosticsApi': 'Diagnostics API',
        'feedbackPage.promotion.remediationCommand': 'Remediation command',
        'feedbackPage.promotion.promotionCoverage': 'Promotion coverage',
        'feedbackPage.promotion.citationMarkerContract': 'Citation marker contract',
        'feedbackPage.promotion.secretFree': 'Secret-free',
        'feedbackPage.promotion.secretScanMissing': 'Secret scan missing',
        'feedbackPage.promotion.syncRemediation': 'Sync remediation',
        'feedbackPage.promotion.syncRemediationDesc': 'Promoted feedback cases missing LangSmith sync or metadata block release readiness.',
        'feedbackPage.promotion.syncRemediationMissingCases': 'Missing synced cases',
        'feedbackPage.promotion.syncRemediationMissingMetadata': 'Missing metadata cases',
        'feedbackPage.promotion.syncRemediationCommand': 'Run LangSmith sync, then regenerate readiness.',
        'dashboard.release.productBoundaryFlow.ingest': 'RAG ingest',
        'dashboard.release.productBoundaryFlow.citedAnswer': 'Ask + cited answer',
        'dashboard.release.productBoundaryFlow.feedback': 'Feedback/eval promotion',
        'dashboard.release.productBoundaryFlow.langsmith': 'LangSmith sync',
        'dashboard.release.productBoundaryFlow.slack': 'Slack workspace smoke',
        'dashboard.release.productBoundaryFlow.a2a': 'A2A peer smoke',
        'dashboard.release.productBoundaryFlow.provider': 'Provider smoke',
        'dashboard.release.productBoundaryFlow.readiness': 'Release readiness aggregate',
        'dashboard.release.productBoundaryFlow.passed': 'Evidence linked',
        'dashboard.release.productBoundaryFlow.missing': 'Evidence missing',
      },
      true,
      true,
    )

    fetchFeedbackStatsMock.mockResolvedValue(buildStats())
    getEvalRunsMock.mockResolvedValue([
      {
        evalRunId: 'eval-1',
        totalCases: 12,
        passCount: 12,
        avgScore: 0.91,
        avgLatencyMs: 1200,
        totalTokens: 1000,
        totalCost: 0.05,
        startedAt: '2026-07-07T00:00:00Z',
        endedAt: '2026-07-07T00:01:00Z',
      },
    ])
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
          caseIds: [
            'case_rag_candidate_grounded_citation',
            'case_rag_candidate_weak_answer',
          ],
          reviewTags: ['promoted', 'langsmith'],
          feedbackRatingCounts: { thumbs_down: 1 },
          feedbackSourceCounts: { slack_button: 1 },
          workflowTagCounts: { rag: 1, 'documents-ask': 1 },
          expectedCitationCounts: { 'case_rag_candidate_grounded_citation': 2 },
          promotionProvenance: [
            {
              caseId: 'case_rag_candidate_weak_answer',
              sourceRunId: 'run-feedback-weak-1',
              runFile: 'reports/runs/run-feedback-weak-1.json',
              caseFile: 'reports/evals/cases/case_rag_candidate_weak_answer.json',
              diagnosticsApi: '/admin/rag/candidates/candidate-weak-1/diagnostics',
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
          exampleCount: 2,
          caseIds: ['case_rag_candidate_grounded_citation'],
          exampleIds: ['example-1', 'example-2'],
          metadataCaseIds: ['case_rag_candidate_grounded_citation'],
          splitCounts: { regression: 2 },
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
      },
    })
  })

  afterEach(() => vi.clearAllMocks())

  it('renders reviewed feedback and latest eval run evidence', async () => {
    render(<FeedbackEvalPromotionPanel />)

    await waitFor(() => {
      expect(screen.getByText('Feedback to eval promotion')).toBeInTheDocument()
    })

    const workflow = screen.getByLabelText('Feedback promotion workflow')
    expect(workflow).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Review inbox/i })).toHaveAttribute('href', FEEDBACK_PROMOTION_ANCHORS.panelHref)
    expect(screen.getByRole('link', { name: /Review inbox/i })).not.toHaveAttribute('data-router-link')
    expect(RELEASE_WORKFLOW_PATHS_BY_ID.feedback).toBe(`/feedback${FEEDBACK_PROMOTION_ANCHORS.panelHref}`)
    expect(screen.getByRole('link', { name: /Promote reviewed feedback/i })).toHaveAttribute('href', FEEDBACK_PROMOTION_ANCHORS.releaseEvidenceHref)
    expect(screen.getByRole('link', { name: /Promote reviewed feedback/i })).not.toHaveAttribute('data-router-link')
    expect(screen.getByRole('link', { name: /Regression suite/i })).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.evals)
    expect(screen.getByRole('link', { name: /Regression suite/i })).toHaveAttribute('data-router-link', 'true')
    const workflowStepNumbers = Array.from(workflow.querySelectorAll('.fb-promotion-panel__workflow-index'))
      .map((node) => node.textContent)
    expect(workflowStepNumbers).toEqual(['1', '2', '3'])
    expect(within(workflow).getByText('0 inbox items remain.')).toBeInTheDocument()
    expect(within(workflow).getByText('8 reviewed items connected.')).toBeInTheDocument()
    expect(within(workflow).getByText('12 eval cases in latest run.')).toBeInTheDocument()
    expect(within(workflow).queryByRole('link', { name: /LangSmith sync/i })).not.toBeInTheDocument()
    const boundaryChain = screen.getByLabelText('Feedback boundary chain')
    expect(boundaryChain).toHaveTextContent('Feedback boundary chain')
    expect(boundaryChain).toHaveTextContent('RAG candidates, reviewed feedback, eval regression, LangSmith sync, and readiness.')
    expect(within(boundaryChain).getByRole('link', { name: /RAG candidates/i })).toHaveAttribute(
      'href',
      RELEASE_RAG_CANDIDATES_PATH,
    )
    expect(within(boundaryChain).getByRole('link', { name: /Feedback review/i })).toHaveAttribute(
      'href',
      FEEDBACK_PROMOTION_ANCHORS.panelHref,
    )
    expect(within(boundaryChain).getByRole('link', { name: /Eval regression/i })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.evals,
    )
    expect(within(boundaryChain).getByRole('link', { name: /LangSmith sync/i })).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
    expect(within(boundaryChain).getByRole('link', { name: /Release readiness/i })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
    )
    const handoffQueue = screen.getByLabelText('Promotion handoff queue')
    expect(handoffQueue).toHaveTextContent('Track reviewed feedback into eval cases, LangSmith sync, and readiness regeneration.')
    expect(within(handoffQueue).getByRole('link', { name: /Reviewed evidence/i })).toHaveAttribute(
      'href',
      FEEDBACK_PROMOTION_ANCHORS.releaseEvidenceHref,
    )
    expect(within(handoffQueue).getByRole('link', { name: /Eval case/i })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.evals,
    )
    expect(within(handoffQueue).getByRole('link', { name: /LangSmith sync/i })).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
    expect(within(handoffQueue).getByRole('link', { name: /Readiness regeneration/i })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
    )
    expect(handoffQueue).toHaveTextContent('8 feedback items reviewed.')
    expect(handoffQueue).toHaveTextContent('case_rag_candidate_grounded_citation, case_rag_candidate_weak_answer')
    expect(handoffQueue).toHaveTextContent('promoted, langsmith')
    expect(handoffQueue).toHaveTextContent('12 cases in latest eval run.')
    expect(handoffQueue).toHaveTextContent('eval-1')
    expect(handoffQueue).toHaveTextContent('1/2 synced cases covered.')
    expect(handoffQueue).toHaveTextContent('reactor-release-regression')
    expect(handoffQueue).toHaveTextContent('1/2 promoted cases have LangSmith metadata.')
    expect(handoffQueue).toHaveTextContent('Client.create_dataset/create_example')
    expect(handoffQueue).toHaveTextContent('Missing synced cases: case_rag_candidate_weak_answer')
    expect(handoffQueue).toHaveTextContent('Missing metadata cases: case_rag_candidate_weak_answer')
    expect(handoffQueue).toHaveTextContent('readiness status: passed')
    expect(handoffQueue).toHaveTextContent('uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json')
    expect(within(handoffQueue).getAllByText('None').length).toBeGreaterThanOrEqual(2)
    const releaseEvidence = screen.getByLabelText('Release gate evidence')
    expect(releaseEvidence).toBeInTheDocument()
    expect(releaseEvidence).not.toHaveAttribute('open')
    fireEvent.click(releaseEvidence.querySelector('summary')!)
    expect(releaseEvidence).toHaveAttribute('open')
    expect(within(releaseEvidence).queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' }))
      .not.toBeInTheDocument()
    expect(screen.getByText('Promoted to regression eval and reviewed.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open RAG candidates/i })).toHaveAttribute(
      'href',
      RELEASE_RAG_CANDIDATES_PATH,
    )
    expect(screen.getByRole('link', { name: /Open RAG candidates/i })).toHaveAttribute('data-router-link', 'true')
    expect(screen.getByText('case_rag_candidate_grounded_citation, case_rag_candidate_weak_answer')).toBeInTheDocument()
    expect(screen.getByText('promoted, langsmith')).toBeInTheDocument()
    expect(screen.getByText('thumbs_down: 1')).toBeInTheDocument()
    expect(screen.getByText('slack_button: 1')).toBeInTheDocument()
    expect(screen.getByText('Expected citations')).toBeInTheDocument()
    expect(screen.getByText('case_rag_candidate_grounded_citation: 2')).toBeInTheDocument()
    expect(screen.getByText('LangSmith coverage')).toBeInTheDocument()
    expect(screen.getByText('1/2')).toBeInTheDocument()
    const boundaryFlow = within(releaseEvidence).getByRole('list', { name: 'Product boundary flow' })
    expect(boundaryFlow).toHaveTextContent('RAG ingest')
    expect(boundaryFlow).toHaveTextContent('Feedback/eval promotion')
    expect(boundaryFlow).toHaveTextContent('LangSmith sync')
    expect(boundaryFlow).toHaveTextContent('Release readiness aggregate')
    expect(within(boundaryFlow).getByRole('link', { name: /RAG ingest/ })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
    )
    expect(within(boundaryFlow).getByRole('link', { name: /Feedback\/eval promotion/ })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.feedback,
    )
    expect(within(boundaryFlow).getByRole('link', { name: /LangSmith sync/ })).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
    const handoff = screen.getByLabelText('LangSmith sync handoff')
    expect(within(handoff).getByText('Synced cases')).toBeInTheDocument()
    expect(within(handoff).getAllByText('case_rag_candidate_grounded_citation')).toHaveLength(2)
    expect(within(handoff).getByText('Unsynced cases')).toBeInTheDocument()
    expect(within(handoff).getAllByText('case_rag_candidate_weak_answer').length).toBeGreaterThanOrEqual(2)
    expect(within(handoff).getByText('LangSmith dataset')).toBeInTheDocument()
    expect(within(handoff).getByText('reactor-release-regression')).toBeInTheDocument()
    expect(within(handoff).getByText('LangSmith examples')).toBeInTheDocument()
    expect(within(handoff).getByText('2 / example-1, example-2')).toBeInTheDocument()
    expect(within(handoff).getByText('Metadata case IDs')).toBeInTheDocument()
    expect(within(handoff).getByText('Metadata coverage')).toBeInTheDocument()
    expect(within(handoff).getByText('1/2 promoted cases have LangSmith metadata.')).toBeInTheDocument()
    expect(within(handoff).getAllByText('Missing metadata cases').length).toBeGreaterThanOrEqual(1)
    expect(within(handoff).getByText('Split counts')).toBeInTheDocument()
    expect(within(handoff).getByText('regression: 2')).toBeInTheDocument()
    expect(within(handoff).getByText('Secret scan')).toBeInTheDocument()
    expect(within(handoff).getByText('Secret-free')).toBeInTheDocument()
    expect(within(handoff).getByText('SDK contract')).toBeInTheDocument()
    expect(within(handoff).getByText('Client.create_dataset/create_example')).toBeInTheDocument()
    expect(within(handoff).getByText('Promotion provenance')).toBeInTheDocument()
    expect(within(handoff).getByText('Source run')).toBeInTheDocument()
    expect(within(handoff).getByText('run-feedback-weak-1')).toBeInTheDocument()
    expect(within(handoff).getByText('Run file')).toBeInTheDocument()
    expect(within(handoff).getByText('reports/runs/run-feedback-weak-1.json')).toBeInTheDocument()
    expect(within(handoff).getByText('Case file')).toBeInTheDocument()
    expect(within(handoff).getByText('reports/evals/cases/case_rag_candidate_weak_answer.json')).toBeInTheDocument()
    expect(within(handoff).getByText('Diagnostics API')).toBeInTheDocument()
    expect(within(handoff).getByText('/admin/rag/candidates/candidate-weak-1/diagnostics')).toBeInTheDocument()
    expect(within(handoff).getByText('Remediation command')).toBeInTheDocument()
    const provenance = within(handoff).getByText('Promotion provenance').closest('div')
    expect(provenance).toBeTruthy()
    expect(within(provenance as HTMLElement).getByText('reactor-langsmith-eval-sync --suite rag-candidates')).toBeInTheDocument()
    expect(within(handoff).getByText('Promotion coverage')).toBeInTheDocument()
    expect(
      within(handoff).getByText(
        'requiredContextDiagnostics: true, runContextDiagnosticsPresent: true, sourceRunIdPresent: true',
      ),
    ).toBeInTheDocument()
    expect(within(handoff).getByText('Citation marker contract')).toBeInTheDocument()
    expect(
      within(handoff).getByText('citationMarkersRequired: true, citationWorkflowTags: rag-candidate:grounded_citation'),
    ).toBeInTheDocument()
    const langsmithSyncLinks = within(handoff).getAllByRole('link', { name: /Open LangSmith sync/i })
    expect(langsmithSyncLinks).toHaveLength(2)
    expect(langsmithSyncLinks[0]).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
    expect(langsmithSyncLinks[0]).toHaveAttribute('data-router-link', 'true')
    expect(langsmithSyncLinks[0]).toHaveTextContent(
      `${RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals}Open LangSmith sync`,
    )
    expect(within(handoff).getAllByText('Readiness command').length).toBeGreaterThanOrEqual(1)
    expect(within(handoff).getByRole('link', { name: /Release cockpit/i })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
    )
    expect(within(handoff).getByRole('link', { name: /Release cockpit/i }))
      .toHaveTextContent(`${RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit}Release cockpit`)
    expect(within(handoff).getByText('uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json')).toBeInTheDocument()
    expect(within(handoff).getByRole('button', { name: /Copy Readiness command/i })).toBeInTheDocument()
    const remediation = within(handoff).getByLabelText('Sync remediation')
    expect(remediation).toHaveTextContent('Promoted feedback cases missing LangSmith sync or metadata block release readiness.')
    expect(within(remediation).getByText('Missing synced cases')).toBeInTheDocument()
    expect(within(remediation).getByText('Missing metadata cases')).toBeInTheDocument()
    expect(within(remediation).getAllByText('case_rag_candidate_weak_answer')).toHaveLength(2)
    expect(within(remediation).getByText('Run LangSmith sync, then regenerate readiness.')).toBeInTheDocument()
    expect(within(remediation).getByRole('link', { name: /Open LangSmith sync/i })).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
    expect(within(remediation).getByText('reactor-langsmith-eval-sync --suite rag-candidates')).toBeInTheDocument()
    expect(within(remediation).getByRole('button', {
      name: /Copy Run LangSmith sync, then regenerate readiness./i,
    })).toBeInTheDocument()
  })

  it('leaves release workflow navigation to the page header', async () => {
    render(<FeedbackEvalPromotionPanel />)

    await waitFor(() => {
      expect(screen.getByText('Feedback to eval promotion')).toBeInTheDocument()
    })

    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' }))
      .not.toBeInTheDocument()
  })

  it('keeps LangSmith workflow warning when synced cases lack metadata coverage', async () => {
    getDashboardMock.mockResolvedValueOnce({
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
        status: 'blocked',
        feedbackReviewQueue: {
          status: 'passed',
          reviewStatus: 'done',
          caseIds: [
            'case_rag_candidate_grounded_citation',
            'case_rag_candidate_weak_answer',
          ],
        },
        langsmithSync: {
          datasetName: 'reactor-release-regression',
          exampleCount: 2,
          caseCount: 2,
          caseIds: [
            'case_rag_candidate_grounded_citation',
            'case_rag_candidate_weak_answer',
          ],
          exampleIds: ['example-1', 'example-2'],
          metadataCaseIds: ['case_rag_candidate_grounded_citation'],
          splitCounts: { regression: 2 },
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

    render(<FeedbackEvalPromotionPanel />)

    await waitFor(() => {
      expect(screen.getByText('Feedback to eval promotion')).toBeInTheDocument()
    })

    const remediation = screen.getByLabelText('Sync remediation')
    expect(within(remediation).getByText('Missing metadata cases')).toBeInTheDocument()
    expect(within(remediation).getByText('case_rag_candidate_weak_answer')).toBeInTheDocument()
    const handoffQueue = screen.getByLabelText('Promotion handoff queue')
    expect(handoffQueue).toHaveTextContent('Missing metadata cases: case_rag_candidate_weak_answer')
  })

  it('surfaces a failed eval-suite check when no eval run exists', async () => {
    getEvalRunsMock.mockResolvedValue([])
    render(<FeedbackEvalPromotionPanel />)

    await waitFor(() => {
      expect(screen.getAllByText('0 cases in latest eval run.').length).toBeGreaterThanOrEqual(1)
    })

    expect(screen.getAllByText('FAIL').length).toBeGreaterThanOrEqual(1)
    const handoffQueue = screen.getByLabelText('Promotion handoff queue')
    expect(handoffQueue).toHaveTextContent('eval run')
    expect(handoffQueue).toHaveTextContent('eval cases')
  })

  it('keeps release and LangSmith handoff visible when readiness evidence is missing', async () => {
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
        status: 'blocked',
        tagRecommendation: {
          releaseReadinessCommand: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
        },
      },
    })

    render(<FeedbackEvalPromotionPanel />)

    await waitFor(() => {
      expect(screen.getByLabelText('Release gate evidence')).toBeInTheDocument()
    })

    expect(screen.getByText('Feedback review evidence is missing from release readiness.')).toBeInTheDocument()
    const handoff = screen.getByLabelText('LangSmith sync handoff')
    expect(within(handoff).getByText('Synced cases')).toBeInTheDocument()
    expect(within(handoff).getByText('Unsynced cases')).toBeInTheDocument()
    expect(within(handoff).getByRole('link', { name: /Open LangSmith sync/i })).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
    expect(within(handoff).getByRole('link', { name: /Open LangSmith sync/i })).toHaveTextContent(
      `${RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals}Open LangSmith sync`,
    )
    expect(within(handoff).getAllByText('Readiness command').length).toBeGreaterThanOrEqual(1)
    expect(within(handoff).getByRole('link', { name: /Release cockpit/i })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
    )
    expect(within(handoff).getByRole('link', { name: /Release cockpit/i }))
      .toHaveTextContent(`${RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit}Release cockpit`)
    expect(within(handoff).getByText('uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json')).toBeInTheDocument()
    const handoffQueue = screen.getByLabelText('Promotion handoff queue')
    expect(handoffQueue).toHaveTextContent('feedbackReviewQueue')
    expect(handoffQueue).toHaveTextContent('langsmith_eval_sync')
    expect(handoffQueue).toHaveTextContent('readiness status: blocked')
  })
})

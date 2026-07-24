import { createMemoryRouter, RouterProvider, useLocation } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within, i18n, fireEvent } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { RagCacheManager } from '../ui/RagCacheManager'
import * as ragCacheApi from '../api'
import * as dashboardApi from '../../dashboard/api'
import {
  RELEASE_RAG_ANSWER_CONTRACT_ANCHOR_ID,
  RELEASE_WORKFLOW_PATHS_BY_ID,
} from '../../../shared/releaseWorkflow'
import type { CacheStats, VectorStoreStats, RagPolicyState } from '../types'

vi.mock('../api', () => ({
  getCacheStats: vi.fn(),
  invalidateCache: vi.fn(),
  getVectorStoreStats: vi.fn(),
  getRagPolicy: vi.fn(),
  updateRagPolicy: vi.fn(),
  resetRagPolicy: vi.fn(),
  searchDocuments: vi.fn(),
  listRagCandidates: vi.fn(),
  approveRagCandidate: vi.fn(),
  rejectRagCandidate: vi.fn(),
  getRagStatusStats: vi.fn(),
  getRagChannelStats: vi.fn(),
  askGroundedRag: vi.fn(),
  promoteWeakRagAnswer: vi.fn(),
}))

vi.mock('../../dashboard/api', () => ({
  getDashboard: vi.fn(),
}))

const getCacheStatsMock = vi.mocked(ragCacheApi.getCacheStats)
const getVectorStoreStatsMock = vi.mocked(ragCacheApi.getVectorStoreStats)
const getRagPolicyMock = vi.mocked(ragCacheApi.getRagPolicy)
const invalidateCacheMock = vi.mocked(ragCacheApi.invalidateCache)
const searchDocumentsMock = vi.mocked(ragCacheApi.searchDocuments)
const listRagCandidatesMock = vi.mocked(ragCacheApi.listRagCandidates)
const approveRagCandidateMock = vi.mocked(ragCacheApi.approveRagCandidate)
const rejectRagCandidateMock = vi.mocked(ragCacheApi.rejectRagCandidate)
const getRagStatusStatsMock = vi.mocked(ragCacheApi.getRagStatusStats)
const getRagChannelStatsMock = vi.mocked(ragCacheApi.getRagChannelStats)
const updateRagPolicyMock = vi.mocked(ragCacheApi.updateRagPolicy)
const resetRagPolicyMock = vi.mocked(ragCacheApi.resetRagPolicy)
const getDashboardMock = vi.mocked(dashboardApi.getDashboard)

function buildCacheStats(overrides: Partial<CacheStats> = {}): CacheStats {
  return {
    enabled: true,
    semanticEnabled: true,
    totalExactHits: 120,
    totalSemanticHits: 45,
    totalMisses: 35,
    hitRate: 0.825,
    config: {
      ttlMinutes: 60,
      maxSize: 1000,
      similarityThreshold: 0.85,
      maxCandidates: 10,
      cacheableTemperature: 0.3,
    },
    ...overrides,
  }
}

function buildVectorStoreStats(overrides: Partial<VectorStoreStats> = {}): VectorStoreStats {
  return {
    available: true,
    documentCount: 42,
    ...overrides,
  }
}

function buildRagPolicyState(): RagPolicyState {
  return {
    configEnabled: true,
    dynamicEnabled: true,
    effective: {
      enabled: true,
      requireReview: true,
      allowedChannels: ['web', 'slack'],
      minQueryChars: 10,
      minResponseChars: 20,
      blockedPatterns: [],
    },
    stored: null,
  }
}

function DocumentsRouteProbe() {
  const location = useLocation()
  return (
    <div>
      <span>Documents Page</span>
      <span data-testid="documents-location">
        {location.pathname}
        {location.search}
        {location.hash}
      </span>
    </div>
  )
}

function renderManager(initialEntries = ['/']) {
  const router = createMemoryRouter(
    [
      { path: '/', element: <RagCacheManager /> },
      { path: '/documents', element: <DocumentsRouteProbe /> },
    ],
    { initialEntries },
  )
  return render(<RouterProvider router={router} />)
}

describe('RagCacheManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'nav.ragCache': 'RAG & Cache',
      'nav.help.ragCache': 'RAG & semantic cache management',
      'common.refresh': 'Refresh',
      'common.enabled': 'Enabled',
      'common.noData': 'No data',
      'common.confirm': 'Confirm',
      'common.cancel': 'Cancel',
      'common.typeToConfirm': 'Type the following exactly to confirm:',
      'common.typeToConfirmHelp': 'This action is irreversible.',
      'common.toast.updated': 'Updated',
      'common.toast.refreshed': 'Refreshed',
      'ragCachePage.tabCache': 'Semantic Cache',
      'ragCachePage.tabRag': 'RAG Management',
      'ragCachePage.tabCandidates': 'Review Queue',
      'ragCachePage.tabAnalytics': 'Analytics',
      'ragCachePage.cacheEnabled': 'Cache Enabled',
      'ragCachePage.semanticEnabled': 'Semantic Cache Enabled',
      'ragCachePage.hitRate': 'Hit Rate',
      'ragCachePage.exactHits': 'Exact Hits',
      'ragCachePage.semanticHits': 'Semantic Hits',
      'ragCachePage.misses': 'Misses',
      'ragCachePage.config': 'Configuration',
      'ragCachePage.ttl': 'TTL (minutes)',
      'ragCachePage.maxSize': 'Max Entries',
      'ragCachePage.threshold': 'Similarity Threshold',
      'ragCachePage.maxCandidates': 'Max Candidates',
      'ragCachePage.temperature': 'Cacheable Temperature',
      'ragCachePage.invalidateAll': 'Invalidate All Cache',
      'ragCachePage.invalidateConfirm': 'This will clear all cached responses. Continue?',
      'ragCachePage.invalidate.title': 'Invalidate All Cache',
      'ragCachePage.invalidate.currentHitRate': 'Current hit rate',
      'ragCachePage.invalidate.willReset': 'will reset to 0%',
      'ragCachePage.invalidate.totalCachedResponses': 'Recent cache hits',
      'ragCachePage.invalidate.expectedImpact': 'Expected impact',
      'ragCachePage.invalidate.expectedImpactDesc': 'Subsequent requests will miss the cache and hit the LLM directly.',
      'ragCachePage.invalidate.irreversible': 'This action cannot be undone',
      'ragCachePage.invalidate.tipTitle': 'Need to clear specific entries?',
      'ragCachePage.invalidate.tipDesc': 'Per-key invalidation will be available when the backend API is added.',
      'ragCachePage.invalidate.cancel': 'Cancel',
      'ragCachePage.invalidate.execute': 'Invalidate All',
      'ragCachePage.quickSearchExt.topK': 'Top-K results',
      'ragCachePage.quickSearchExt.history': 'Recent searches',
      'ragCachePage.quickSearchExt.clearHistory': 'Clear',
      'ragCachePage.quickSearchExt.exportCsv': 'Export CSV',
      'ragCachePage.quickSearchExt.scoreLabel': 'Score',
      'common.close': 'Close',
      'ragCachePage.vectorStoreStatus': 'Vector Store',
      'ragCachePage.documentCount': 'Indexed Documents',
      'ragCachePage.ragPolicy': 'RAG Ingestion Policy',
      'ragCachePage.quickSearch': 'Quick Search',
      'ragCachePage.searchPlaceholder': 'Enter a query to test similarity search...',
      'ragCachePage.search': 'Search',
      'ragCachePage.resultsFound': '{{count}} results found',
      'ragCachePage.manageDocuments': 'Manage Documents',
      'ragCachePage.available': 'Available',
      'ragCachePage.unavailable': 'Unavailable',
      'ragCachePage.policy.title': 'RAG Ingestion Policy',
      'ragCachePage.policy.enabled': 'Enabled',
      'ragCachePage.policy.requireReview': 'Require Review',
      'ragCachePage.policy.requireReviewWarning': 'Governance Bypass',
      'ragCachePage.policy.requireReviewWarningDesc': 'Unreviewed documents will be exposed to production.',
      'ragCachePage.policy.allowedChannels': 'Allowed Channels',
      'ragCachePage.policy.allowedChannelsHint': 'Press Enter to add.',
      'ragCachePage.policy.blockedPatterns': 'Blocked Patterns',
      'ragCachePage.policy.blockedPatternsHint': 'Regex patterns.',
      'ragCachePage.policy.minQueryChars': 'Min Query Chars',
      'ragCachePage.policy.minResponseChars': 'Min Response Chars',
      'ragCachePage.policy.save': 'Save',
      'ragCachePage.policy.reset': 'Reset to Defaults',
      'ragCachePage.policy.resetConfirm': 'Reset the policy?',
      'ragCachePage.policy.savedAt': 'Last saved',
      'ragCachePage.policy.usingDefaults': 'Using config defaults',
      'ragCachePage.policy.usingStored': 'Using saved override',
      'ragCachePage.candidates.title': 'Candidate Review',
      'ragCachePage.candidates.queue': 'Review Queue',
      'ragCachePage.candidates.empty': 'No candidates found',
      'ragCachePage.candidates.filterStatus': 'Status',
      'ragCachePage.candidates.statusAll': 'All',
      'ragCachePage.candidates.approve': 'Approve',
      'ragCachePage.candidates.reject': 'Reject',
      'ragCachePage.candidates.approveConfirm': 'Approve this candidate?',
      'ragCachePage.candidates.rejectConfirm': 'Reject this candidate?',
      'ragCachePage.candidates.query': 'Query',
      'ragCachePage.candidates.response': 'Response',
      'ragCachePage.candidates.channel': 'Channel',
      'ragCachePage.candidates.capturedAt': 'Captured At',
      'ragCachePage.candidates.status': 'Status',
      'ragCachePage.candidates.sourceRun': 'Source run',
      'ragCachePage.candidates.ingestedDocument': 'Ingested document',
      'ragCachePage.candidates.detailDescription': 'Review the question and answer before making a decision.',
      'ragCachePage.candidates.nextChecks': 'Additional checks',
      'ragCachePage.candidates.nextChecksDescription': 'Check these operating conditions before approval.',
      'ragCachePage.candidates.actionKind.sync': 'Check evaluation data sync',
      'ragCachePage.candidates.actionKind.readiness': 'Check release readiness',
      'ragCachePage.candidates.actionKind.review': 'Check the operating decision',
      'ragCachePage.candidates.actionState.ready': 'Ready for review',
      'ragCachePage.candidates.actionState.blocked': 'Action needed',
      'ragCachePage.candidates.actionState.pending': 'Waiting for review',
      'ragCachePage.candidates.technicalDetails': 'Developer details',
      'ragCachePage.candidates.technicalAction': 'Original data for action {{index}}',
      'ragCachePage.candidates.candidateId': 'Candidate ID',
      'ragCachePage.candidates.actionId': 'Action ID',
      'ragCachePage.candidates.actionLabel': 'Original action label',
      'ragCachePage.candidates.runbook': 'Runbook',
      'ragCachePage.candidates.runbookCommand': 'Run command',
      'ragCachePage.candidates.runbookRemediation': 'Remediation command',
      'ragCachePage.candidates.runbookEnv': 'Env command',
      'ragCachePage.candidates.runbookReadiness': 'Readiness command',
      'ragCachePage.candidates.candidateTag': 'Candidate tag',
      'ragCachePage.candidates.workflowTags': 'Workflow tags',
      'ragCachePage.candidates.dataset': 'Dataset',
      'ragCachePage.candidates.evalCase': 'Eval case ID',
      'ragCachePage.candidates.feedbackRating': 'Feedback rating',
      'ragCachePage.candidates.feedbackSource': 'Feedback source',
      'ragCachePage.candidates.feedbackTags': 'Feedback tags',
      'ragCachePage.candidates.preflightFile': 'Preflight file',
      'ragCachePage.candidates.preflightEnvTemplate': 'Preflight env template',
      'ragCachePage.candidates.replatformReadinessFile': 'Replatform readiness file',
      'ragCachePage.candidates.smokePlanFile': 'Smoke plan file',
      'ragCachePage.candidates.releaseEvidenceFile': 'Release evidence file',
      'ragCachePage.candidates.readinessFile': 'Readiness file',
      'ragCachePage.candidates.reportFile': 'Report file',
      'ragCachePage.candidates.caseFile': 'Case file',
      'ragCachePage.candidates.runFile': 'Run file',
      'ragCachePage.candidates.suiteFile': 'Suite file',
      'ragCachePage.candidates.readinessReportArg': 'Readiness report arg',
      'ragCachePage.candidates.requiredReadinessReports': 'Required readiness reports',
      'ragCachePage.candidates.readinessReports': 'Readiness reports',
      'ragCachePage.candidates.requiredEnvAnyOf': 'Required env any-of',
      'ragCachePage.candidates.missingEnvAnyOf': 'Missing env any-of',
      'ragCachePage.candidates.recommendedEnv': 'Recommended env',
      'ragCachePage.candidates.versionBump': 'Version bump',
      'ragCachePage.candidates.tagPattern': 'Tag pattern',
      'ragCachePage.candidates.latestTagCommand': 'Latest tag command',
      'ragCachePage.candidates.recommendedTagSource': 'Recommended tag source',
      'ragCachePage.candidates.minorBoundaryReports': 'Minor boundary reports',
      'ragCachePage.candidates.dependsOnActionIds': 'Depends on actions',
      'ragCachePage.candidates.promotionCoverage': 'Promotion coverage',
      'ragCachePage.candidates.citationMarkerContract': 'Citation marker contract',
      'ragCachePage.analytics.title': 'RAG Analytics',
      'ragCachePage.analytics.empty': 'No analytics data',
      'ragCachePage.analytics.totalPending': 'Total Pending',
      'ragCachePage.analytics.totalApproved': 'Total Approved',
      'ragCachePage.analytics.totalRejected': 'Total Rejected',
      'ragCachePage.analytics.latestCaptured': 'Latest evidence {{time}}',
      'ragCachePage.analytics.latestCapturedMissing': 'No latest evidence',
      'ragCachePage.analytics.byChannel': 'By Channel',
      'ragCachePage.analytics.approvalRate': 'Approval Rate',
      'ragCachePage.insightBar.statusOk': 'System healthy',
      'ragCachePage.insightBar.statusWarning': 'Attention needed',
      'ragCachePage.insightBar.statusError': 'Error',
      'ragCachePage.insightBar.cacheLabel': 'Cache',
      'ragCachePage.insightBar.ragDocsLabel': 'RAG docs',
      'ragCachePage.insightBar.pendingLabel': 'Pending',
      'ragCachePage.insightBar.reviewQueueLabel': 'Review pending',
      'ragCachePage.insightBar.reviewQueueTitle': 'Open Review Queue tab',
      'ragCachePage.insightBar.reviewQueueAriaLabel': 'Open Review Queue tab ({{count}} pending)',
      'ragCachePage.insightBar.noPending': 'No pending reviews',
      'ragCachePage.lifecycle.title': 'RAG product flow',
      'ragCachePage.lifecycle.description': 'Release boundary from ingest to promotion.',
      'ragCachePage.lifecycle.summary': 'RAG release flow checks',
      'ragCachePage.lifecycle.ingest': 'Ingest',
      'ragCachePage.lifecycle.ingestDesc': '{{count}} docs indexed, {{pending}} pending.',
      'ragCachePage.lifecycle.ask': 'Ask',
      'ragCachePage.lifecycle.askDesc': '{{count}} docs searchable.',
      'ragCachePage.lifecycle.citedAnswer': 'Cited answer',
      'ragCachePage.lifecycle.citedAnswerDesc': '{{count}} docs can be cited.',
      'ragCachePage.lifecycle.feedbackPromotion': 'Feedback promotion',
      'ragCachePage.lifecycle.feedbackPromotionDesc': '{{approved}} approved, {{rejected}} rejected, {{pending}} pending.',
      'ragCachePage.lifecycle.releaseEvidenceVerified': 'Release evidence {{contracts}}.',
      'ragCachePage.lifecycle.releaseEvidenceMissing': 'Release evidence missing.',
      'ragCachePage.lifecycle.releaseRuntime': 'Runtime {{runtime}}.',
      'ragCachePage.lifecycle.citationStyle': 'Citation {{style}}.',
      'ragCachePage.lifecycle.poisoningEvalCases': 'Poisoning eval {{count}}.',
      'ragCachePage.lifecycle.reviewCandidates': 'Review {{count}} candidates',
      'ragCachePage.answerContract.title': 'Cited answer contract',
      'ragCachePage.answerContract.description': 'Inspect ask, citation, and promotion readiness.',
      'ragCachePage.answerContract.boundaryReady': 'Release boundary ready',
      'ragCachePage.answerContract.boundaryNeedsEvidence': 'Needs more evidence',
      'ragCachePage.answerContract.workflowLabel': 'Workflow: ingest to promotion',
      'ragCachePage.answerContract.workflowIngest': 'Ingest documents',
      'ragCachePage.answerContract.workflowIngestDesc': 'Open ingestion jobs and document readiness.',
      'ragCachePage.answerContract.workflowAsk': 'Ask readiness',
      'ragCachePage.answerContract.workflowAskDesc': '{{count}} searchable documents ready.',
      'ragCachePage.answerContract.workflowCitedAnswer': 'Cited answer',
      'ragCachePage.answerContract.workflowCitedAnswerDesc': 'Check citation IDs and source labels.',
      'ragCachePage.answerContract.workflowPromotion': 'Weak answer promotion',
      'ragCachePage.answerContract.workflowPromotionDesc': '{{count}} pending candidates need review.',
      'ragCachePage.answerContract.workflowEval': 'Eval regression',
      'ragCachePage.answerContract.workflowEvalDesc': 'Promote weak answers into source-controlled eval cases.',
      'ragCachePage.answerContract.workflowLangSmith': 'LangSmith sync',
      'ragCachePage.answerContract.workflowLangSmithDesc': 'Sync dataset examples before release readiness.',
      'ragCachePage.answerContract.workflowReadiness': 'Release readiness',
      'ragCachePage.answerContract.workflowReadinessDesc': '{{reports}} required reports checked in the cockpit.',
      'ragCachePage.answerContract.opsQueue': 'RAG operations queue',
      'ragCachePage.answerContract.opsQueueDesc': 'Close ingest, ask, cited answer, promotion, LangSmith, and readiness evidence.',
      'ragCachePage.answerContract.opsIngest': 'Ingest evidence',
      'ragCachePage.answerContract.opsIngestDesc': 'Check runtime, readiness contracts, and diagnostics surface.',
      'ragCachePage.answerContract.opsCitedAnswer': 'Ask and cited answer',
      'ragCachePage.answerContract.opsCitedAnswerDesc': 'Check searchable docs, citation style, and source label policy.',
      'ragCachePage.answerContract.opsFeedback': 'Weak answer promotion',
      'ragCachePage.answerContract.opsFeedbackDesc': 'Check reviewed candidates, eval case, and promotion coverage.',
      'ragCachePage.answerContract.opsLangSmith': 'LangSmith and readiness',
      'ragCachePage.answerContract.opsLangSmithDesc': 'Check sync evidence and readiness command.',
      'ragCachePage.answerContract.opsEvidence': 'Connected evidence',
      'ragCachePage.answerContract.opsMissing': 'Missing evidence',
      'ragCachePage.answerContract.opsNone': 'None',
      'ragCachePage.answerContract.opsMissingReleaseEvidence': 'ragIngestionLifecycle',
      'ragCachePage.answerContract.opsMissingReadinessContracts': 'readiness contracts',
      'ragCachePage.answerContract.opsMissingDiagnostics': 'diagnostics API',
      'ragCachePage.answerContract.opsMissingVectorStore': 'vector store',
      'ragCachePage.answerContract.opsMissingCitationIds': 'citation ID requirement',
      'ragCachePage.answerContract.opsMissingUncitedClaimsBlock': 'uncited claims block',
      'ragCachePage.answerContract.opsMissingReviewedCandidates': 'reviewed candidates',
      'ragCachePage.answerContract.opsMissingEvalCase': 'eval case ID',
      'ragCachePage.answerContract.opsMissingLangSmithSync': 'LangSmith sync',
      'ragCachePage.answerContract.opsMissingReadinessCommand': 'readiness command',
      'ragCachePage.answerContract.askReadiness': 'Ask readiness',
      'ragCachePage.answerContract.searchableDocuments': '{{count}} searchable documents',
      'ragCachePage.answerContract.askReadyDesc': 'Vector store can serve the ask flow.',
      'ragCachePage.answerContract.askBlockedDesc': 'Vector store is blocked.',
      'ragCachePage.answerContract.citationContract': 'Citation contract',
      'ragCachePage.answerContract.manifestCitationIds': 'Manifest citation IDs required',
      'ragCachePage.answerContract.citationDesc': '{{status}} requires source labels and manifest citation IDs.',
      'ragCachePage.answerContract.policyEnabled': 'Policy enabled',
      'ragCachePage.answerContract.policyDisabled': 'Policy disabled',
      'ragCachePage.answerContract.weakAnswerHandoff': 'Weak answer handoff',
      'ragCachePage.answerContract.reviewedCandidates': '{{count}} reviewed candidates',
      'ragCachePage.answerContract.handoffDesc': '{{approved}} approved, {{rejected}} rejected, {{pending}} pending.',
      'ragCachePage.answerContract.openPromotionQueue': 'Open promotion queue {{count}}',
      'ragCachePage.answerContract.latestHandoff': 'Latest handoff evidence',
      'ragCachePage.answerContract.pendingReview': 'Pending review',
      'common.statuses.PENDING': 'Pending',
      'common.statuses.APPROVED': 'Approved',
      'common.statuses.REJECTED': 'Rejected',
      'ragCachePage.statusLabels.pending': 'Pending review',
      'ragCachePage.statusLabels.approved': 'Approved',
      'ragCachePage.statusLabels.rejected': 'Excluded',
      'ragCachePage.statusLabels.ingested': 'Collected',
      'ragCachePage.statusLabels.unknown': 'Needs review',
      'ragCachePage.answerContract.actionId': 'Action ID',
      'ragCachePage.answerContract.actionLabel': 'Action label',
      'ragCachePage.answerContract.sourceRun': 'Source run',
      'ragCachePage.answerContract.dataset': 'Dataset',
      'ragCachePage.answerContract.reportFile': 'Report file',
      'ragCachePage.answerContract.answerContract': 'Answer contract',
      'ragCachePage.answerContract.answerContractValue': 'researchAnswerContract.citationStyle={{citationStyle}}',
      'ragCachePage.answerContract.feedbackGate': 'Feedback gate',
      'ragCachePage.answerContract.reviewRequired': 'Candidates are promoted after review',
      'ragCachePage.answerContract.reviewOptional': 'Review optional',
      'ragCachePage.answerContract.releaseEvidence': 'Release evidence',
      'ragCachePage.answerContract.releaseEvidenceValue': 'ragIngestionLifecycle + langsmith_eval_sync',
      'ragCachePage.answerContract.releaseGateEvidence': 'Release gate evidence',
      'ragCachePage.answerContract.ragRuntime': 'RAG runtime',
      'ragCachePage.answerContract.embeddingBoundary': 'Embedding boundary',
      'ragCachePage.answerContract.citationStyle': 'Citation style',
      'ragCachePage.answerContract.sourceLabelPolicy': 'Source label policy',
      'ragCachePage.answerContract.sourceLabelsRequired': 'Source labels required',
      'ragCachePage.answerContract.sourceLabelsOptional': 'Source labels optional',
      'ragCachePage.answerContract.uncitedClaims': 'Uncited claims',
      'ragCachePage.answerContract.uncitedClaimsBlocked': 'Blocked',
      'ragCachePage.answerContract.uncitedClaimsAllowed': 'Allowed',
      'ragCachePage.answerContract.readinessContracts': 'Readiness contracts',
      'ragCachePage.answerContract.diagnosticsApi': 'Diagnostics API',
      'ragCachePage.answerContract.releaseEvidenceChecklist': 'Required release evidence',
      'ragCachePage.answerContract.allEvidencePresent': 'All required evidence is connected.',
      'ragCachePage.answerContract.missingEvidence': 'Missing: {{fields}}',
      'ragCachePage.answerContract.releaseReadinessHandoff': 'Release readiness handoff',
      'ragCachePage.answerContract.releaseReadinessStatus': 'Readiness status',
      'ragCachePage.answerContract.blockingReports': 'Blocking reports',
      'ragCachePage.answerContract.productBoundary': 'Product boundary',
      'ragCachePage.answerContract.missingBoundaryEvidence': 'Missing boundary evidence',
      'ragCachePage.answerContract.langsmithSyncCases': 'LangSmith sync cases',
      'ragCachePage.answerContract.sourceAllowlist': 'source allowlist',
      'ragCachePage.answerContract.mimeAllowlist': 'MIME allowlist',
      'ragCachePage.answerContract.sizeLimit': 'size limit',
      'ragCachePage.answerContract.aclMetadata': 'ACL metadata',
      'ragCachePage.answerContract.aclBeforeRanking': 'ACL before ranking',
      'ragCachePage.answerContract.rawAclRedaction': 'raw ACL redaction',
      'ragCachePage.answerContract.quarantine': 'quarantine before index',
      'ragCachePage.answerContract.checksumIdempotency': 'checksum idempotency',
      'ragCachePage.answerContract.citationIds': 'citation IDs',
      'ragCachePage.answerContract.sourceLabels': 'source labels',
      'ragCachePage.answerContract.missingChunks': 'missing chunk tracking',
      'ragCachePage.answerContract.contentHashMismatch': 'content hash mismatch tracking',
      'ragCachePage.answerContract.humanReviewPromotion': 'human review promotion',
      'documentsPage.requireReview': 'Require review for new candidates',
      'documentsPage.allowedChannels': 'Allowed Channels',
    }, true, true)

    getCacheStatsMock.mockResolvedValue(buildCacheStats())
    getVectorStoreStatsMock.mockResolvedValue(buildVectorStoreStats())
    getRagPolicyMock.mockResolvedValue(buildRagPolicyState())
    invalidateCacheMock.mockResolvedValue({ invalidated: true, message: 'done' })
    listRagCandidatesMock.mockResolvedValue([])
    approveRagCandidateMock.mockResolvedValue(undefined)
    rejectRagCandidateMock.mockResolvedValue(undefined)
    getRagStatusStatsMock.mockResolvedValue([])
    getRagChannelStatsMock.mockResolvedValue([])
    updateRagPolicyMock.mockResolvedValue(undefined)
    resetRagPolicyMock.mockResolvedValue(undefined)
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
        ragIngestionLifecycle: {
          status: 'verified',
          framework: 'langchain-postgres',
          vectorStore: 'PGVector',
          embeddingBoundary: 'LangChainEmbeddings',
          sourceAllowlistRequired: true,
          mimeAllowlistRequired: true,
          sizeLimitRequired: true,
          aclMetadataRequired: true,
          aclBeforeRanking: true,
          rawAclRedactedFromModelContext: true,
          humanReviewRequiredForCapturedCandidates: true,
          quarantineBeforeIndex: true,
          checksumIdempotency: true,
          poisoningEvalCaseIds: ['case_rag_poisoning_guard'],
          diagnosticsSurface: {
            apiPaths: ['/api/admin/rag/ingestion-jobs/{job_id}'],
          },
          verificationSensors: {
            releaseReadinessContracts: ['ragIngestionLifecycle', 'researchAnswerContract'],
          },
          researchAnswerContract: {
            profile: 'research',
            citationStyle: 'manifest_ids',
            requiresCitationIds: true,
            requiresSourceLabels: true,
            fallbackResponseIncludesSources: true,
            uncitedClaimsAllowed: false,
            tracksMissingChunks: true,
            tracksContentHashMismatches: true,
          },
        },
      },
    })

    // jsdom does not implement scrollIntoView. Our insight-bar CTA calls it
    // after selecting the candidates tab. Provide a harmless stub so the
    // rAF-scheduled callback doesn't blow up assertions in other tests.
    if (!('scrollIntoView' in HTMLElement.prototype)) {
      Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
        configurable: true,
        writable: true,
        value: () => {},
      })
    }
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders page title and five task tabs', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('RAG & Cache')).toBeInTheDocument()
    })
    expect(screen.getByText('RAG & semantic cache management')).toBeInTheDocument()

    const tabButtons = screen.getAllByRole('tab')
    expect(tabButtons).toHaveLength(5)
    expect(tabButtons[0]).toHaveTextContent('Semantic Cache')
    expect(tabButtons[1]).toHaveTextContent('Review Queue')
    expect(tabButtons[2]).toHaveTextContent('RAG Management')
    expect(tabButtons[3]).toHaveTextContent('ragCachePage.tabPolicy')
    expect(tabButtons[4]).toHaveTextContent('Analytics')
  }, 10_000)

  it('keeps refresh with the document-search operating summary', () => {
    const { container } = renderManager()
    expect(within(container.querySelector('.rag-insight-bar')!).getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
  })

  it('shows cache statistics after clicking Semantic Cache tab', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))

    await waitFor(() => {
      // 82.5% appears in both InsightBar and the cache StatCard
      expect(screen.getAllByText('82.5%').length).toBeGreaterThanOrEqual(1)
    })
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByText('45')).toBeInTheDocument()
    expect(screen.getByText('35')).toBeInTheDocument()
  })

  it('keeps developer cache settings collapsed', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))

    await waitFor(() => {
      expect(screen.getByText('ragCachePage.cacheTechnicalDetails')).toBeInTheDocument()
    })
    expect(screen.getByText('ragCachePage.cacheTechnicalDetails').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('60')).toBeInTheDocument()
    expect(screen.getByText((1000).toLocaleString())).toBeInTheDocument()
    expect(screen.getByText('0.85')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText('0.3')).toBeInTheDocument()
  })

  it('shows cache controls with readable labels', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))

    await waitFor(() => {
      expect(screen.getByText('ragCachePage.runtime.title')).toBeInTheDocument()
    })
    expect(screen.getByRole('checkbox', { name: 'ragCachePage.runtime.cacheEnabled' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'ragCachePage.runtime.semanticEnabled' })).toBeChecked()
  })

  it('shows invalidate cache button', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Invalidate All Cache' })).toBeInTheDocument()
    })
  })

  it('opens impact preview modal when invalidate is clicked and executes on confirm', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Invalidate All Cache' })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'Invalidate All Cache' }))

    // Modal shows impact preview
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(screen.getByText('Current hit rate')).toBeInTheDocument()
    // 82.5% appears in StatCard and modal; check dialog contains it
    expect(dialog).toHaveTextContent('82.5%')
    expect(screen.getByText('This action cannot be undone')).toBeInTheDocument()

    // Execute button is gated by type-to-confirm; type the token first.
    const confirmInput = within(dialog).getByRole('textbox')
    await user.type(confirmInput, 'INVALIDATE')
    await user.click(screen.getByRole('button', { name: 'Invalidate All' }))

    await waitFor(() => {
      expect(invalidateCacheMock).toHaveBeenCalled()
    })
  })

  it('cancels invalidate impact modal without calling API', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Invalidate All Cache' })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'Invalidate All Cache' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(invalidateCacheMock).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('switches to the document-search tab without repeating vector-store status tiles', async () => {
    const user = userEvent.setup()
    const { container } = renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    await waitFor(() => {
      // '42' also appears in the insight bar — check at least one occurrence.
      expect(screen.getAllByText('42').length).toBeGreaterThanOrEqual(1)
    })
    expect(container.querySelector('.stat-row')).not.toBeInTheDocument()
  })

  it('keeps document search focused on a compact answer summary and direct actions', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    await waitFor(() => {
      expect(screen.getByText('ragCachePage.answerContract.operatorTitle')).toBeInTheDocument()
    })
    expect(screen.getByText('ragCachePage.answerContract.prepareDocuments')).toBeInTheDocument()
    expect(screen.getByText('ragCachePage.answerContract.reviewWeakAnswers')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'ragCachePage.answerContract.openAnswerTest' })).toHaveAttribute('href', '#rag-answer-probe')
    expect(screen.queryByText('RAG product flow')).not.toBeInTheDocument()
  })

  it('surfaces release readiness blockers on the RAG answer contract panel', async () => {
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
        blockingReports: ['preflight', 'langsmith_eval_sync'],
        productCapabilityBoundary: {
          capability: 'rag_ingest_to_feedback_eval_langsmith_readiness',
          status: 'blocked',
          minorEligible: false,
          missingEvidence: ['rag_ingestion_lifecycle', 'langsmith_trace_grading'],
          sourceReport: 'release_readiness',
        },
        langsmithSync: {
          datasetName: 'reactor-rag-regression',
          caseCount: 1,
          exampleCount: 1,
          caseIds: ['case_rag_candidate_grounded_citation'],
        },
        ragIngestionLifecycle: {
          status: 'verified',
          framework: 'langchain-postgres',
          vectorStore: 'PGVector',
          embeddingBoundary: 'LangChainEmbeddings',
          sourceAllowlistRequired: true,
          mimeAllowlistRequired: true,
          sizeLimitRequired: true,
          aclMetadataRequired: true,
          aclBeforeRanking: true,
          rawAclRedactedFromModelContext: true,
          humanReviewRequiredForCapturedCandidates: true,
          quarantineBeforeIndex: true,
          checksumIdempotency: true,
          poisoningEvalCaseIds: ['case_rag_poisoning_guard'],
          diagnosticsSurface: {
            apiPaths: ['/api/admin/rag/ingestion-jobs/{job_id}'],
          },
          verificationSensors: {
            releaseReadinessContracts: ['ragIngestionLifecycle', 'researchAnswerContract'],
          },
          researchAnswerContract: {
            profile: 'research',
            citationStyle: 'manifest_ids',
            requiresCitationIds: true,
            requiresSourceLabels: true,
            fallbackResponseIncludesSources: true,
            uncitedClaimsAllowed: false,
            tracksMissingChunks: true,
            tracksContentHashMismatches: true,
          },
        },
      },
    })
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    const details = await screen.findByText('ragCachePage.answerContract.technicalDetails')
    expect(details.closest('details')).not.toHaveAttribute('open')
    expect(screen.queryByText('preflight, langsmith_eval_sync')).not.toBeInTheDocument()
  })

  it('surfaces metadata-only release handoff candidates in the answer contract panel', async () => {
    listRagCandidatesMock.mockResolvedValue([
      {
        id: 'candidate-metadata-only',
        runId: 'run-metadata-only',
        query: 'Weak answer with evidence metadata',
        response: 'Candidate answer',
        channel: 'slack',
        status: 'PENDING',
        capturedAt: 1700000000000,
        nextActions: [
          {
            id: 'sync-langsmith-metadata',
            label: 'Sync metadata-only candidate to LangSmith',
            sourceRunId: 'run-metadata-only',
            datasetName: 'reactor-release-regression',
            reportFile: 'reports/langsmith-eval-sync.json',
          },
        ],
      },
    ])
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    const details = await screen.findByText('ragCachePage.answerContract.technicalDetails')
    await user.click(details)
    expect(details.closest('details')).not.toHaveTextContent('reactor-release-regression')
  })

  it('keeps reviewed release handoff evidence visible after candidate promotion', async () => {
    listRagCandidatesMock.mockResolvedValue([
      {
        id: 'candidate-reviewed-release',
        runId: 'run-reviewed-release',
        query: 'Weak answer promoted after missing citation',
        response: 'Candidate answer with weak citation evidence',
        channel: 'slack',
        status: 'APPROVED',
        capturedAt: 1700000000000,
        reviewedAt: 1700000100000,
        reviewedBy: 'release-operator',
        nextActions: [
          {
            id: 'sync-reviewed-langsmith',
            label: 'Sync reviewed candidate to LangSmith',
            evalCaseId: 'case_rag_candidate_grounded_citation',
            sourceRunId: 'run-reviewed-release',
            datasetName: 'reactor-release-regression',
            reportFile: 'reports/langsmith-eval-sync.json',
          },
        ],
      },
    ])
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    const details = await screen.findByText('ragCachePage.answerContract.technicalDetails')
    await user.click(details)
    expect(details.closest('details')).not.toHaveTextContent('case_rag_candidate_grounded_citation')
    expect(details.closest('details')).not.toHaveTextContent('reactor-release-regression')
  })

  it('opens the RAG lifecycle tab from a release workflow deep link', async () => {
    listRagCandidatesMock.mockResolvedValue([
      {
        id: 'candidate-1',
        tenantId: 'tenant-1',
        status: 'PENDING',
        channel: 'slack',
        query: 'How do I cite this?',
        response: 'Use the manifest citation.',
        capturedAt: '2026-07-07T00:00:00Z',
      },
    ])

    const { container } = renderManager([RELEASE_WORKFLOW_PATHS_BY_ID.rag.replace('/rag-cache', '/')])

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'RAG Management' })).toHaveAttribute('aria-selected', 'true')
    })
    await waitFor(() => {
      expect(container.querySelector(`#${RELEASE_RAG_ANSWER_CONTRACT_ANCHOR_ID}`)).toBeInTheDocument()
    })
  })

  it('keeps editable collection policy in its own tab', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'ragCachePage.tabPolicy' }))

    await waitFor(() => {
      expect(screen.getByText('RAG Ingestion Policy')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset to Defaults' })).toBeInTheDocument()
  })

  it('explains when document search is unavailable', async () => {
    getVectorStoreStatsMock.mockResolvedValue(buildVectorStoreStats({ available: false }))
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    await waitFor(() => {
      expect(screen.getByText('ragCachePage.answerContract.checkAnswerBlocked')).toBeInTheDocument()
    })
  })

  it('shows quick search section on RAG tab', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    await waitFor(() => {
      expect(screen.getByText('Quick Search')).toBeInTheDocument()
    })
    expect(screen.getByPlaceholderText('Enter a query to test similarity search...')).toBeInTheDocument()
  })

  it('performs search and shows results count', async () => {
    searchDocumentsMock.mockResolvedValue([
      { id: 'doc-1', content: 'Test content 1', metadata: {}, score: 0.95 },
      { id: 'doc-2', content: 'Test content 2', metadata: {}, score: 0.88 },
    ])
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    await waitFor(() => {
      expect(screen.getByText('Quick Search')).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText('Enter a query to test similarity search...')
    await user.type(input, 'test query')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => {
      expect(screen.getByText('2 results found')).toBeInTheDocument()
    })
    expect(searchDocumentsMock).toHaveBeenCalledWith('test query', 5)
  })

  it('shows empty state when search returns no results', async () => {
    searchDocumentsMock.mockResolvedValue([])
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    await waitFor(() => {
      expect(screen.getByText('Quick Search')).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText('Enter a query to test similarity search...')
    await user.type(input, 'no results query')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => {
      expect(screen.getByText('No data')).toBeInTheDocument()
    })
  })

  it('does not search when query is empty', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    await waitFor(() => {
      expect(screen.getByText('Quick Search')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'Search' }))

    expect(searchDocumentsMock).not.toHaveBeenCalled()
  })

  it('opens document management from the answer-preparation step', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    await waitFor(() => {
      expect(screen.getByText('ragCachePage.answerContract.openDocuments')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('link', { name: 'ragCachePage.answerContract.openDocuments' }))

    expect(screen.getByText('Documents Page')).toBeInTheDocument()
    expect(screen.getByTestId('documents-location')).toHaveTextContent(
      RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
    )
  })

  it('hides cache tab content when RAG tab is active', async () => {
    const user = userEvent.setup()
    renderManager()

    // Switch to Semantic Cache tab first so cache settings appear.
    await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))

    await waitFor(() => {
      expect(screen.getByText('ragCachePage.cacheTechnicalDetails')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    expect(screen.queryByText('ragCachePage.cacheTechnicalDetails')).not.toBeInTheDocument()
    expect(screen.queryByText('Invalidate All Cache')).not.toBeInTheDocument()
  })

  it('handles search error gracefully by showing empty results', async () => {
    searchDocumentsMock.mockRejectedValue(new Error('Network error'))
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    await waitFor(() => {
      expect(screen.getByText('Quick Search')).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText('Enter a query to test similarity search...')
    await user.type(input, 'failing query')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => {
      expect(screen.getByText('No data')).toBeInTheDocument()
    })
  })

  it('triggers search when Enter is pressed in the search input', async () => {
    searchDocumentsMock.mockResolvedValue([{ id: 'doc-1', content: 'Test content', metadata: {}, score: 0.9 }])
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'RAG Management' }))

    await waitFor(() => {
      expect(screen.getByText('Quick Search')).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText('Enter a query to test similarity search...')
    await user.type(input, 'enter test{Enter}')

    await waitFor(() => {
      expect(searchDocumentsMock).toHaveBeenCalled()
    })
  })

  it('shows dash placeholders when cache stats are missing', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      getCacheStatsMock.mockResolvedValue(undefined as unknown as CacheStats)
      const user = userEvent.setup()
      renderManager()

      await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))

      await waitFor(() => {
        const dashes = screen.getAllByText('-')
        expect(dashes.length).toBeGreaterThanOrEqual(4)
      })
      expect(consoleError).not.toHaveBeenCalledWith(
        expect.stringContaining('Query data cannot be undefined'),
      )
    } finally {
      consoleError.mockRestore()
    }
  })

  it('shows candidates empty state on Review Queue tab when none', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'Review Queue' }))

    await waitFor(() => {
      expect(screen.getByText('No candidates found')).toBeInTheDocument()
    })
    expect(screen.getByText('ragCachePage.candidates.emptyDesc')).toBeInTheDocument()
    expect(document.querySelector('.rag-inline-state')).toBeInTheDocument()
    expect(document.querySelector('.empty-state-icon')).not.toBeInTheDocument()
    expect(listRagCandidatesMock).toHaveBeenCalled()
  })

  it('keeps release evidence closed in the candidate drawer', async () => {
    listRagCandidatesMock.mockResolvedValue([
      {
        id: 'c1',
        runId: 'run-c1',
        query: 'Weak answer with missing citation',
        response: 'Candidate answer',
        channel: 'slack',
        status: 'APPROVED',
        capturedAt: 1700000000000,
        ingestedDocumentId: 'doc-c1',
        nextActions: [
          {
            id: 'sync-langsmith',
            label: 'Sync the candidate regression case to LangSmith',
            evalCaseId: 'case_rag_candidate_grounded_citation',
            sourceRunId: 'run-c1',
            candidateTag: 'rag-candidate:c1',
            workflowTags: ['rag-candidate', 'citation-failure', 'expected-citation:doc-c1-0'],
            datasetName: 'reactor-release-regression',
            feedbackRating: 'thumbs_down',
            feedbackSource: 'slack',
            feedbackTags: ['missing-citation', 'weak-answer'],
            preflightFile: 'reports/release-smoke-preflight.json',
            preflightEnvTemplate: 'reports/release-smoke.env.example',
            replatformReadinessFile: 'reports/replatform-readiness.json',
            smokePlanFile: 'reports/release-smoke-plan.json',
            releaseEvidenceFile: 'reports/release-evidence.json',
            reportFile: 'reports/langsmith-eval-sync.json',
            caseFile: 'reports/evals/cases/case_rag_candidate_grounded_citation.json',
            runFile: 'reports/runs/run-c1.json',
            suiteFile: 'reports/evals/rag-candidates.json',
            releaseReadinessFile: 'reports/release-readiness.json',
            releaseReadinessCommand: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
            remediationCommand: 'reactor-langsmith-eval-sync --suite rag-candidates',
            envFileCommand: 'cp reports/release-smoke.env.example .env.release-smoke',
            readinessReportArg: '--readiness-output reports/release-readiness.json',
            requiredReadinessReports: ['rag_ingestion_lifecycle', 'langsmith_eval_sync'],
            readinessReports: {
              langsmith_eval_sync: 'reports/langsmith-eval-sync.json',
              release_evidence: 'reports/release-evidence.json',
            },
            requiredEnvAnyOf: [['LANGSMITH_API_KEY', 'REACTOR_OBSERVABILITY_LANGSMITH_API_KEY']],
            missingEnvAnyOf: ['LANGSMITH_API_KEY'],
            recommendedEnv: ['LANGSMITH_API_KEY'],
            recommendedVersionBump: 'minor',
            recommendedTagPattern: 'v1.1.0',
            latestTagCommand: 'git describe --tags --abbrev=0',
            recommendedTagSource: 'release_readiness',
            minorBoundaryReports: ['rag_ingestion_lifecycle', 'langsmith_eval_sync'],
            dependsOnActionIds: ['review-candidate'],
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
    ])
    const user = userEvent.setup()
    renderManager()

    await user.click(await screen.findByRole('tab', { name: 'Review Queue' }))
    await user.click(await screen.findByRole('button', { name: /Weak answer with missing citation/ }))

    expect(screen.getByText('Additional checks')).toBeInTheDocument()
    expect(screen.getByText('Check evaluation data sync')).toBeInTheDocument()
    expect(screen.getByText('Waiting for review')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /release|sync|promotion/i })).not.toBeInTheDocument()

    const details = screen.getByText('Developer details').closest('details')
    expect(details).not.toHaveAttribute('open')
    expect(screen.getByText('sync-langsmith')).not.toBeVisible()
    expect(screen.getByText('reports/release-readiness.json')).not.toBeVisible()
    expect(screen.getByText('reactor-release-regression')).not.toBeVisible()

    await user.click(screen.getByText('Developer details'))

    expect(screen.getAllByText('run-c1')[0]).toBeVisible()
    expect(screen.getByText('doc-c1')).toBeVisible()
    expect(screen.getByText('sync-langsmith')).toBeVisible()
    expect(screen.getByText('case_rag_candidate_grounded_citation')).toBeVisible()
    expect(screen.getByText('rag-candidate:c1')).toBeVisible()
    expect(screen.getByText('reactor-release-regression')).toBeVisible()
    expect(screen.getByText('reports/release-smoke-preflight.json')).toBeVisible()
    expect(screen.getByText('reports/release-readiness.json')).toBeVisible()
    expect(screen.getByText('reports/evals/cases/case_rag_candidate_grounded_citation.json')).toBeVisible()
    expect(screen.getByText('reports/runs/run-c1.json')).toBeVisible()
    expect(screen.getByText('reactor-langsmith-eval-sync --suite rag-candidates')).toBeVisible()
    expect(screen.getByText('cp reports/release-smoke.env.example .env.release-smoke')).toBeVisible()
    expect(screen.getByText('--readiness-output reports/release-readiness.json')).toBeVisible()
    expect(screen.getByText('minor')).toBeVisible()
    expect(screen.getByText('v1.1.0')).toBeVisible()
    expect(screen.getByText('git describe --tags --abbrev=0')).toBeVisible()
    expect(screen.getByText('requiredContextDiagnostics: true, runContextDiagnosticsPresent: true, sourceRunIdPresent: true')).toBeVisible()
    expect(screen.getByText('citationMarkersRequired: true, citationWorkflowTags: rag-candidate:grounded_citation')).toBeVisible()
    expect(screen.getAllByRole('button', { name: 'common.copy.aria' }).length).toBeGreaterThan(0)
  })

  it('shows analytics empty state when no data', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'Analytics' }))

    await waitFor(() => {
      expect(screen.getByText('No analytics data')).toBeInTheDocument()
    })
    expect(screen.getByText('ragCachePage.analytics.emptyDesc')).toBeInTheDocument()
    expect(document.querySelector('.rag-inline-state')).toBeInTheDocument()
    expect(getRagStatusStatsMock).toHaveBeenCalled()
    expect(getRagChannelStatsMock).toHaveBeenCalled()
  })

  it('shows latest captured evidence on RAG analytics status cards', async () => {
    getRagStatusStatsMock.mockResolvedValue([
      { status: 'PENDING', count: 3, latestCaptured: '2026-04-05T09:00:00' },
      { status: 'APPROVED', count: 7, latestCaptured: '2026-04-05T12:00:00' },
      { status: 'REJECTED', count: 2, latestCaptured: '2026-04-04T18:30:00' },
    ])
    getRagChannelStatsMock.mockResolvedValue([
      { channel: 'slack', pendingCount: 3, approvedCount: 7, rejectedCount: 2 },
    ])
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('tab', { name: 'Analytics' }))

    await waitFor(() => {
      expect(screen.getByText('Latest evidence 2026-04-05 09:00')).toBeInTheDocument()
    })
    expect(screen.getByText('Latest evidence 2026-04-05 12:00')).toBeInTheDocument()
    expect(screen.getByText('Latest evidence 2026-04-04 18:30')).toBeInTheDocument()
  })

  it('handles fireEvent click on refresh button', async () => {
    renderManager()

    await waitFor(() => {
      expect(getCacheStatsMock).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => {
      expect(getCacheStatsMock).toHaveBeenCalledTimes(2)
    })
  })

  it('defaults to RAG Management tab on first load when no pending candidates', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'RAG Management' })).toHaveAttribute(
        'aria-selected',
        'true',
      )
    })
  })

  it('defaults to Review Queue tab when pending candidates exist on first load', async () => {
    listRagCandidatesMock.mockResolvedValue([
      {
        id: 'c1',
        query: 'Pending 1',
        response: 'answer',
        channel: 'web',
        status: 'PENDING',
        capturedAt: 0,
      },
      {
        id: 'c2',
        query: 'Pending 2',
        response: 'answer',
        channel: 'web',
        status: 'PENDING',
        capturedAt: 0,
      },
    ])
    renderManager()

    await waitFor(() => {
      const reviewTab = screen.getByRole('tab', { name: /Review Queue/ })
      expect(reviewTab).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('shows pending count badge on Review Queue tab', async () => {
    listRagCandidatesMock.mockResolvedValue([
      {
        id: 'c1',
        query: 'Pending 1',
        response: 'a',
        channel: 'web',
        status: 'PENDING',
        capturedAt: 0,
      },
      {
        id: 'c2',
        query: 'Pending 2',
        response: 'a',
        channel: 'web',
        status: 'PENDING',
        capturedAt: 0,
      },
      {
        id: 'c3',
        query: 'Pending 3',
        response: 'a',
        channel: 'web',
        status: 'PENDING',
        capturedAt: 0,
      },
    ])
    renderManager()

    await waitFor(() => {
      const reviewTab = screen.getByRole('tab', { name: /Review Queue/ })
      expect(reviewTab).toHaveTextContent('3')
    })
  })

  it('renders the insight bar with system status and metrics', async () => {
    renderManager()

    await waitFor(() => {
      expect(screen.getByText('System healthy')).toBeInTheDocument()
    })
    expect(screen.getByText('Cache')).toBeInTheDocument()
    expect(screen.getByText('RAG docs')).toBeInTheDocument()
    expect(screen.getByText('Pending')).toBeInTheDocument()
  })

  it('keeps manually selected tab even after data refreshes', async () => {
    const user = userEvent.setup()
    renderManager()

    // Manually click Semantic Cache
    await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Semantic Cache' })).toHaveAttribute(
        'aria-selected',
        'true',
      )
    })

    // Simulate data refresh by clicking Refresh
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    // Should still be on Semantic Cache
    await waitFor(() => {
      expect(getCacheStatsMock).toHaveBeenCalledTimes(2)
    })
    expect(screen.getByRole('tab', { name: 'Semantic Cache' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('insight bar review button jumps to candidates tab', async () => {
    listRagCandidatesMock.mockResolvedValue([
      {
        id: 'c1',
        query: 'pending',
        response: 'r',
        channel: 'web',
        status: 'PENDING',
        capturedAt: 0,
      },
    ])
    const user = userEvent.setup()
    renderManager()

    // Default is candidates (since pending > 0). Click Semantic Cache to move off it.
    await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Semantic Cache' })).toHaveAttribute(
        'aria-selected',
        'true',
      )
    })

    // The insight bar should have a Review button for the pending candidate.
    // aria-label takes precedence over visible text for role-based queries.
    const reviewButton = screen.getByRole('button', {
      name: /Open Review Queue tab/,
    })
    await user.click(reviewButton)

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Review Queue/ })).toHaveAttribute(
        'aria-selected',
        'true',
      )
    })
  })

  it('insight bar review button scrolls the candidates tab into view and focuses it', async () => {
    listRagCandidatesMock.mockResolvedValue([
      {
        id: 'c1',
        query: 'pending',
        response: 'r',
        channel: 'web',
        status: 'PENDING',
        capturedAt: 0,
      },
    ])
    // scrollIntoView is polyfilled in beforeEach; replace with a spy here.
    const scrollSpy = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: scrollSpy,
    })
    // jsdom does not implement rAF timing precisely; delegate to setTimeout.
    const rafSpy = vi
      .spyOn(window, 'requestAnimationFrame')
      .mockImplementation((cb: FrameRequestCallback) => {
        cb(0)
        return 0
      })
    const user = userEvent.setup()
    renderManager()

    await user.click(await screen.findByRole('tab', { name: 'Semantic Cache' }))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'Semantic Cache' })).toHaveAttribute(
        'aria-selected',
        'true',
      )
    })

    const reviewButton = screen.getByRole('button', {
      name: /Open Review Queue tab/,
    })
    await user.click(reviewButton)

    await waitFor(() => {
      expect(scrollSpy).toHaveBeenCalled()
    })
    const candidatesTab = screen.getByRole('tab', { name: /Review Queue/ })
    expect(candidatesTab).toHaveFocus()

    rafSpy.mockRestore()
  })
})

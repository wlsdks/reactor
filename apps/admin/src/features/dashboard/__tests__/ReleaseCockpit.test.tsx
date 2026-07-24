import { describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, within } from '../../../test/utils'
import { ReleaseCockpit, type ReleaseCockpitView } from '../ui/ReleaseCockpit'
import {
  RELEASE_COCKPIT_ANCHOR_ID,
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_RAG_ANSWER_CONTRACT_PATH,
  RELEASE_WORKFLOW_GATE_PATHS,
  RELEASE_WORKFLOW_GATE_STEP_NUMBERS,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../../shared/releaseWorkflow'
import type { DashboardReleaseReadinessSummary } from '../types'

const passedReadiness: DashboardReleaseReadinessSummary = {
  status: 'eligible_with_warnings',
  syncedAt: '2026-07-10T00:00:00Z',
  provenance: {
    status: 'verified',
    commitSha: 'a'.repeat(40),
    expectedCommitSha: 'a'.repeat(40),
    generatedAt: '2026-07-10T00:00:00Z',
    inputHash: 'b'.repeat(64),
    verifiedCurrentHead: true,
  },
  recommendedTag: null,
  recommendedVersionBump: null,
  minorEligible: null,
  blockingReports: [],
  warningReports: [],
  warnings: [
    {
      name: 'hardening_suite',
      status: 'review_required',
      source: 'memoryMaintenanceLifecycle.dependencyWarnings',
      remediation: 'review LangMem/trustcall/LangGraph dependency update',
      remediationCommand: 'monitor upstream trustcall/langmem compatibility',
      reviewCommand: 'uv pip show langmem trustcall langgraph',
      findings: [
        {
          package: 'trustcall',
          module: 'trustcall._base',
          deprecatedImport: 'langgraph.constants.Send',
          replacement: 'langgraph.types.Send',
          severity: 'warning',
        },
      ],
    },
  ],
  tagRecommendation: {
    status: 'eligible_with_warnings',
    eligible: true,
    latestTag: 'v1.0.14',
    recommendedTag: 'v1.1.0',
    recommendedVersionBump: 'minor',
    minorEligible: true,
    minorBoundaryReports: ['langsmith_eval_sync'],
    passedReports: ['smoke_run', 'release_evidence', 'hardening_suite', 'langsmith_eval_sync'],
    warningReports: ['hardening_suite'],
    warningReviewRequired: true,
    nextAction: 'review release readiness warnings, then verify clean worktree and choose the next minor version tag',
    releaseReadinessCommand: 'uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json',
  },
  productCapabilityBoundary: {
    capability: 'rag_ingest_to_feedback_eval_langsmith_readiness',
    minorEligible: true,
    evidence: [
      'rag_ingestion_lifecycle',
      'rag_ingestion_candidate_feedback_queue',
      'feedback_promotion.reviewed_feedback',
      'langsmith_trace_grading',
      'slack_gateway_smoke',
      'a2a_protocol',
      'backend_provider_integration',
      'release_readiness_command',
    ],
    missingEvidence: [],
    sourceReport: 'langsmith_eval_sync',
    status: 'passed',
  },
  requiredReports: ['smoke_run', 'release_evidence', 'hardening_suite', 'langsmith_eval_sync'],
  missingReports: [],
  requiredEnvAnyOf: [
    ['LANGSMITH_API_KEY', 'REACTOR_OBSERVABILITY_LANGSMITH_API_KEY'],
    ['REACTOR_A2A_BASE_URL'],
  ],
  missingEnvAnyOf: ['REACTOR_A2A_BASE_URL'],
  recommendedEnv: ['REACTOR_SLACK_BOT_TOKEN', 'REACTOR_SLACK_SIGNING_SECRET'],
  gates: [
    { id: 'rag', status: 'passed' },
    { id: 'feedback', status: 'passed' },
    { id: 'langsmith', status: 'passed' },
    { id: 'slack', status: 'passed' },
    { id: 'a2a', status: 'passed' },
    { id: 'provider', status: 'passed' },
  ],
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
  ragIngestionLifecycle: {
    status: 'verified',
    framework: 'langchain-postgres',
    vectorStore: 'PGVector',
    embeddingBoundary: 'provider-managed embeddings with ACL-aware manifests',
    poisoningEvalCaseIds: ['case_rag_ingest_poisoning_guard'],
    diagnosticsSurface: {
      status: 'verified',
      apiPaths: ['/api/admin/rag/diagnostics', '/api/admin/rag/candidates'],
      releaseReviewFields: ['ragIngestionLifecycle', 'researchAnswerContract'],
    },
    verificationSensors: {
      covers: ['ingest', 'ask', 'cited_answer', 'weak_answer_promotion'],
      focusedTests: ['tests/integration/test_rag_ingestion_lifecycle.py'],
      releaseReadinessContracts: ['rag_ingestion_lifecycle', 'research_answer_contract'],
    },
    researchAnswerContract: {
      profile: 'grounded_research',
      citationStyle: 'manifest_ids',
      requiresCitationIds: true,
      requiresSourceLabels: true,
      fallbackResponseIncludesSources: true,
      uncitedClaimsAllowed: false,
      tracksMissingChunks: true,
      tracksContentHashMismatches: true,
    },
  },
  feedbackReviewQueue: {
    status: 'passed',
    reviewStatus: 'reviewed',
    reviewNote: 'feedback inbox reviewed and promoted into regression coverage',
    candidateTag: 'case_rag_candidate_grounded_citation',
    caseIds: ['case_rag_candidate_grounded_citation'],
    reviewTags: ['release-gate', 'grounded-citation'],
    feedbackRatingCounts: { positive: 3, negative: 1 },
    feedbackSourceCounts: { slack: 2, admin: 2 },
    workflowTagCounts: { rag: 4 },
    expectedCitationCounts: { required: 4 },
  },
  slackGatewaySmoke: {
    status: 'verified',
    gateway: 'native-slack-gateway',
    ingress: 'socket-mode',
    currentThreadReplyRoute: 'chat.postMessage',
    signatureVerificationRequired: true,
    responseUrlRouteSupported: true,
    mcpWriteOverlapForbidden: true,
    requiredChecks: ['events_ack', 'reply_route', 'feedback_action'],
  },
  a2aProtocol: {
    status: 'verified',
    agentCard: {
      name: 'reactor-a2a-agent',
      interfaceCount: 2,
      interfaceProtocolBindings: ['jsonrpc', 'http'],
      interfaceProtocolVersions: ['1.0'],
      wellKnownPath: '/.well-known/agent-card.json',
    },
    diagnostics: {
      sdkAvailable: true,
      protocolVersion: '1.0',
      path: '/api/a2a/tasks',
    },
    protocolNegotiation: {
      requestHeader: 'A2A-Version',
      requestedVersion: '1.0',
      responseVersion: '1.0',
      majorMinorOnly: true,
      agentCardVersionsChecked: true,
      serverGeneratedTaskIds: true,
      sdkFastApiSurface: true,
      telemetryInstrumentation: 'otel',
    },
    taskApi: {
      status: 'verified',
      taskStatus: 'completed',
      path: '/api/a2a/tasks',
    },
    operationalEvidence: {
      auditRecorded: true,
      idempotencyEnforced: true,
      telemetryEnabled: true,
      pushOutboxRouted: true,
    },
    secretFree: true,
    tlsRequired: true,
  },
  dependencyWarnings: {
    status: 'review_required',
    source: 'memoryMaintenanceLifecycle.dependencyWarnings',
    warningReports: ['hardening_suite'],
    warningReviewRequired: false,
    checkedPackages: ['langmem', 'trustcall', 'langgraph'],
    installedVersions: {
      langmem: '0.0.30',
      trustcall: '0.0.39',
      langgraph: '1.2.7',
    },
    directPins: {
      langmem: '==0.0.30',
      langgraph: '==1.2.7',
    },
    pinSource: 'pyproject.toml',
    findings: [
      {
        package: 'trustcall',
        module: 'trustcall._base',
        deprecatedImport: 'langgraph.constants.Send',
        replacement: 'langgraph.types.Send',
        severity: 'warning',
      },
    ],
    findingCount: 1,
    reviewCommand: 'uv pip show langmem trustcall langgraph',
    remediationCommand: 'monitor upstream trustcall/langmem compatibility',
    resolverCheck: {
      status: 'no_lockfile_changes',
      command: 'uv lock --upgrade-package langmem --upgrade-package trustcall --upgrade-package langgraph --dry-run',
      latestKnownFrom: 'resolver',
    },
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
}

const blockedReadiness: DashboardReleaseReadinessSummary = {
  ...passedReadiness,
  status: 'blocked',
  syncedAt: '2026-07-10T00:05:00Z',
  summary: {
    blocked: 1,
    failed: 0,
    passed: 2,
    skipped: 0,
    total: 3,
  },
  failureSummary: 'release_readiness status=blocked\npreflight: status=blocked failure=release smoke preflight blocked by missing environment',
  readyNextActionIds: [
    'set-release-smoke-preflight-env',
    'run-live-backend-provider-local-contract',
  ],
  nextActionStates: {
    'set-release-smoke-preflight-env': 'ready',
    'run-live-backend-provider-local-contract': 'ready',
  },
  recommendedTag: null,
  recommendedVersionBump: 'none',
  minorEligible: false,
  blockingReports: ['smoke_run', 'release_readiness', 'langsmith_eval_sync', 'backend_provider_integration'],
  warningReports: ['hardening_suite'],
  tagRecommendation: {
    status: 'defer',
    eligible: false,
    latestTag: 'v1.1.0',
    recommendedTagPattern: 'none',
    recommendedVersionBump: 'none',
    minorEligible: false,
    passedReports: ['release_evidence', 'hardening_suite', 'langsmith_eval_sync'],
    warningReports: ['hardening_suite'],
    missingEnv: [
      'REACTOR_A2A_API_KEY',
      'REACTOR_A2A_BASE_URL',
      'REACTOR_SLACK_BOT_TOKEN',
      'REACTOR_SLACK_SIGNING_SECRET',
    ],
    preflightEnvFileCommand: 'uv run reactor-release-smoke-run --env-file reports/release/release-smoke-preflight.local.env --preflight-only',
    releaseSmokeEnvFileCommand: 'uv run reactor-release-smoke-run --env-file reports/release/release-smoke-preflight.local.env --report-file reports/release-smoke-run.json',
    nextAction: 'set release smoke preflight environment before tagging',
    reason: 'release readiness is blocked',
  },
  items: [
    {
      name: 'preflight',
      status: 'blocked',
      ok: false,
      artifact: 'reports/release/release-smoke-preflight.local.json',
      mode: 'release_smoke_preflight',
      failure: 'release smoke preflight blocked by missing environment',
      preflightMissingEnv: [
        'REACTOR_A2A_API_KEY',
        'REACTOR_A2A_BASE_URL',
        'REACTOR_SLACK_BOT_TOKEN',
        'REACTOR_SLACK_SIGNING_SECRET',
      ],
      nextActions: [
        {
          id: 'set-release-smoke-preflight-env',
          label: 'Set release smoke preflight environment before tagging',
          command: 'uv run reactor-release-smoke-run --env-file reports/release/release-smoke-preflight.local.env --preflight-only',
          missingEnv: [
            'REACTOR_A2A_API_KEY',
            'REACTOR_A2A_BASE_URL',
            'REACTOR_SLACK_BOT_TOKEN',
            'REACTOR_SLACK_SIGNING_SECRET',
          ],
        },
      ],
    },
  ],
  gates: [
    { id: 'rag', status: 'warning' },
    { id: 'feedback', status: 'passed' },
    { id: 'langsmith', status: 'passed' },
    { id: 'slack', status: 'blocked' },
    { id: 'a2a', status: 'blocked' },
    { id: 'provider', status: 'passed' },
  ],
}

function renderCockpit(
  readiness: DashboardReleaseReadinessSummary | null,
  view: ReleaseCockpitView = 'all',
) {
  return render(
    <MemoryRouter>
      <ReleaseCockpit readiness={readiness} view={view} />
    </MemoryRouter>,
  )
}

describe('ReleaseCockpit', () => {
  it('classifies top-level panels for the release operations views', () => {
    const { container } = renderCockpit(passedReadiness, 'evidence')
    const cockpit = container.querySelector('.release-cockpit')

    expect(cockpit).toHaveClass('release-cockpit--evidence')
    expect(cockpit?.querySelectorAll('[data-release-section="decision"]')?.length).toBeGreaterThan(0)
    expect(cockpit?.querySelectorAll('[data-release-section="boundary"]')?.length).toBeGreaterThan(0)
    expect(cockpit?.querySelectorAll('[data-release-section="evidence"]')?.length).toBeGreaterThan(0)
    cockpit?.querySelectorAll('[data-release-section="evidence"]').forEach((panel) => {
      expect(panel.tagName).toBe('DETAILS')
      expect(panel).not.toHaveAttribute('open')
    })
    expect(screen.getByLabelText('dashboard.release.decisionBrief.title'))
      .toHaveAttribute('data-release-section', 'decision')
    expect(screen.getByLabelText('dashboard.release.productBoundary.title'))
      .toHaveAttribute('data-release-section', 'boundary')
    expect(screen.queryByLabelText('dashboard.release.gatesLabel')).not.toBeInTheDocument()
    expect(screen.getByLabelText('dashboard.release.langsmith.title'))
      .toHaveAttribute('data-release-section', 'evidence')
  })

  it('renders v1.1 release readiness and gate labels', () => {
    renderCockpit(passedReadiness)

    expect(screen.getByText('dashboard.release.title')).toBeInTheDocument()
    expect(screen.getByText('v1.1.0')).toBeInTheDocument()
    expect(screen.getByText('dashboard.release.versionBumpValue.minor')).toBeInTheDocument()
    expect(screen.getAllByText('v1.0.14')).toHaveLength(3)
    const decisionBrief = screen.getByLabelText('dashboard.release.decisionBrief.title')
    expect(decisionBrief).toHaveTextContent('dashboard.release.decisionBrief.nextAction')
    expect(decisionBrief).toHaveTextContent('dashboard.release.decisionBrief.reviewWarningsThenVerify')
    expect(decisionBrief).toHaveTextContent('dashboard.release.decisionBrief.noOwningSurface')
    expect(decisionBrief).toHaveTextContent('v1.0.14')
    expect(within(decisionBrief).getByRole('button', { name: 'common.copy.aria' })).toBeInTheDocument()
    expect(decisionBrief.querySelector('.release-cockpit__decision-technical')).not.toHaveAttribute('open')
    expect(screen.getByLabelText('dashboard.release.recommendation.title')).not.toHaveAttribute('open')
    expect(screen.getByLabelText('dashboard.release.warningReviewHandoff.title')).not.toHaveAttribute('open')
    expect(screen.getByLabelText('dashboard.release.localGates.title')).not.toHaveAttribute('open')
    expect(screen.getAllByText('Smoke Run')).toHaveLength(2)
    expect(screen.getAllByText('Release Evidence')).toHaveLength(2)
    expect(screen.getAllByText('Hardening Suite')).toHaveLength(2)
    expect(screen.getAllByText('Langsmith Eval Sync').length).toBeGreaterThanOrEqual(2)
    const recommendation = screen.getByLabelText('dashboard.release.recommendation.title')
    const recommendationLangsmithLinks = within(recommendation).getAllByRole('link', { name: 'Open Langsmith Eval Sync' })
    expect(recommendationLangsmithLinks).toHaveLength(2)
    recommendationLangsmithLinks.forEach((link) => {
      expect(link).toHaveAttribute('href', RELEASE_WORKFLOW_GATE_PATHS.langsmith)
    })
    expect(screen.getByText('dashboard.release.localGates.title')).toBeInTheDocument()
    expect(screen.getByText('dashboard.release.localGates.ciDisabled')).toBeInTheDocument()
    expect(screen.getByText('dashboard.release.localGates.evidenceReady')).toBeInTheDocument()
    expect(screen.getByText('dashboard.release.localGates.localEvidence')).toBeInTheDocument()
    expect(screen.getByText('dashboard.release.localGates.cleanMainUnverified')).toBeInTheDocument()
    expect(screen.getByLabelText('dashboard.release.localGates.title')).toHaveTextContent(
      'dashboard.release.localGates.latestVerifiedTag',
    )
    expect(screen.getByText('dashboard.release.localGates.noProgressTags')).toBeInTheDocument()
    expect(document.getElementById(RELEASE_COCKPIT_ANCHOR_ID)).toBeInTheDocument()
    expect(RELEASE_WORKFLOW_PATHS_BY_ID.cockpit).toBe(`/release#${RELEASE_COCKPIT_ANCHOR_ID}`)
    expect(screen.getByText('pnpm test -- --reporter=dot')).toBeInTheDocument()
    expect(screen.getByText('pnpm lint --quiet')).toBeInTheDocument()
    expect(screen.getByText('pnpm build')).toBeInTheDocument()
    expect(screen.getByText('pnpm verify:admin-api')).toBeInTheDocument()
    expect(screen.getByText('git status --short --branch')).toBeInTheDocument()
    expect(screen.getByText('git tag --points-at HEAD')).toBeInTheDocument()
    const releaseHandoff = screen.getByLabelText('dashboard.release.handoff.title')
    expect(within(releaseHandoff).getByRole('link', { name: 'Open Langsmith Eval Sync' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.langsmith,
    )
    expect(screen.queryByText('review release readiness warnings, then verify clean worktree and choose the next minor version tag')).not.toBeInTheDocument()
    expect(screen.getAllByText('uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json')).toHaveLength(3)
    const warningReviewHandoff = screen.getByLabelText('dashboard.release.warningReviewHandoff.title')
    expect(warningReviewHandoff).toHaveTextContent('dashboard.release.warningReviewHandoff.reviewRequired')
    expect(warningReviewHandoff).toHaveTextContent('hardening_suite')
    expect(warningReviewHandoff).toHaveTextContent('uv pip show langmem trustcall langgraph')
    expect(warningReviewHandoff).toHaveTextContent('monitor upstream trustcall/langmem compatibility')
    expect(warningReviewHandoff).toHaveTextContent('dashboard.release.decisionBrief.reviewWarningsThenVerify')
    expect(screen.getAllByRole('button', { name: 'common.copy.aria' })).toHaveLength(10)
    expect(screen.getByText('dashboard.release.productBoundary.title')).toBeInTheDocument()
    expect(screen.getByText('rag_ingest_to_feedback_eval_langsmith_readiness')).toBeInTheDocument()
    expect(screen.getAllByText('확인 자료 1개 연결됨').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('langsmith_eval_sync')).not.toBeInTheDocument()
    expect(screen.getByText('dashboard.release.productBoundary.noneMissing')).toBeInTheDocument()
    const boundaryOpsQueue = screen.getByLabelText('dashboard.release.productBoundaryOps.title')
    expect(boundaryOpsQueue).toHaveTextContent('dashboard.release.productBoundaryOps.description')
    expect(within(boundaryOpsQueue).getByRole('link', { name: /dashboard\.release\.productBoundaryOps\.ingestTitle/ })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
    )
    expect(within(boundaryOpsQueue).getByRole('link', { name: /dashboard\.release\.productBoundaryOps\.citedAnswerTitle/ })).toHaveAttribute(
      'href',
      RELEASE_RAG_ANSWER_CONTRACT_PATH,
    )
    expect(within(boundaryOpsQueue).getByRole('link', { name: /dashboard\.release\.productBoundaryOps\.feedbackTitle/ })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.feedback,
    )
    expect(within(boundaryOpsQueue).getByRole('link', { name: /dashboard\.release\.productBoundaryOps\.langsmithTitle/ })).toHaveAttribute(
      'href',
      RELEASE_LANGSMITH_SYNC_PATH,
    )
    expect(boundaryOpsQueue).toHaveTextContent('langchain-postgres / PGVector')
    expect(boundaryOpsQueue).toHaveTextContent('rag_ingestion_lifecycle, research_answer_contract')
    expect(boundaryOpsQueue).toHaveTextContent('manifest_ids')
    expect(boundaryOpsQueue).toHaveTextContent('case_rag_candidate_grounded_citation')
    expect(boundaryOpsQueue).toHaveTextContent('required: 4')
    expect(boundaryOpsQueue).toHaveTextContent('reactor-release-regression')
    expect(boundaryOpsQueue).toHaveTextContent('regression: 12')
    expect(within(boundaryOpsQueue).getAllByText('dashboard.release.productBoundaryOps.evidenceCount')).toHaveLength(4)
    within(boundaryOpsQueue).getAllByText('dashboard.release.productBoundaryOps.evidenceCount').forEach((summary) => {
      expect(summary.closest('details')).not.toHaveAttribute('open')
    })
    expect(screen.getByText(/LANGSMITH_API_KEY or REACTOR_OBSERVABILITY_LANGSMITH_API_KEY/)).toBeInTheDocument()
    expect(screen.getAllByText('REACTOR_A2A_BASE_URL').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('REACTOR_SLACK_BOT_TOKEN, REACTOR_SLACK_SIGNING_SECRET')).toBeInTheDocument()
    expect(screen.getByText('dashboard.release.warningList.title')).toBeInTheDocument()
    expect(screen.getByText('dashboard.release.warningList.count')).toBeInTheDocument()
    expect(screen.getByText('review LangMem/trustcall/LangGraph dependency update')).toBeInTheDocument()
    expect(screen.getByText('dashboard.release.warningEvidence.title')).toBeInTheDocument()
    expect(screen.getAllByText('review_required')).toHaveLength(2)
    expect(screen.getAllByText('memoryMaintenanceLifecycle.dependencyWarnings')).toHaveLength(2)
    expect(screen.getAllByText('hardening_suite').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('langmem, trustcall, langgraph')).toBeInTheDocument()
    expect(screen.getAllByText('trustcall / trustcall._base / langgraph.constants.Send -> langgraph.types.Send / warning')).toHaveLength(2)
    expect(screen.getByText('langmem: 0.0.30, trustcall: 0.0.39, langgraph: 1.2.7')).toBeInTheDocument()
    expect(screen.getByText('langmem: ==0.0.30, langgraph: ==1.2.7 dashboard.release.warningEvidence.from pyproject.toml')).toBeInTheDocument()
    expect(screen.getAllByText('uv pip show langmem trustcall langgraph')).toHaveLength(3)
    expect(screen.getByText(/no_lockfile_changes \/ resolver \/ uv lock --upgrade-package langmem/)).toBeInTheDocument()
    expect(screen.getAllByText('monitor upstream trustcall/langmem compatibility')).toHaveLength(3)
    expect(screen.getAllByText('dashboard.release.gates.rag').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('dashboard.release.gates.feedback').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('dashboard.release.gates.langsmith').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('reactor-release-regression')).toBeInTheDocument()
    expect(screen.getByText('regression: 12')).toBeInTheDocument()
    expect(screen.getByText('Client.create_dataset/create_example')).toBeInTheDocument()
    expect(screen.getByText(/"datasetApi": "Client.create_dataset"/)).toBeInTheDocument()
    expect(screen.getByText(/"secretScan": "passed"/)).toBeInTheDocument()
    expect(screen.getByText(/"requiredMetadata"/)).toBeInTheDocument()
    expect(screen.getAllByText('example-1, example-2').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('case-1, case-2').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('dashboard.release.rag.title')).toBeInTheDocument()
    expect(screen.getByText('langchain-postgres / PGVector')).toBeInTheDocument()
    expect(screen.getByText('provider-managed embeddings with ACL-aware manifests')).toBeInTheDocument()
    expect(screen.getByText('manifest_ids')).toBeInTheDocument()
    expect(screen.getByText('rag_ingestion_lifecycle, research_answer_contract')).toBeInTheDocument()
    expect(screen.getByText('/api/admin/rag/diagnostics, /api/admin/rag/candidates')).toBeInTheDocument()
    expect(screen.getByText('case_rag_ingest_poisoning_guard')).toBeInTheDocument()
    expect(screen.getByText('dashboard.release.feedback.title')).toBeInTheDocument()
    expect(screen.getByText('feedback inbox reviewed and promoted into regression coverage')).toBeInTheDocument()
    expect(screen.getAllByText('case_rag_candidate_grounded_citation').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('release-gate, grounded-citation')).toBeInTheDocument()
    expect(screen.getByText('positive: 3, negative: 1')).toBeInTheDocument()
    expect(screen.getByText('slack: 2, admin: 2')).toBeInTheDocument()
    expect(screen.getByText('rag: 4')).toBeInTheDocument()
    expect(screen.getByText('required: 4')).toBeInTheDocument()
    expect(screen.getByText('dashboard.release.smoke.title')).toBeInTheDocument()
    const smokePanel = screen.getByLabelText('dashboard.release.smoke.title')
    expect(within(smokePanel).getByRole('link', { name: 'dashboard.release.smoke.openSlack' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.slack,
    )
    expect(within(smokePanel).getByRole('link', { name: 'dashboard.release.smoke.openA2a' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.a2a,
    )
    expect(screen.getByText('native-slack-gateway')).toBeInTheDocument()
    expect(screen.getByText('socket-mode')).toBeInTheDocument()
    expect(screen.getByText('chat.postMessage')).toBeInTheDocument()
    expect(screen.getAllByText('events_ack, reply_route, feedback_action')).toHaveLength(2)
    expect(screen.getByText('reactor-a2a-agent')).toBeInTheDocument()
    expect(screen.getByText('jsonrpc, http')).toBeInTheDocument()
    expect(screen.getAllByText('verified / completed / /api/a2a/tasks')).toHaveLength(2)
    expect(screen.getByText('1.0 / A2A-Version / 1.0')).toBeInTheDocument()
    expect(screen.getByText(/dashboard.release.smoke.audit: Yes/)).toBeInTheDocument()
    const smokeChecklist = screen.getByLabelText('dashboard.release.smoke.checklistTitle')
    expect(smokeChecklist).toHaveTextContent('dashboard.release.smoke.slackChecklist')
    expect(smokeChecklist).toHaveTextContent('events_ack, reply_route, feedback_action')
    expect(smokeChecklist).toHaveTextContent('dashboard.release.smoke.a2aChecklist')
    expect(smokeChecklist).toHaveTextContent('verified / completed / /api/a2a/tasks')
    expect(smokeChecklist).toHaveTextContent('dashboard.release.smoke.providerChecklist')
    expect(smokeChecklist).toHaveTextContent('required_env, tracing_config, chat_model_invoke, usage_metadata')
    expect(smokeChecklist).toHaveTextContent('dashboard.release.smoke.commandChecklist')
    expect(smokeChecklist).toHaveTextContent('uv run reactor-release-smoke-run --readiness-output reports/release-readiness.json')
    expect(screen.getByText('dashboard.release.provider.title')).toBeInTheDocument()
    const providerPanel = screen.getByLabelText('dashboard.release.provider.title')
    expect(within(providerPanel).getByRole('link', { name: 'dashboard.release.provider.openProvider' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.provider,
    )
    expect(screen.getByText('ollama')).toBeInTheDocument()
    expect(screen.getByText('gemma4:12b')).toBeInTheDocument()
    expect(within(providerPanel).getByText('dashboard.release.provider.localProviderNoKey')).toBeInTheDocument()
    expect(within(providerPanel).queryByText('OPENAI_API_KEY')).not.toBeInTheDocument()
    expect(screen.getByText(
      'dashboard.release.provider.inputTokens: 20, dashboard.release.provider.outputTokens: 63, dashboard.release.provider.totalTokens: 83',
    )).toBeInTheDocument()
    expect(screen.getByText('LangChain AIMessage.usage_metadata')).toBeInTheDocument()
    expect(screen.getAllByText('required_env, tracing_config, chat_model_invoke, usage_metadata')).toHaveLength(2)
  }, 10000)

  it('keeps release warning transport data behind a closed technical disclosure', async () => {
    const user = userEvent.setup()
    renderCockpit(passedReadiness)

    const releaseWarnings = screen.getByLabelText('dashboard.release.warningList.title')
    await user.click(within(releaseWarnings).getByText('dashboard.release.warningList.title'))

    const warningSummary = releaseWarnings.querySelector('.release-cockpit__warning-operator-grid')
    expect(warningSummary).toHaveTextContent('dashboard.release.warningList.dependencyTitle')
    expect(warningSummary).toHaveTextContent('dashboard.release.warningList.dependencySummary')
    expect(warningSummary).not.toHaveTextContent('hardening_suite')
    expect(warningSummary).not.toHaveTextContent('trustcall')

    const warningTechnical = releaseWarnings.querySelector('.release-cockpit__warning-technical')
    expect(warningTechnical).not.toHaveAttribute('open')
    await user.click(within(warningTechnical as HTMLElement).getByText('common.technicalDetails'))
    expect(warningTechnical).toHaveAttribute('open')
    expect(warningTechnical).toHaveTextContent('hardening_suite')
    expect(warningTechnical).toHaveTextContent('uv pip show langmem trustcall langgraph')

    const dependencyWarnings = screen.getByLabelText('dashboard.release.warningEvidence.title')
    await user.click(within(dependencyWarnings).getByText('dashboard.release.warningEvidence.title'))

    const dependencySummary = dependencyWarnings.querySelector('.release-cockpit__warning-operator-grid')
    expect(dependencySummary).toHaveTextContent('dashboard.release.warningEvidence.dependencyTitle')
    expect(dependencySummary).toHaveTextContent('dashboard.release.warningEvidence.operatorSummaryWithCount')
    expect(dependencySummary).not.toHaveTextContent('memoryMaintenanceLifecycle.dependencyWarnings')

    const dependencyTechnical = dependencyWarnings.querySelector('.release-cockpit__warning-technical')
    expect(dependencyTechnical).not.toHaveAttribute('open')
    await user.click(within(dependencyTechnical as HTMLElement).getByText('common.technicalDetails'))
    expect(dependencyTechnical).toHaveAttribute('open')
    expect(dependencyTechnical).toHaveTextContent('memoryMaintenanceLifecycle.dependencyWarnings')
    expect(dependencyTechnical).toHaveTextContent('uv lock --upgrade-package langmem')
  })

  it('fails the displayed decision closed while warning review is still required', () => {
    const { container } = renderCockpit({
      ...passedReadiness,
      status: 'passed',
    })

    expect(container.querySelector('.release-cockpit__status'))
      .toHaveTextContent('dashboard.release.status.eligible_with_warnings')
  })

  it('fails closed when release evidence has no generation timestamp', () => {
    renderCockpit({ ...passedReadiness, syncedAt: null })

    expect(screen.getByRole('status')).toHaveTextContent('dashboard.release.status.blocked')
    expect(screen.getByLabelText('dashboard.release.summaryLabel')).toHaveTextContent(
      'dashboard.release.currentEvidenceRequired',
    )
    expect(screen.queryByLabelText('dashboard.release.recommendation.title')).not.toBeInTheDocument()
    expect(screen.getByLabelText('dashboard.release.decisionBrief.title')).toHaveTextContent(
      'dashboard.release.decisionBrief.evidenceNotCurrent',
    )
    expect(screen.getByText('dashboard.release.decisionBrief.notReported')).toBeInTheDocument()
  })

  it('keeps commit and input-hash evidence behind a closed disclosure', async () => {
    const user = userEvent.setup()
    renderCockpit(passedReadiness)

    const summary = screen.getByText('dashboard.release.decisionBrief.showProvenance')
    const disclosure = summary.closest('details')
    expect(disclosure).not.toHaveAttribute('open')

    await user.click(summary)

    expect(disclosure).toHaveAttribute('open')
    expect(screen.getAllByText('a'.repeat(40)).length).toBeGreaterThan(0)
    expect(screen.getByText('b'.repeat(64))).toBeInTheDocument()
  })

  it('keeps verdict metrics out of workflow and evidence views', () => {
    const boundary = renderCockpit(passedReadiness, 'boundary')

    expect(screen.queryByLabelText('dashboard.release.summaryLabel')).not.toBeInTheDocument()
    expect(screen.queryByText('dashboard.release.title')).not.toBeInTheDocument()
    expect(boundary.container.querySelector('.release-cockpit')).toHaveAttribute(
      'aria-label',
      'releaseOperations.views.boundary',
    )

    boundary.unmount()
    const evidence = renderCockpit(passedReadiness, 'evidence')

    expect(screen.queryByLabelText('dashboard.release.summaryLabel')).not.toBeInTheDocument()
    expect(screen.queryByText('dashboard.release.title')).not.toBeInTheDocument()
    expect(evidence.container.querySelector('.release-cockpit')).toHaveAttribute(
      'aria-label',
      'releaseOperations.views.evidence',
    )
  })

  it('links release gates and blocker reports to their owning operations surfaces', () => {
    renderCockpit(blockedReadiness)

    const decisionBrief = screen.getByLabelText('dashboard.release.decisionBrief.title')
    expect(decisionBrief).toHaveTextContent('dashboard.release.decisionBrief.reviewReportedAction')
    expect(within(decisionBrief).getByRole('link', { name: 'dashboard.release.decisionBrief.openSurface' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.integrations,
    )
    expect(decisionBrief).toHaveTextContent('v1.1.0')
    expect(screen.getByText('dashboard.release.localGates.evidenceIncomplete')).toBeInTheDocument()

    const aggregateDiagnostics = screen.getByLabelText('dashboard.release.aggregateDiagnostics.title')
    expect(aggregateDiagnostics).toHaveAttribute('open')
    expect(aggregateDiagnostics).toHaveTextContent('dashboard.release.aggregateDiagnostics.summary')
    expect(aggregateDiagnostics).toHaveTextContent('dashboard.release.aggregateDiagnostics.summaryValue')
    expect(aggregateDiagnostics).toHaveTextContent('dashboard.release.aggregateDiagnostics.failureSummary')
    expect(aggregateDiagnostics).toHaveTextContent('release_readiness status=blocked')
    expect(aggregateDiagnostics).toHaveTextContent('dashboard.release.aggregateDiagnostics.readyActions')
    expect(aggregateDiagnostics).toHaveTextContent('set-release-smoke-preflight-env')
    expect(aggregateDiagnostics).toHaveTextContent('run-live-backend-provider-local-contract')
    expect(aggregateDiagnostics).toHaveTextContent('dashboard.release.aggregateDiagnostics.items')
    expect(within(aggregateDiagnostics).getAllByRole('link', { name: 'preflight' })[0]).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.integrations,
    )
    expect(aggregateDiagnostics).toHaveTextContent('reports/release/release-smoke-preflight.local.json')
    expect(aggregateDiagnostics).toHaveTextContent('release smoke preflight blocked by missing environment')
    expect(aggregateDiagnostics).toHaveTextContent('REACTOR_A2A_API_KEY, REACTOR_A2A_BASE_URL, REACTOR_SLACK_BOT_TOKEN, REACTOR_SLACK_SIGNING_SECRET')
    expect(aggregateDiagnostics).toHaveTextContent('Set release smoke preflight environment before tagging')
    expect(aggregateDiagnostics).toHaveTextContent('uv run reactor-release-smoke-run --env-file reports/release/release-smoke-preflight.local.env --preflight-only')
    expect(within(aggregateDiagnostics).getAllByRole('button', { name: 'common.copy.aria' }).length).toBeGreaterThanOrEqual(1)

    const actionHandoff = within(aggregateDiagnostics).getByLabelText(
      'dashboard.release.aggregateDiagnostics.actionHandoff',
    )
    expect(actionHandoff).toHaveTextContent('set-release-smoke-preflight-env')
    expect(actionHandoff).toHaveTextContent('ready')
    expect(actionHandoff).toHaveTextContent('Set release smoke preflight environment before tagging')
    expect(within(actionHandoff).getByRole('link', { name: 'preflight' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.integrations,
    )
    expect(actionHandoff).toHaveTextContent('REACTOR_A2A_API_KEY, REACTOR_A2A_BASE_URL, REACTOR_SLACK_BOT_TOKEN, REACTOR_SLACK_SIGNING_SECRET')
    expect(actionHandoff).toHaveTextContent('uv run reactor-release-smoke-run --env-file reports/release/release-smoke-preflight.local.env --preflight-only')
    expect(within(actionHandoff).getByRole('button', { name: 'common.copy.aria' })).toBeInTheDocument()

    const remediationQueue = screen.getByLabelText('dashboard.release.blockerQueue.title')
    expect(remediationQueue).toBeInTheDocument()
    expect(within(remediationQueue).getByText('dashboard.release.blockerQueue.count')).toBeInTheDocument()
    expect(within(remediationQueue).getAllByText('smoke_run')).toHaveLength(3)
    expect(
      within(remediationQueue).getByRole('link', { name: /smoke_rundashboard\.release\.gates\.slack/ }),
    ).toHaveAttribute('href', RELEASE_WORKFLOW_GATE_PATHS.slack)
    expect(
      within(remediationQueue).getByRole('link', { name: /smoke_rundashboard\.release\.gates\.a2a/ }),
    ).toHaveAttribute('href', RELEASE_WORKFLOW_GATE_PATHS.a2a)
    expect(
      within(remediationQueue).getByRole('link', { name: /smoke_rundashboard\.release\.gates\.provider/ }),
    ).toHaveAttribute('href', RELEASE_WORKFLOW_GATE_PATHS.provider)
    expect(within(remediationQueue).getByText('dashboard.release.gateRemediation.slack')).toBeInTheDocument()
    expect(within(remediationQueue).getByText('dashboard.release.gateRemediation.a2a')).toBeInTheDocument()
    expect(within(remediationQueue).getByText('dashboard.release.gateRemediation.provider')).toBeInTheDocument()
    const queueStepNumbers = Array.from(remediationQueue.querySelectorAll('.release-cockpit__blocker-step')).map((node) =>
      node.textContent,
    )
    expect(queueStepNumbers).toEqual([
      String(RELEASE_WORKFLOW_GATE_STEP_NUMBERS.slack),
      String(RELEASE_WORKFLOW_GATE_STEP_NUMBERS.a2a),
      String(RELEASE_WORKFLOW_GATE_STEP_NUMBERS.provider),
      String(RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit),
      String(RELEASE_WORKFLOW_GATE_STEP_NUMBERS.langsmith),
      String(RELEASE_WORKFLOW_GATE_STEP_NUMBERS.provider),
    ])
    expect(
      within(remediationQueue).getByRole('link', { name: /release_readinesscommandPalette\.actions\.releaseCockpit/ }),
    ).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.cockpit)
    expect(
      within(remediationQueue).getByRole('link', { name: /langsmith_eval_synccommandPalette\.actions\.langsmithSync/ }),
    ).toHaveAttribute('href', RELEASE_LANGSMITH_SYNC_PATH)
    expect(
      within(remediationQueue).getByRole('link', { name: /backend_provider_integrationcommandPalette\.actions\.providerSmoke/ }),
    ).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.provider)
    expect(within(remediationQueue).getAllByText('dashboard.release.blockerQueue.openOwningSurface'))
      .toHaveLength(3)

    const smokeHandoff = screen.getByLabelText('dashboard.release.smokeHandoff.title')
    expect(smokeHandoff).toHaveTextContent('dashboard.release.smokeHandoff.blocked')
    expect(smokeHandoff).toHaveTextContent('REACTOR_A2A_API_KEY, REACTOR_A2A_BASE_URL, REACTOR_SLACK_BOT_TOKEN, REACTOR_SLACK_SIGNING_SECRET')
    expect(within(smokeHandoff).getByRole('link', { name: 'dashboard.release.smokeHandoff.openIntegrationSmoke' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.integrations,
    )
    const smokeBlockerBreakdown = within(smokeHandoff).getByRole('list', {
      name: 'dashboard.release.smokeHandoff.blockerBreakdown',
    })
    expect(smokeBlockerBreakdown).toHaveTextContent('dashboard.release.gates.slack')
    expect(smokeBlockerBreakdown).toHaveTextContent('dashboard.release.smokeHandoff.slackDesc')
    expect(smokeBlockerBreakdown).toHaveTextContent('REACTOR_SLACK_BOT_TOKEN, REACTOR_SLACK_SIGNING_SECRET')
    expect(smokeBlockerBreakdown).toHaveTextContent('dashboard.release.gates.a2a')
    expect(smokeBlockerBreakdown).toHaveTextContent('dashboard.release.smokeHandoff.a2aDesc')
    expect(smokeBlockerBreakdown).toHaveTextContent('REACTOR_A2A_BASE_URL, REACTOR_A2A_API_KEY')
    expect(within(smokeBlockerBreakdown).getByRole('link', { name: /dashboard\.release\.gates\.slack/ }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_GATE_PATHS.slack)
    expect(within(smokeBlockerBreakdown).getByRole('link', { name: /dashboard\.release\.gates\.a2a/ }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_GATE_PATHS.a2a)
    const smokeBlockerSteps = Array.from(
      smokeBlockerBreakdown.querySelectorAll('.release-cockpit__blocker-step'),
    ).map((node) => node.textContent)
    expect(smokeBlockerSteps).toEqual([
      String(RELEASE_WORKFLOW_GATE_STEP_NUMBERS.slack),
      String(RELEASE_WORKFLOW_GATE_STEP_NUMBERS.a2a),
    ])
    expect(smokeHandoff).toHaveTextContent('uv run reactor-release-smoke-run --env-file reports/release/release-smoke-preflight.local.env --preflight-only')
    expect(smokeHandoff).toHaveTextContent('uv run reactor-release-smoke-run --env-file reports/release/release-smoke-preflight.local.env --report-file reports/release-smoke-run.json')

    expect(screen.queryByLabelText('dashboard.release.gatesLabel')).not.toBeInTheDocument()
  })

  it('keeps aggregate diagnostics collapsed unless readiness is blocked', () => {
    renderCockpit({
      ...passedReadiness,
      summary: { blocked: 0, failed: 0, passed: 4, skipped: 0, total: 4 },
    })

    expect(screen.getByLabelText('dashboard.release.aggregateDiagnostics.title')).not.toHaveAttribute('open')
  })

  it('summarizes minor boundary gate readiness inside the product boundary card', () => {
    renderCockpit({
      ...blockedReadiness,
      productCapabilityBoundary: {
        ...passedReadiness.productCapabilityBoundary!,
        status: 'blocked',
        minorEligible: false,
        missingEvidence: [
          'rag_ingestion_lifecycle',
          'slack_gateway_smoke',
          'a2a_protocol',
        ],
      },
    })

    const productBoundary = screen.getByLabelText('dashboard.release.productBoundary.title')
    const checklist = within(productBoundary).getByRole('list', {
      name: 'dashboard.release.productBoundary.checklistTitle',
    })
    const flow = within(productBoundary).getByRole('list', {
      name: 'dashboard.release.productBoundaryFlow.title',
    })
    expect(flow).toHaveTextContent('dashboard.release.productBoundaryFlow.ingest')
    expect(flow).toHaveTextContent('dashboard.release.productBoundaryFlow.citedAnswer')
    expect(flow).toHaveTextContent('dashboard.release.productBoundaryFlow.feedback')
    expect(flow).toHaveTextContent('dashboard.release.productBoundaryFlow.langsmith')
    expect(flow).toHaveTextContent('dashboard.release.productBoundaryFlow.slack')
    expect(flow).toHaveTextContent('dashboard.release.productBoundaryFlow.a2a')
    expect(flow).toHaveTextContent('dashboard.release.productBoundaryFlow.provider')
    expect(flow).toHaveTextContent('dashboard.release.productBoundaryFlow.readiness')
    expect(within(flow).getByRole('link', { name: /dashboard\.release\.productBoundaryFlow\.citedAnswer/ }))
      .toHaveAttribute('href', RELEASE_RAG_ANSWER_CONTRACT_PATH)
    expect(within(flow).getByRole('link', { name: /dashboard\.release\.productBoundaryFlow\.readiness/ }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.cockpit)
    expect(checklist).toHaveTextContent('dashboard.release.gates.rag')
    expect(checklist).toHaveTextContent('dashboard.release.gates.feedback')
    expect(checklist).toHaveTextContent('dashboard.release.gates.langsmith')
    expect(checklist).toHaveTextContent('dashboard.release.gates.slack')
    expect(checklist).toHaveTextContent('dashboard.release.gates.a2a')
    expect(checklist).toHaveTextContent('dashboard.release.gates.provider')
    expect(checklist).toHaveTextContent('dashboard.release.gateStatus.warning')
    expect(checklist).toHaveTextContent('dashboard.release.gateStatus.blocked')
    expect(within(checklist).getByRole('link', { name: /dashboard\.release\.gates\.rag/ })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.rag,
    )
    expect(within(checklist).getByRole('link', { name: /dashboard\.release\.gates\.slack/ })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.slack,
    )
    expect(within(checklist).getByRole('link', { name: /dashboard\.release\.gates\.a2a/ })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.a2a,
    )
  })

  it('keeps the provider smoke handoff visible when provider evidence is missing', () => {
    renderCockpit({
      ...blockedReadiness,
      backendProviderIntegration: null,
      gates: [
        { id: 'rag', status: 'warning' },
        { id: 'feedback', status: 'passed' },
        { id: 'langsmith', status: 'passed' },
        { id: 'slack', status: 'blocked' },
        { id: 'a2a', status: 'blocked' },
        { id: 'provider', status: 'blocked' },
      ],
    })

    const providerPanel = screen.getByLabelText('dashboard.release.provider.title')
    expect(within(providerPanel).getAllByRole('link', { name: 'dashboard.release.provider.openProvider' })[0]).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.provider,
    )
    expect(providerPanel).toHaveTextContent('dashboard.release.provider.missing')
    const providerRemediation = within(providerPanel).getByLabelText('dashboard.release.provider.remediationTitle')
    expect(providerRemediation).toHaveTextContent('dashboard.release.provider.remediationDesc')
    expect(providerRemediation).toHaveTextContent('dashboard.release.provider.provider')
    expect(providerRemediation).toHaveTextContent('dashboard.release.provider.usage')
    expect(within(providerRemediation).getByRole('link', { name: /dashboard\.release\.provider\.openProvider/ }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_GATE_PATHS.provider)
    expect(within(providerRemediation).getByRole('link', { name: /dashboard\.release\.smoke\.openIntegrationSmoke/ }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.integrations)

    const smokeChecklist = screen.getByLabelText('dashboard.release.smoke.checklistTitle')
    expect(smokeChecklist).toHaveTextContent('dashboard.release.smoke.providerChecklist')
    expect(smokeChecklist).toHaveTextContent('dashboard.release.smoke.missing')
  })

  it('requires provider evidence before marking live smoke evidence verified', () => {
    renderCockpit({
      ...passedReadiness,
      backendProviderIntegration: null,
      gates: [
        { id: 'rag', status: 'passed' },
        { id: 'feedback', status: 'passed' },
        { id: 'langsmith', status: 'passed' },
        { id: 'slack', status: 'passed' },
        { id: 'a2a', status: 'passed' },
        { id: 'provider', status: 'blocked' },
      ],
    })

    const smokePanel = screen.getByLabelText('dashboard.release.smoke.title')
    expect(smokePanel).toHaveTextContent('dashboard.release.smoke.needsEvidence')
    expect(smokePanel).not.toHaveTextContent('dashboard.release.smoke.verified')
    expect(screen.getByLabelText('dashboard.release.smoke.checklistTitle'))
      .toHaveTextContent('dashboard.release.smoke.missing')
  })

  it('requires Slack action route evidence before marking live smoke verified', () => {
    renderCockpit({
      ...passedReadiness,
      slackGatewaySmoke: {
        ...passedReadiness.slackGatewaySmoke!,
        status: 'verified',
        feedbackActionRoute: '',
        evalPromotionRoute: '',
      },
    })

    const smokePanel = screen.getByLabelText('dashboard.release.smoke.title')
    const smokeStatus = smokePanel.querySelector('.release-cockpit__smoke-head')
    expect(smokeStatus?.querySelector('.badge-yellow')).toBeInTheDocument()
    expect(smokeStatus?.querySelector('.badge-green')).not.toBeInTheDocument()
    expect(smokePanel).toHaveTextContent('dashboard.release.smoke.needsEvidence')
    expect(smokePanel).not.toHaveTextContent('dashboard.release.smoke.verified')
  })

  it('requires provider usage metadata before marking provider evidence verified', () => {
    renderCockpit({
      ...passedReadiness,
      backendProviderIntegration: {
        ...passedReadiness.backendProviderIntegration!,
        status: 'verified',
        usageMetadata: {
          ...passedReadiness.backendProviderIntegration!.usageMetadata!,
          present: false,
          inputTokens: null,
          outputTokens: null,
          totalTokens: null,
          totalMatchesBreakdown: false,
        },
      },
    })

    const providerPanel = screen.getByLabelText('dashboard.release.provider.title')
    const providerStatus = providerPanel.querySelector('.release-cockpit__provider-head')
    expect(providerStatus?.querySelector('.badge-yellow')).toBeInTheDocument()
    expect(providerStatus?.querySelector('.badge-green')).not.toBeInTheDocument()
    expect(providerPanel).toHaveTextContent('dashboard.release.provider.remediationMissing')
    expect(providerPanel).toHaveTextContent('dashboard.release.provider.usage')
    expect(providerPanel).toHaveTextContent('dashboard.release.provider.tokenCounts')
    expect(providerPanel).toHaveTextContent('dashboard.release.provider.breakdown')
  })

  it('keeps LangSmith sync warning until dataset metadata contract is complete', () => {
    renderCockpit({
      ...passedReadiness,
      langsmithSync: {
        datasetName: 'reactor-release-regression',
        exampleCount: 2,
        caseCount: 2,
        exampleIds: ['example-1', 'example-2'],
        caseIds: ['case-1', 'case-2'],
        metadataCaseIds: [],
        splitCounts: {},
        secretFree: true,
        sdkContract: '',
      },
    })

    const langsmithPanel = screen.getByLabelText('dashboard.release.langsmith.title')
    expect(langsmithPanel.querySelector('.badge-yellow')).toBeInTheDocument()
    expect(langsmithPanel.querySelector('.badge-green')).not.toBeInTheDocument()
    expect(langsmithPanel).toHaveTextContent('dashboard.release.langsmith.missing')
    expect(langsmithPanel).toHaveTextContent('reactor-release-regression')
    expect(langsmithPanel).toHaveTextContent('example-1, example-2')
    expect(langsmithPanel).toHaveTextContent('case-1, case-2')
  })

  it('keeps Slack and A2A smoke handoff visible when live smoke evidence is missing', () => {
    renderCockpit({
      ...blockedReadiness,
      slackGatewaySmoke: null,
      a2aProtocol: null,
      gates: [
        { id: 'rag', status: 'warning' },
        { id: 'feedback', status: 'passed' },
        { id: 'langsmith', status: 'passed' },
        { id: 'slack', status: 'blocked' },
        { id: 'a2a', status: 'blocked' },
        { id: 'provider', status: 'passed' },
      ],
    })

    const smokePanel = screen.getByLabelText('dashboard.release.smoke.title')
    expect(within(smokePanel).getByRole('link', { name: 'dashboard.release.smoke.openSlack' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.slack,
    )
    expect(within(smokePanel).getByRole('link', { name: 'dashboard.release.smoke.openA2a' })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_GATE_PATHS.a2a,
    )
    expect(smokePanel).toHaveTextContent('dashboard.release.smoke.missing')
    expect(screen.getByLabelText('dashboard.release.smoke.checklistTitle')).toHaveTextContent(
      'dashboard.release.smoke.missing',
    )
  })

  it('keeps LangSmith and feedback evidence shells visible when release evidence is missing', () => {
    renderCockpit({
      ...blockedReadiness,
      langsmithSync: null,
      feedbackReviewQueue: null,
      gates: [
        { id: 'rag', status: 'warning' },
        { id: 'feedback', status: 'blocked' },
        { id: 'langsmith', status: 'blocked' },
        { id: 'slack', status: 'blocked' },
        { id: 'a2a', status: 'blocked' },
        { id: 'provider', status: 'passed' },
      ],
    })

    const langsmithPanel = screen.getByLabelText('dashboard.release.langsmith.title')
    expect(langsmithPanel).toHaveTextContent('dashboard.release.langsmith.missing')
    expect(langsmithPanel).toHaveTextContent('dashboard.release.langsmith.dataset')
    expect(langsmithPanel).toHaveTextContent('dashboard.release.langsmith.caseIds')

    const feedbackPanel = screen.getByLabelText('dashboard.release.feedback.title')
    expect(feedbackPanel).toHaveTextContent('dashboard.release.feedback.missing')
    expect(feedbackPanel).toHaveTextContent('dashboard.release.feedback.candidateTag')
    expect(feedbackPanel).toHaveTextContent('dashboard.release.feedback.caseIds')
  })

  it('renders missing evidence state when readiness is not connected', () => {
    renderCockpit(null)

    expect(screen.getAllByText('dashboard.release.status.missing')).toHaveLength(1)
    expect(screen.getByText('dashboard.release.missingEvidence')).toBeInTheDocument()
  })
})

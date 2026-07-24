import type { SearchableRecord } from './lib/searchIndex'

export type ReleaseWorkflowGateId =
  | 'rag'
  | 'feedback'
  | 'langsmith'
  | 'slack'
  | 'a2a'
  | 'provider'

export const RELEASE_DOCUMENT_INGESTION_ANCHOR_ID = 'documents-tabpanel-ingestion'
export const RELEASE_EVAL_REGRESSION_ANCHOR_ID = 'eval-regression'
export const RELEASE_LANGSMITH_SYNC_ANCHOR_ID = 'langsmith-sync-evidence'
export const RELEASE_FEEDBACK_PROMOTION_ANCHOR_ID = 'feedback-promotion'
export const RELEASE_INTEGRATION_SMOKE_ANCHOR_ID = 'release-smoke'
export const RELEASE_SLACK_GATEWAY_ANCHOR_ID = 'slack-gateway-smoke'
export const RELEASE_A2A_PROTOCOL_ANCHOR_ID = 'a2a-protocol-smoke'
export const RELEASE_PROVIDER_SMOKE_ANCHOR_ID = 'provider-smoke'
export const RELEASE_RAG_ANSWER_CONTRACT_ANCHOR_ID = 'rag-answer-contract'
export const RELEASE_RAG_ANSWER_PROBE_ANCHOR_ID = 'rag-answer-probe'
export const RELEASE_COCKPIT_ANCHOR_ID = 'release-cockpit'

export const RELEASE_WORKFLOW_STEPS = [
  {
    id: 'cockpit',
    stepNumber: 1,
    navPath: '/release',
    path: `/release#${RELEASE_COCKPIT_ANCHOR_ID}`,
    titleKey: 'dashboard.releaseWorkflow.cockpit',
    descKey: 'dashboard.releaseWorkflow.cockpitDesc',
    gates: [],
  },
  {
    id: 'ingest',
    stepNumber: 2,
    navPath: '/documents',
    path: `/documents?tab=ingestion#${RELEASE_DOCUMENT_INGESTION_ANCHOR_ID}`,
    titleKey: 'dashboard.releaseWorkflow.ingest',
    descKey: 'dashboard.releaseWorkflow.ingestDesc',
    gates: ['rag'],
  },
  {
    id: 'rag',
    stepNumber: 3,
    navPath: '/rag-cache',
    path: `/rag-cache?tab=rag#${RELEASE_RAG_ANSWER_CONTRACT_ANCHOR_ID}`,
    titleKey: 'dashboard.releaseWorkflow.rag',
    descKey: 'dashboard.releaseWorkflow.ragDesc',
    gates: ['rag'],
  },
  {
    id: 'feedback',
    stepNumber: 4,
    navPath: '/feedback',
    path: `/feedback#${RELEASE_FEEDBACK_PROMOTION_ANCHOR_ID}`,
    titleKey: 'dashboard.releaseWorkflow.feedback',
    descKey: 'dashboard.releaseWorkflow.feedbackDesc',
    gates: ['feedback'],
  },
  {
    id: 'evals',
    stepNumber: 5,
    navPath: '/evals',
    path: `/evals#${RELEASE_EVAL_REGRESSION_ANCHOR_ID}`,
    titleKey: 'dashboard.releaseWorkflow.evals',
    descKey: 'dashboard.releaseWorkflow.evalsDesc',
    gates: ['langsmith'],
  },
  {
    id: 'integrations',
    stepNumber: 6,
    navPath: '/integrations',
    path: `/integrations#${RELEASE_INTEGRATION_SMOKE_ANCHOR_ID}`,
    titleKey: 'dashboard.releaseWorkflow.integrations',
    descKey: 'dashboard.releaseWorkflow.integrationsDesc',
    gates: ['slack', 'a2a'],
  },
  {
    id: 'provider',
    stepNumber: 7,
    navPath: '/models',
    path: `/models#${RELEASE_PROVIDER_SMOKE_ANCHOR_ID}`,
    titleKey: 'dashboard.releaseWorkflow.provider',
    descKey: 'dashboard.releaseWorkflow.providerDesc',
    gates: ['provider'],
  },
] as const

export const RELEASE_WORKFLOW_ANCHOR_PATH = '/release#release-workflow'
export const RELEASE_LANGSMITH_SYNC_PATH = `/evals#${RELEASE_LANGSMITH_SYNC_ANCHOR_ID}`
export const RELEASE_SLACK_GATEWAY_PATH = `/integrations#${RELEASE_SLACK_GATEWAY_ANCHOR_ID}`
export const RELEASE_A2A_PROTOCOL_PATH = `/integrations#${RELEASE_A2A_PROTOCOL_ANCHOR_ID}`
export const RELEASE_RAG_ANSWER_CONTRACT_PATH = `/rag-cache?tab=rag#${RELEASE_RAG_ANSWER_CONTRACT_ANCHOR_ID}`
export const RELEASE_RAG_CANDIDATES_PATH = '/rag-cache?tab=candidates#rag-cache-tabpanel-candidates'

export function ragAnswerProbePath({
  question,
  expectedDocumentId,
}: {
  question?: string | null
  expectedDocumentId?: string | null
} = {}): string {
  const search = new URLSearchParams({ tab: 'rag' })
  const normalizedQuestion = question?.trim()
  const normalizedDocumentId = expectedDocumentId?.trim()
  if (normalizedQuestion) search.set('question', normalizedQuestion)
  if (normalizedDocumentId) search.set('expectedDocumentId', normalizedDocumentId)
  return `/rag-cache?${search.toString()}#${RELEASE_RAG_ANSWER_PROBE_ANCHOR_ID}`
}

export type ReleaseWorkflowStepId = typeof RELEASE_WORKFLOW_STEPS[number]['id']
export type ReleaseOperationStepId = Exclude<ReleaseWorkflowStepId, 'cockpit'>

export const RELEASE_WORKFLOW_NAV_PATHS_BY_ID = Object.fromEntries(
  RELEASE_WORKFLOW_STEPS.map((step) => [step.id, step.navPath]),
) as Record<ReleaseWorkflowStepId, string>

export const RELEASE_WORKFLOW_PATHS_BY_ID = Object.fromEntries(
  RELEASE_WORKFLOW_STEPS.map((step) => [step.id, step.path]),
) as Record<ReleaseWorkflowStepId, string>

export const RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID = Object.fromEntries(
  RELEASE_WORKFLOW_STEPS.map((step) => [step.id, step.stepNumber]),
) as Record<ReleaseWorkflowStepId, number>

export const RELEASE_WORKFLOW_COMMAND_ACTIONS = [
  {
    id: 'navigate.release-workflow',
    path: RELEASE_WORKFLOW_ANCHOR_PATH,
    titleKey: 'commandPalette.actions.releaseWorkflow',
    descriptionKey: 'commandPalette.actions.releaseWorkflowDesc',
    keywords: [
      'release',
      'v1.1',
      'rag',
      'langsmith',
      'smoke',
      'readiness',
      'requiredReports',
      'missingReports',
      'release_evidence',
      '릴리즈',
      '릴리즈 운영',
      '운영 흐름',
      '필수 리포트',
      '누락 리포트',
    ],
    stepNumber: undefined,
  },
  {
    id: 'navigate.release-cockpit',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
    titleKey: 'commandPalette.actions.releaseCockpit',
    descriptionKey: 'commandPalette.actions.releaseCockpitDesc',
    keywords: [
      'release',
      'readiness',
      'tag',
      'gate',
      'cockpit',
      'requiredReports',
      'missingReports',
      'release_evidence',
      'blockingReports',
      'warningReports',
      '릴리즈',
      '준비상태',
      '차단',
      '태그',
      '필수 리포트',
      '누락 리포트',
    ],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit,
  },
  {
    id: 'navigate.rag-ingestion',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
    titleKey: 'commandPalette.actions.ragIngestion',
    descriptionKey: 'commandPalette.actions.ragIngestionDesc',
    keywords: ['rag', 'ingest', 'document', 'candidate', '수집', '문서', '후보', '격리'],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.ingest,
  },
  {
    id: 'navigate.rag-lifecycle',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.rag,
    titleKey: 'commandPalette.actions.ragLifecycle',
    descriptionKey: 'commandPalette.actions.ragLifecycleDesc',
    keywords: ['rag', 'citation', 'ingest', '근거', '검색', '인용', '답변 계약'],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.rag,
  },
  {
    id: 'navigate.rag-cited-answer',
    path: RELEASE_RAG_ANSWER_CONTRACT_PATH,
    titleKey: 'commandPalette.actions.ragCitedAnswer',
    descriptionKey: 'commandPalette.actions.ragCitedAnswerDesc',
    keywords: ['rag', 'ask', 'answer', 'cited', 'citation', 'grounded', '질문', '답변', '근거 답변', '인용', '근거'],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.rag,
    showByDefault: false,
  },
  {
    id: 'navigate.feedback-promotion',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.feedback,
    titleKey: 'commandPalette.actions.feedbackPromotion',
    descriptionKey: 'commandPalette.actions.feedbackPromotionDesc',
    keywords: ['feedback', 'promotion', 'eval', 'review', '피드백', '리뷰', '승격'],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback,
  },
  {
    id: 'navigate.eval-regression',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.evals,
    titleKey: 'commandPalette.actions.evalRegression',
    descriptionKey: 'commandPalette.actions.evalRegressionDesc',
    keywords: ['eval', 'langsmith', 'regression', 'dataset', '평가', '회귀', '평가 회귀', '스위트'],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
  },
  {
    id: 'navigate.langsmith-sync',
    path: RELEASE_LANGSMITH_SYNC_PATH,
    titleKey: 'commandPalette.actions.langsmithSync',
    descriptionKey: 'commandPalette.actions.langsmithSyncDesc',
    keywords: [
      'langsmith',
      'sync',
      'dataset',
      'example',
      'metadata',
      'secret',
      'sdk',
      'langsmith_eval_sync',
      'metadataCaseIds',
      'exampleIds',
      'LANGSMITH_API_KEY',
      'REACTOR_OBSERVABILITY_LANGSMITH_API_KEY',
      '동기화',
      '데이터셋',
      '예제',
      '시크릿',
    ],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
    showByDefault: false,
  },
  {
    id: 'navigate.integration-smoke',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.integrations,
    titleKey: 'commandPalette.actions.integrationSmoke',
    descriptionKey: 'commandPalette.actions.integrationSmokeDesc',
    keywords: [
      'slack',
      'a2a',
      'provider',
      'smoke',
      'probe',
      'preflight',
      'smoke_run',
      'env',
      'token',
      'requiredReports',
      'missingReports',
      'REACTOR_SLACK_BOT_TOKEN',
      'REACTOR_SLACK_SIGNING_SECRET',
      'REACTOR_A2A_BASE_URL',
      'REACTOR_A2A_API_KEY',
      'OPENAI_API_KEY',
      '라이브 스모크',
      '연동',
      '환경값',
      '필수 리포트',
      '누락 리포트',
    ],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
  },
  {
    id: 'navigate.slack-gateway-smoke',
    path: RELEASE_SLACK_GATEWAY_PATH,
    titleKey: 'commandPalette.actions.slackGatewaySmoke',
    descriptionKey: 'commandPalette.actions.slackGatewaySmokeDesc',
    keywords: [
      'slack',
      'workspace',
      'gateway',
      'channel',
      'auth',
      'feedback',
      'eval',
      'signature',
      'REACTOR_SLACK_BOT_TOKEN',
      'REACTOR_SLACK_SIGNING_SECRET',
      '슬랙',
      '워크스페이스',
      '채널',
      '인증',
    ],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
    showByDefault: false,
  },
  {
    id: 'navigate.a2a-protocol-smoke',
    path: RELEASE_A2A_PROTOCOL_PATH,
    titleKey: 'commandPalette.actions.a2aProtocolSmoke',
    descriptionKey: 'commandPalette.actions.a2aProtocolSmokeDesc',
    keywords: [
      'a2a',
      'agent card',
      'protocol',
      'peer',
      'task',
      'diagnostics',
      'telemetry',
      'REACTOR_A2A_BASE_URL',
      'REACTOR_A2A_API_KEY',
      '프로토콜',
      '피어',
      '진단',
    ],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
    showByDefault: false,
  },
  {
    id: 'navigate.provider-smoke',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.provider,
    titleKey: 'commandPalette.actions.providerSmoke',
    descriptionKey: 'commandPalette.actions.providerSmokeDesc',
    keywords: [
      'provider',
      'openai',
      'ollama',
      'model',
      'usage',
      'usage_metadata',
      'token',
      'langchain',
      'OPENAI_API_KEY',
      'AIMessage.usage_metadata',
      'smoke',
      '제공자',
      '모델',
      '토큰',
      '올라마',
    ],
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.provider,
  },
] as const

export const RELEASE_BLOCKING_REPORT_ROUTES = [
  {
    reportId: 'release_readiness',
    actionId: 'navigate.release-cockpit',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit,
    titleKey: 'commandPalette.actions.releaseCockpit',
    aliases: ['release-readiness.json', 'blockingReports', 'eligible', 'minorEligible'],
  },
  {
    reportId: 'preflight',
    actionId: 'navigate.integration-smoke',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.integrations,
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
    titleKey: 'commandPalette.actions.integrationSmoke',
    aliases: ['release_smoke_preflight', 'release-smoke-preflight', 'env missing', 'live provider', 'slack workspace', 'a2a peer'],
  },
  {
    reportId: 'smoke_run',
    actionId: 'navigate.integration-smoke',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.integrations,
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
    titleKey: 'commandPalette.actions.integrationSmoke',
    aliases: ['release_smoke_run', 'release-smoke-run', 'live smoke', 'requiredReports', 'missingReports'],
  },
  {
    reportId: 'langsmith_eval_sync',
    actionId: 'navigate.langsmith-sync',
    path: RELEASE_LANGSMITH_SYNC_PATH,
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
    titleKey: 'commandPalette.actions.langsmithSync',
    aliases: ['datasetName', 'exampleIds', 'metadataCaseIds', 'splitCounts', 'secretScan', 'sdkContract'],
  },
  {
    reportId: 'rag_ingestion_lifecycle',
    actionId: 'navigate.rag-lifecycle',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.rag,
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.rag,
    titleKey: 'commandPalette.actions.ragLifecycle',
    aliases: ['ragIngestionLifecycle', 'minorEligible', 'citation', 'answer contract', 'grounded citation'],
  },
  {
    reportId: 'feedback_promotion',
    actionId: 'navigate.feedback-promotion',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.feedback,
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback,
    titleKey: 'commandPalette.actions.feedbackPromotion',
    aliases: ['feedbackReviewQueue', 'promotedCaseIds', 'reviewed', 'eval promotion'],
  },
  {
    reportId: 'slack_gateway_smoke',
    actionId: 'navigate.slack-gateway-smoke',
    path: RELEASE_SLACK_GATEWAY_PATH,
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
    titleKey: 'commandPalette.actions.slackGatewaySmoke',
    aliases: ['slack_workspace_smoke', 'REACTOR_SLACK_BOT_TOKEN', 'REACTOR_SLACK_SIGNING_SECRET', 'feedback action'],
  },
  {
    reportId: 'a2a_protocol',
    actionId: 'navigate.a2a-protocol-smoke',
    path: RELEASE_A2A_PROTOCOL_PATH,
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
    titleKey: 'commandPalette.actions.a2aProtocolSmoke',
    aliases: ['a2a_peer_smoke', 'REACTOR_A2A_BASE_URL', 'REACTOR_A2A_API_KEY', 'agent card', 'task API'],
  },
  {
    reportId: 'backend_provider_integration',
    actionId: 'navigate.provider-smoke',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.provider,
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.provider,
    titleKey: 'commandPalette.actions.providerSmoke',
    aliases: ['provider_smoke', 'OPENAI_API_KEY', 'Ollama', 'AIMessage.usage_metadata', 'usage metadata'],
  },
] as const

export function releaseBlockingReportRoute(report: string) {
  const normalized = report.toLowerCase()
  return RELEASE_BLOCKING_REPORT_ROUTES.find((route) => route.reportId.toLowerCase() === normalized) ?? null
}

export function buildReleaseWorkflowSearchRecords(
  translate: (key: string) => string,
): SearchableRecord[] {
  const actionRecords = RELEASE_WORKFLOW_COMMAND_ACTIONS.map((action) => {
    const haystackParts = [
      translate(action.titleKey),
      action.descriptionKey ? translate(action.descriptionKey) : null,
      action.id,
      ...action.keywords,
      action.stepNumber ? `step ${action.stepNumber}` : null,
      action.stepNumber ? `${action.stepNumber}` : null,
    ].filter((part): part is string => Boolean(part))

    return {
      id: `release:${action.id}`,
      scope: 'release',
      title: translate(action.titleKey),
      subtitle: action.descriptionKey ? translate(action.descriptionKey) : undefined,
      stepNumber: action.stepNumber,
      navigateTo: action.path,
      haystack: haystackParts.join(' ').toLowerCase(),
    } satisfies SearchableRecord
  })

  const blockerRecords = RELEASE_BLOCKING_REPORT_ROUTES.map((route) => {
    const title = `${route.reportId} blocker`
    const subtitle = translate(route.titleKey)
    const haystackParts = [
      title,
      subtitle,
      route.reportId,
      route.actionId,
      `step ${route.stepNumber}`,
      `${route.stepNumber}`,
      ...route.aliases,
      'blockingReports',
      'release readiness',
      'blocked',
      '릴리즈 차단',
      '차단 리포트',
    ]

    return {
      id: `release:blocker:${route.reportId}`,
      scope: 'release',
      title,
      subtitle,
      stepNumber: route.stepNumber,
      navigateTo: route.path,
      haystack: haystackParts.join(' ').toLowerCase(),
    } satisfies SearchableRecord
  })

  return [...actionRecords, ...blockerRecords]
}

export const RELEASE_OPERATION_NAV_PATHS = RELEASE_WORKFLOW_STEPS
  .map((step) => step.path)

export const RELEASE_OPERATION_NAV_PATHS_BY_ID: Record<ReleaseOperationStepId, string> = {
  ingest: RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
  rag: RELEASE_WORKFLOW_PATHS_BY_ID.rag,
  feedback: RELEASE_WORKFLOW_PATHS_BY_ID.feedback,
  evals: RELEASE_WORKFLOW_PATHS_BY_ID.evals,
  integrations: RELEASE_WORKFLOW_PATHS_BY_ID.integrations,
  provider: RELEASE_WORKFLOW_PATHS_BY_ID.provider,
}

export const RELEASE_WORKFLOW_GATE_ORDER: ReleaseWorkflowGateId[] = [
  'rag',
  'feedback',
  'langsmith',
  'slack',
  'a2a',
  'provider',
]

export const RELEASE_SMOKE_GATE_IDS = [
  'slack',
  'a2a',
  'provider',
] as const satisfies readonly ReleaseWorkflowGateId[]

export const RELEASE_WORKFLOW_GATE_PATHS: Record<ReleaseWorkflowGateId, string> = {
  rag: RELEASE_WORKFLOW_PATHS_BY_ID.rag,
  feedback: RELEASE_WORKFLOW_PATHS_BY_ID.feedback,
  langsmith: RELEASE_LANGSMITH_SYNC_PATH,
  slack: RELEASE_SLACK_GATEWAY_PATH,
  a2a: RELEASE_A2A_PROTOCOL_PATH,
  provider: RELEASE_WORKFLOW_PATHS_BY_ID.provider,
}

export const RELEASE_WORKFLOW_GATE_STEP_NUMBERS: Record<ReleaseWorkflowGateId, number> = {
  rag: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.rag,
  feedback: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback,
  langsmith: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
  slack: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
  a2a: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
  provider: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.provider,
}

export function releaseReportBelongsToGate(report: string, gateId: ReleaseWorkflowGateId): boolean {
  const normalized = report.toLowerCase()
  if (gateId === 'rag') {
    return normalized.includes('rag')
      || normalized.includes('citation')
      || normalized.includes('research_answer_contract')
      || normalized.includes('answer_contract')
  }
  if (gateId === 'feedback') return normalized.includes('feedback') || normalized.includes('promotion')
  if (gateId === 'langsmith') return normalized.includes('langsmith') || normalized.includes('eval')
  if (gateId === 'slack') {
    return normalized.includes('slack')
      || normalized.includes('preflight')
      || normalized.includes('smoke_run')
  }
  if (gateId === 'a2a') {
    return normalized.includes('a2a')
      || normalized.includes('preflight')
      || normalized.includes('smoke_run')
  }
  if (gateId === 'provider') {
    return normalized.includes('provider')
      || normalized.includes('openai')
      || normalized.includes('model')
      || normalized.includes('preflight')
      || normalized.includes('smoke_run')
  }
  return false
}

export function releaseReportPath(report: string): string | null {
  const exactRoute = releaseBlockingReportRoute(report)
  if (exactRoute) return exactRoute.path
  if (report.toLowerCase() === 'preflight') return RELEASE_WORKFLOW_PATHS_BY_ID.integrations
  if (report.toLowerCase() === 'smoke_run') return RELEASE_WORKFLOW_PATHS_BY_ID.integrations
  if (releaseReportBelongsToGate(report, 'rag')) return RELEASE_WORKFLOW_GATE_PATHS.rag
  if (releaseReportBelongsToGate(report, 'feedback')) return RELEASE_WORKFLOW_GATE_PATHS.feedback
  if (releaseReportBelongsToGate(report, 'langsmith')) return RELEASE_WORKFLOW_GATE_PATHS.langsmith
  if (releaseReportBelongsToGate(report, 'slack')) return RELEASE_WORKFLOW_GATE_PATHS.slack
  if (releaseReportBelongsToGate(report, 'a2a')) return RELEASE_WORKFLOW_GATE_PATHS.a2a
  if (releaseReportBelongsToGate(report, 'provider')) return RELEASE_WORKFLOW_GATE_PATHS.provider
  return null
}

export function releaseReportStepNumber(report: string): number | null {
  const exactRoute = releaseBlockingReportRoute(report)
  if (exactRoute) return exactRoute.stepNumber
  const gateId = RELEASE_WORKFLOW_GATE_ORDER.find((candidate) => releaseReportBelongsToGate(report, candidate))
  return gateId ? RELEASE_WORKFLOW_GATE_STEP_NUMBERS[gateId] : null
}

export function releaseBoundaryEvidencePath(evidence: string): string | null {
  const normalized = evidence.toLowerCase()
  if (normalized.includes('release_readiness_command')) return RELEASE_WORKFLOW_PATHS_BY_ID.cockpit
  if (normalized.includes('research_answer_contract') || normalized.includes('answer_contract')) {
    return RELEASE_RAG_ANSWER_CONTRACT_PATH
  }
  return releaseReportPath(evidence)
}

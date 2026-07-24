import {
  RELEASE_A2A_PROTOCOL_PATH,
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_RAG_ANSWER_CONTRACT_PATH,
  RELEASE_SLACK_GATEWAY_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../releaseWorkflow'

export type ProductCapabilityBoundaryFlowItemId =
  | 'ingest'
  | 'cited_answer'
  | 'feedback'
  | 'langsmith'
  | 'slack'
  | 'a2a'
  | 'provider'
  | 'readiness'

export interface ProductCapabilityBoundaryFlowInput {
  evidence?: string[] | null
  missingEvidence?: string[] | null
}

export interface ProductCapabilityBoundaryFlowItem {
  id: ProductCapabilityBoundaryFlowItemId
  stepNumber: number
  labelKey: string
  path: string
  status: 'passed' | 'missing'
  matchedEvidence: string[]
  missingEvidence: string[]
}

interface ProductCapabilityBoundaryFlowDefinition {
  id: ProductCapabilityBoundaryFlowItemId
  stepNumber: number
  labelKey: string
  path: string
  evidenceAliases: string[]
}

const flowDefinitions: ProductCapabilityBoundaryFlowDefinition[] = [
  {
    id: 'ingest',
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.ingest,
    labelKey: 'dashboard.release.productBoundaryFlow.ingest',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
    evidenceAliases: ['rag_ingestion_lifecycle'],
  },
  {
    id: 'cited_answer',
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.rag,
    labelKey: 'dashboard.release.productBoundaryFlow.citedAnswer',
    path: RELEASE_RAG_ANSWER_CONTRACT_PATH,
    evidenceAliases: ['research_answer_contract', 'rag_answer_contract'],
  },
  {
    id: 'feedback',
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback,
    labelKey: 'dashboard.release.productBoundaryFlow.feedback',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.feedback,
    evidenceAliases: [
      'feedback_promotion.reviewed_feedback',
      'rag_ingestion_candidate_feedback_queue',
    ],
  },
  {
    id: 'langsmith',
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
    labelKey: 'dashboard.release.productBoundaryFlow.langsmith',
    path: RELEASE_LANGSMITH_SYNC_PATH,
    evidenceAliases: ['langsmith_trace_grading', 'langsmith_eval_sync'],
  },
  {
    id: 'slack',
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
    labelKey: 'dashboard.release.productBoundaryFlow.slack',
    path: RELEASE_SLACK_GATEWAY_PATH,
    evidenceAliases: ['slack_gateway_smoke'],
  },
  {
    id: 'a2a',
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations,
    labelKey: 'dashboard.release.productBoundaryFlow.a2a',
    path: RELEASE_A2A_PROTOCOL_PATH,
    evidenceAliases: ['a2a_protocol'],
  },
  {
    id: 'provider',
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.provider,
    labelKey: 'dashboard.release.productBoundaryFlow.provider',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.provider,
    evidenceAliases: ['backend_provider_integration'],
  },
  {
    id: 'readiness',
    stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit,
    labelKey: 'dashboard.release.productBoundaryFlow.readiness',
    path: RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
    evidenceAliases: ['release_readiness_command'],
  },
]

function normalizeEvidence(values: string[] | null | undefined): Map<string, string> {
  return new Map(
    (values ?? [])
      .filter(Boolean)
      .map((value) => [value.toLowerCase(), value]),
  )
}

export function listProductCapabilityBoundaryFlowItems({
  evidence,
  missingEvidence,
}: ProductCapabilityBoundaryFlowInput): ProductCapabilityBoundaryFlowItem[] {
  const present = normalizeEvidence(evidence)
  const missing = normalizeEvidence(missingEvidence)

  return flowDefinitions.map((definition) => {
    const matchedEvidence = definition.evidenceAliases
      .map((alias) => present.get(alias))
      .filter((value): value is string => Boolean(value))
    const missingMatches = definition.evidenceAliases
      .map((alias) => missing.get(alias))
      .filter((value): value is string => Boolean(value))

    return {
      id: definition.id,
      stepNumber: definition.stepNumber,
      labelKey: definition.labelKey,
      path: definition.path,
      status: matchedEvidence.length > 0 && missingMatches.length === 0 ? 'passed' : 'missing',
      matchedEvidence,
      missingEvidence: missingMatches,
    }
  })
}

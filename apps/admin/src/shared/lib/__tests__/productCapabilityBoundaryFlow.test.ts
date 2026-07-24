import { describe, expect, it } from 'vitest'
import {
  RELEASE_RAG_ANSWER_CONTRACT_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
} from '../../releaseWorkflow'
import { listProductCapabilityBoundaryFlowItems } from '../productCapabilityBoundaryFlow'

describe('listProductCapabilityBoundaryFlowItems', () => {
  it('maps release minor evidence into the product workflow order', () => {
    const items = listProductCapabilityBoundaryFlowItems({
      evidence: [
        'rag_ingestion_lifecycle',
        'feedback_promotion.reviewed_feedback',
        'langsmith_trace_grading',
        'slack_gateway_smoke',
        'a2a_protocol',
        'backend_provider_integration',
        'release_readiness_command',
      ],
      missingEvidence: ['research_answer_contract'],
    })

    expect(items.map((item) => item.id)).toEqual([
      'ingest',
      'cited_answer',
      'feedback',
      'langsmith',
      'slack',
      'a2a',
      'provider',
      'readiness',
    ])
    expect(items.find((item) => item.id === 'ingest')).toMatchObject({
      status: 'passed',
      path: RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
      matchedEvidence: ['rag_ingestion_lifecycle'],
    })
    expect(items.find((item) => item.id === 'cited_answer')).toMatchObject({
      status: 'missing',
      path: RELEASE_RAG_ANSWER_CONTRACT_PATH,
      missingEvidence: ['research_answer_contract'],
    })
    expect(items.find((item) => item.id === 'readiness')).toMatchObject({
      status: 'passed',
      path: RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
      matchedEvidence: ['release_readiness_command'],
    })
  })
})

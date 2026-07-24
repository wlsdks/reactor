import { describe, expect, it } from 'vitest'
import {
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_A2A_PROTOCOL_PATH,
  RELEASE_BLOCKING_REPORT_ROUTES,
  RELEASE_RAG_ANSWER_CONTRACT_PATH,
  RELEASE_RAG_CANDIDATES_PATH,
  RELEASE_SLACK_GATEWAY_PATH,
  RELEASE_WORKFLOW_COMMAND_ACTIONS,
  RELEASE_WORKFLOW_STEPS,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
  RELEASE_SMOKE_GATE_IDS,
  RELEASE_WORKFLOW_GATE_PATHS,
  RELEASE_WORKFLOW_GATE_STEP_NUMBERS,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  ragAnswerProbePath,
  buildReleaseWorkflowSearchRecords,
  releaseBlockingReportRoute,
  releaseReportBelongsToGate,
  releaseReportPath,
  releaseReportStepNumber,
  releaseBoundaryEvidencePath,
} from '../releaseWorkflow'

describe('RELEASE_SMOKE_GATE_IDS', () => {
  it('keeps the release smoke gate order shared across cockpit and integrations', () => {
    expect(RELEASE_SMOKE_GATE_IDS).toEqual(['slack', 'a2a', 'provider'])
  })
})

describe('RELEASE_WORKFLOW_COMMAND_ACTIONS', () => {
  it('builds a register-to-answer handoff without putting document content in the URL', () => {
    expect(ragAnswerProbePath({
      question: 'What changed?',
      expectedDocumentId: 'doc-policy-1',
    })).toBe('/rag-cache?tab=rag&question=What+changed%3F&expectedDocumentId=doc-policy-1#rag-answer-probe')
  })

  it('exposes the RAG candidate queue deep link for feedback promotion handoff', () => {
    expect(RELEASE_RAG_CANDIDATES_PATH).toBe('/rag-cache?tab=candidates#rag-cache-tabpanel-candidates')
  })

  it('keeps the release workflow step numbers in the shared workflow contract', () => {
    expect(RELEASE_WORKFLOW_STEPS.map((step) => step.stepNumber)).toEqual([1, 2, 3, 4, 5, 6, 7])
    expect(RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID).toMatchObject({
      cockpit: 1,
      ingest: 2,
      rag: 3,
      feedback: 4,
      evals: 5,
      integrations: 6,
      provider: 7,
    })
  })

  it('routes command palette shortcuts through the owning workflow step ids', () => {
    expect(Object.fromEntries(
      RELEASE_WORKFLOW_COMMAND_ACTIONS.map((action) => [action.id, action.path]),
    )).toMatchObject({
      'navigate.release-cockpit': RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
      'navigate.rag-ingestion': RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
      'navigate.rag-lifecycle': RELEASE_WORKFLOW_PATHS_BY_ID.rag,
      'navigate.rag-cited-answer': RELEASE_RAG_ANSWER_CONTRACT_PATH,
      'navigate.feedback-promotion': RELEASE_WORKFLOW_PATHS_BY_ID.feedback,
      'navigate.eval-regression': RELEASE_WORKFLOW_PATHS_BY_ID.evals,
      'navigate.langsmith-sync': RELEASE_LANGSMITH_SYNC_PATH,
      'navigate.integration-smoke': RELEASE_WORKFLOW_PATHS_BY_ID.integrations,
      'navigate.slack-gateway-smoke': RELEASE_SLACK_GATEWAY_PATH,
      'navigate.a2a-protocol-smoke': RELEASE_A2A_PROTOCOL_PATH,
      'navigate.provider-smoke': RELEASE_WORKFLOW_PATHS_BY_ID.provider,
    })
  })

  it('marks command palette workflow shortcuts with stable release step numbers', () => {
    expect(Object.fromEntries(
      RELEASE_WORKFLOW_COMMAND_ACTIONS.map((action) => [action.id, action.stepNumber ?? null]),
    )).toMatchObject({
      'navigate.release-workflow': null,
      'navigate.release-cockpit': 1,
      'navigate.rag-ingestion': 2,
      'navigate.rag-lifecycle': 3,
      'navigate.rag-cited-answer': 3,
      'navigate.feedback-promotion': 4,
      'navigate.eval-regression': 5,
      'navigate.langsmith-sync': 5,
      'navigate.integration-smoke': 6,
      'navigate.slack-gateway-smoke': 6,
      'navigate.a2a-protocol-smoke': 6,
      'navigate.provider-smoke': 7,
    })
  })

  it('keeps release smoke shortcuts discoverable by current blocker and local provider terms', () => {
    const actionsById = Object.fromEntries(
      RELEASE_WORKFLOW_COMMAND_ACTIONS.map((action) => [action.id, action]),
    )

    expect(actionsById['navigate.integration-smoke']?.keywords).toEqual(expect.arrayContaining([
      'preflight',
      'env',
      'token',
      'REACTOR_SLACK_BOT_TOKEN',
      'REACTOR_A2A_BASE_URL',
      'OPENAI_API_KEY',
    ]))
    expect(actionsById['navigate.langsmith-sync']?.keywords).toEqual(expect.arrayContaining([
      'LANGSMITH_API_KEY',
      'REACTOR_OBSERVABILITY_LANGSMITH_API_KEY',
    ]))
    expect(actionsById['navigate.slack-gateway-smoke']?.keywords).toEqual(expect.arrayContaining([
      'REACTOR_SLACK_BOT_TOKEN',
      'REACTOR_SLACK_SIGNING_SECRET',
    ]))
    expect(actionsById['navigate.a2a-protocol-smoke']?.keywords).toEqual(expect.arrayContaining([
      'REACTOR_A2A_BASE_URL',
      'REACTOR_A2A_API_KEY',
    ]))
    expect(actionsById['navigate.provider-smoke']?.keywords).toEqual(expect.arrayContaining([
      'ollama',
      'usage',
      'usage_metadata',
      'token',
      'langchain',
      'OPENAI_API_KEY',
      'AIMessage.usage_metadata',
    ]))
  })

  it('exposes release workflow gates as global search records', () => {
    const records = buildReleaseWorkflowSearchRecords((key) => key)
    const recordsById = Object.fromEntries(records.map((record) => [record.id, record]))

    expect(records).toHaveLength(RELEASE_WORKFLOW_COMMAND_ACTIONS.length + RELEASE_BLOCKING_REPORT_ROUTES.length)
    expect(records.every((record) => record.scope === 'release')).toBe(true)
    expect(recordsById['release:navigate.release-workflow']).toMatchObject({
      title: 'commandPalette.actions.releaseWorkflow',
      navigateTo: '/release#release-workflow',
    })
    expect(recordsById['release:navigate.eval-regression']).toMatchObject({
      navigateTo: RELEASE_WORKFLOW_PATHS_BY_ID.evals,
    })
    expect(recordsById['release:navigate.langsmith-sync']).toMatchObject({
      navigateTo: RELEASE_LANGSMITH_SYNC_PATH,
    })
    expect(recordsById['release:navigate.release-workflow']?.haystack).toContain('requiredreports')
    expect(recordsById['release:navigate.release-workflow']?.haystack).toContain('missingreports')
    expect(recordsById['release:navigate.release-workflow']?.haystack).toContain('release_evidence')
    expect(recordsById['release:navigate.release-cockpit']?.haystack).toContain('blockingreports')
    expect(recordsById['release:navigate.release-cockpit']?.haystack).toContain('warningreports')
    expect(recordsById['release:navigate.langsmith-sync']?.haystack).toContain('example')
    expect(recordsById['release:navigate.langsmith-sync']?.haystack).toContain('metadata')
    expect(recordsById['release:navigate.langsmith-sync']?.haystack).toContain('langsmith_eval_sync')
    expect(recordsById['release:navigate.langsmith-sync']?.haystack).toContain('metadatacaseids')
    expect(recordsById['release:navigate.langsmith-sync']?.haystack).toContain('langsmith_api_key')
    expect(recordsById['release:navigate.integration-smoke']?.haystack).toContain('a2a')
    expect(recordsById['release:navigate.integration-smoke']?.haystack).toContain('slack')
    expect(recordsById['release:navigate.integration-smoke']?.haystack).toContain('smoke_run')
    expect(recordsById['release:navigate.integration-smoke']?.haystack).toContain('missingreports')
    expect(recordsById['release:navigate.integration-smoke']?.haystack).toContain('reactor_a2a_base_url')
    expect(recordsById['release:navigate.integration-smoke']?.haystack).toContain('reactor_slack_bot_token')
    expect(recordsById['release:navigate.slack-gateway-smoke']).toMatchObject({
      navigateTo: RELEASE_SLACK_GATEWAY_PATH,
    })
    expect(recordsById['release:navigate.slack-gateway-smoke']?.haystack).toContain('workspace')
    expect(recordsById['release:navigate.slack-gateway-smoke']?.haystack).toContain('reactor_slack_signing_secret')
    expect(recordsById['release:navigate.a2a-protocol-smoke']).toMatchObject({
      navigateTo: RELEASE_A2A_PROTOCOL_PATH,
    })
    expect(recordsById['release:navigate.a2a-protocol-smoke']?.haystack).toContain('agent card')
    expect(recordsById['release:navigate.a2a-protocol-smoke']?.haystack).toContain('reactor_a2a_api_key')
    expect(recordsById['release:navigate.provider-smoke']?.haystack).toContain('ollama')
    expect(recordsById['release:navigate.provider-smoke']?.haystack).toContain('usage_metadata')
    expect(recordsById['release:navigate.provider-smoke']?.haystack).toContain('token')
    expect(recordsById['release:navigate.provider-smoke']?.haystack).toContain('langchain')
    expect(recordsById['release:navigate.provider-smoke']?.haystack).toContain('openai_api_key')
    expect(recordsById['release:navigate.release-workflow']?.haystack).toContain('v1.1')
    expect(recordsById['release:navigate.rag-cited-answer']).toMatchObject({
      navigateTo: RELEASE_RAG_ANSWER_CONTRACT_PATH,
    })
    expect(recordsById['release:navigate.rag-cited-answer']?.haystack).toContain('ask')
    expect(recordsById['release:navigate.rag-cited-answer']?.haystack).toContain('cited')
    expect(recordsById['release:navigate.rag-cited-answer']?.haystack).toContain('citation')
    expect(recordsById['release:navigate.rag-cited-answer']?.haystack).toContain('인용')
  })

  it('exposes blocking report ids as release search records routed to the owning surfaces', () => {
    const records = buildReleaseWorkflowSearchRecords((key) => key)
    const recordsById = Object.fromEntries(records.map((record) => [record.id, record]))

    for (const route of RELEASE_BLOCKING_REPORT_ROUTES) {
      expect(recordsById[`release:blocker:${route.reportId}`]).toMatchObject({
        title: `${route.reportId} blocker`,
        subtitle: route.titleKey,
        navigateTo: route.path,
        stepNumber: route.stepNumber,
      })
      expect(recordsById[`release:blocker:${route.reportId}`]?.haystack).toContain(route.reportId)
      expect(recordsById[`release:blocker:${route.reportId}`]?.haystack).toContain('blockingreports')
      expect(recordsById[`release:blocker:${route.reportId}`]?.haystack).toContain('blocked')
    }

    expect(recordsById['release:blocker:preflight']?.navigateTo)
      .toBe(RELEASE_WORKFLOW_PATHS_BY_ID.integrations)
    expect(recordsById['release:blocker:preflight']?.haystack).toContain('env missing')
    expect(recordsById['release:blocker:langsmith_eval_sync']?.navigateTo)
      .toBe(RELEASE_LANGSMITH_SYNC_PATH)
    expect(recordsById['release:blocker:langsmith_eval_sync']?.haystack).toContain('metadatacaseids')
    expect(recordsById['release:blocker:backend_provider_integration']?.navigateTo)
      .toBe(RELEASE_WORKFLOW_PATHS_BY_ID.provider)
    expect(recordsById['release:blocker:backend_provider_integration']?.haystack).toContain('aimessage.usage_metadata')
  })
})

describe('releaseBoundaryEvidencePath', () => {
  it('maps release readiness gates to the owning workflow step numbers', () => {
    expect(RELEASE_WORKFLOW_GATE_STEP_NUMBERS).toEqual({
      rag: 3,
      feedback: 4,
      langsmith: 5,
      slack: 6,
      a2a: 6,
      provider: 7,
    })
  })

  it('routes product capability boundary evidence to the owning release operation surfaces', () => {
    expect(releaseBoundaryEvidencePath('rag_ingestion_lifecycle')).toBe(RELEASE_WORKFLOW_GATE_PATHS.rag)
    expect(releaseBoundaryEvidencePath('research_answer_contract')).toBe(RELEASE_RAG_ANSWER_CONTRACT_PATH)
    expect(releaseBoundaryEvidencePath('feedback_promotion.reviewed_feedback')).toBe(RELEASE_WORKFLOW_GATE_PATHS.feedback)
    expect(releaseBoundaryEvidencePath('langsmith_eval_sync')).toBe(RELEASE_LANGSMITH_SYNC_PATH)
    expect(releaseBoundaryEvidencePath('slack_gateway_smoke')).toBe(RELEASE_WORKFLOW_GATE_PATHS.slack)
    expect(releaseBoundaryEvidencePath('a2a_protocol')).toBe(RELEASE_WORKFLOW_GATE_PATHS.a2a)
    expect(releaseBoundaryEvidencePath('backend_provider_integration')).toBe(RELEASE_WORKFLOW_GATE_PATHS.provider)
  })

  it('routes release readiness command evidence back to the release cockpit', () => {
    expect(releaseBoundaryEvidencePath('release_readiness_command')).toBe(RELEASE_WORKFLOW_PATHS_BY_ID.cockpit)
  })
})

describe('release report routing', () => {
  it('keeps exact blocker report routes tied to the owning workflow surfaces', () => {
    expect(releaseBlockingReportRoute('release_readiness')).toMatchObject({
      path: RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
      stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit,
      titleKey: 'commandPalette.actions.releaseCockpit',
    })
    expect(releaseBlockingReportRoute('langsmith_eval_sync')).toMatchObject({
      path: RELEASE_LANGSMITH_SYNC_PATH,
      stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
      titleKey: 'commandPalette.actions.langsmithSync',
    })
    expect(releaseBlockingReportRoute('backend_provider_integration')).toMatchObject({
      path: RELEASE_WORKFLOW_PATHS_BY_ID.provider,
      stepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.provider,
      titleKey: 'commandPalette.actions.providerSmoke',
    })
    expect(releaseBlockingReportRoute('unknown_report')).toBeNull()
  })

  it('classifies blocker and warning report names by release gate', () => {
    expect(releaseReportBelongsToGate('rag_ingestion_lifecycle', 'rag')).toBe(true)
    expect(releaseReportBelongsToGate('feedback_review_queue', 'feedback')).toBe(true)
    expect(releaseReportBelongsToGate('langsmith_eval_sync', 'langsmith')).toBe(true)
    expect(releaseReportBelongsToGate('slack_workspace_smoke', 'slack')).toBe(true)
    expect(releaseReportBelongsToGate('a2a_peer_smoke', 'a2a')).toBe(true)
    expect(releaseReportBelongsToGate('provider_smoke', 'provider')).toBe(true)
    expect(releaseReportBelongsToGate('preflight', 'slack')).toBe(true)
    expect(releaseReportBelongsToGate('preflight', 'a2a')).toBe(true)
    expect(releaseReportBelongsToGate('preflight', 'provider')).toBe(true)
    expect(releaseReportBelongsToGate('smoke_run', 'slack')).toBe(true)
    expect(releaseReportBelongsToGate('smoke_run', 'a2a')).toBe(true)
    expect(releaseReportBelongsToGate('smoke_run', 'provider')).toBe(true)
    expect(releaseReportBelongsToGate('feedback_review_queue', 'provider')).toBe(false)
  })

  it('routes blocker and warning report names to the primary owning screen', () => {
    expect(releaseReportPath('rag_ingestion_lifecycle')).toBe(RELEASE_WORKFLOW_GATE_PATHS.rag)
    expect(releaseReportPath('feedback_review_queue')).toBe(RELEASE_WORKFLOW_GATE_PATHS.feedback)
    expect(releaseReportPath('langsmith_eval_sync')).toBe(RELEASE_LANGSMITH_SYNC_PATH)
    expect(releaseReportPath('preflight')).toBe(RELEASE_WORKFLOW_PATHS_BY_ID.integrations)
    expect(releaseReportPath('smoke_run')).toBe(RELEASE_WORKFLOW_PATHS_BY_ID.integrations)
    expect(releaseReportPath('slack_workspace_smoke')).toBe(RELEASE_WORKFLOW_GATE_PATHS.slack)
    expect(releaseReportPath('a2a_peer_smoke')).toBe(RELEASE_WORKFLOW_GATE_PATHS.a2a)
    expect(releaseReportPath('provider_smoke')).toBe(RELEASE_WORKFLOW_GATE_PATHS.provider)
    expect(releaseReportPath('release_readiness')).toBe(RELEASE_WORKFLOW_PATHS_BY_ID.cockpit)
    expect(releaseReportPath('backend_provider_integration')).toBe(RELEASE_WORKFLOW_PATHS_BY_ID.provider)
    expect(releaseReportPath('unknown_report')).toBeNull()
  })

  it('resolves report step numbers with exact blocker routes before gate heuristics', () => {
    expect(releaseReportStepNumber('release_readiness')).toBe(RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit)
    expect(releaseReportStepNumber('langsmith_eval_sync')).toBe(RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals)
    expect(releaseReportStepNumber('backend_provider_integration')).toBe(RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.provider)
    expect(releaseReportStepNumber('smoke_run')).toBe(RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations)
    expect(releaseReportStepNumber('feedback_review_queue')).toBe(RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback)
    expect(releaseReportStepNumber('unknown_report')).toBeNull()
  })
})

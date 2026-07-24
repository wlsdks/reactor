import { http, HttpResponse } from 'msw'
import { NOW, HOUR, DAY } from './shared'

const persistedEvalCases = [
  {
    id: 'case_feedback_run_103',
    name: 'Feedback run 103 citation regression',
    userInput: 'What changed in the release workflow?',
    expectedAnswerContains: ['citation'],
    forbiddenAnswerContains: [],
    expectedToolNames: [],
    forbiddenToolNames: [],
    expectedExposedToolNames: [],
    forbiddenExposedToolNames: [],
    maxToolExposureCount: null,
    agentType: 'reactor',
    model: 'ollama',
    enabled: true,
    tags: ['feedback', 'regression'],
    minScore: 1,
    sourceRunId: 'run-103',
    assertionCount: 1,
    createdAt: new Date(NOW - HOUR).toISOString(),
    updatedAt: new Date(NOW - HOUR).toISOString(),
    nextActions: [],
  },
  {
    id: 'case_rag_candidate_grounded_citation',
    name: 'RAG grounded citation regression',
    userInput: 'Summarize the ingested document with citations.',
    expectedAnswerContains: ['[doc-release-workflow]'],
    forbiddenAnswerContains: [],
    expectedToolNames: [],
    forbiddenToolNames: [],
    expectedExposedToolNames: [],
    forbiddenExposedToolNames: [],
    maxToolExposureCount: null,
    agentType: 'reactor',
    model: 'ollama',
    enabled: true,
    tags: ['rag', 'grounded-citation', 'regression'],
    minScore: 1,
    sourceRunId: 'run-rag-candidate-1',
    assertionCount: 1,
    createdAt: new Date(NOW - HOUR).toISOString(),
    updatedAt: new Date(NOW - HOUR).toISOString(),
    nextActions: [],
  },
]

export const mockFeedback = [
  {
    feedbackId: 'fb-1',
    query: 'How do I create a new Jira ticket?',
    response: 'You can create a new Jira ticket using the jira_create_issue tool. Specify the project key, issue type, and summary.',
    rating: 'thumbs_up' as const,
    timestamp: new Date(NOW - 3 * HOUR).toISOString(),
    comment: 'Clear and helpful instructions',
    runId: 'run-101',
    intent: 'jira_create',
    domain: 'project_management',
    model: 'claude-sonnet-4-20250514',
    promptVersion: 2,
    toolsUsed: ['jira_create_issue'],
    durationMs: 1250,
    tags: ['jira', 'tools'],
    templateId: 'template-support',
  },
  {
    feedbackId: 'fb-2',
    query: 'Summarize the latest sprint retrospective notes',
    response: 'Based on the Confluence page, the key takeaways from the sprint retrospective are: 1) Deploy pipeline improvements reduced build times by 40%, 2) Need more code review capacity, 3) Customer feedback loop needs shortening.',
    rating: 'thumbs_up' as const,
    timestamp: new Date(NOW - 6 * HOUR).toISOString(),
    comment: null,
    runId: 'run-102',
    intent: 'content_summary',
    domain: 'knowledge_base',
    model: 'claude-sonnet-4-20250514',
    promptVersion: 2,
    toolsUsed: ['confluence_get_page'],
    durationMs: 3400,
    tags: ['confluence', 'summary'],
    templateId: 'template-support',
  },
  {
    feedbackId: 'fb-3',
    query: 'What is the current deployment status?',
    response: 'I was unable to retrieve the deployment status. The monitoring endpoint returned an error.',
    rating: 'thumbs_down' as const,
    timestamp: new Date(NOW - DAY).toISOString(),
    comment: 'Should have retried or shown cached data',
    runId: 'run-103',
    intent: 'status_check',
    domain: 'devops',
    model: 'claude-sonnet-4-20250514',
    promptVersion: 1,
    toolsUsed: [],
    durationMs: 820,
    tags: ['monitoring', 'error'],
    templateId: null,
  },
  {
    feedbackId: 'fb-4',
    query: 'Calculate the cost breakdown for tenant acme-corp this month',
    response: 'The cost breakdown for acme-corp this month: API calls: $245.80, Token usage: $1,892.50, Storage: $12.00. Total: $2,150.30',
    rating: 'thumbs_up' as const,
    timestamp: new Date(NOW - 2 * DAY).toISOString(),
    comment: 'Accurate numbers, well formatted',
    runId: 'run-104',
    intent: 'cost_analysis',
    domain: 'billing',
    model: 'claude-opus-4-20250514',
    promptVersion: 3,
    toolsUsed: ['billing_query', 'calculator'],
    durationMs: 5200,
    tags: ['billing', 'analytics'],
    templateId: 'template-sales',
  },
]

function getMockFeedback() {
  return [
    {
      ...mockFeedback[0],
      query: '새 Jira 티켓은 어떻게 만드나요?',
      response: 'jira_create_issue 도구를 사용하여 새 Jira 티켓을 생성할 수 있습니다. 프로젝트 키, 이슈 유형, 요약을 지정하세요.',
      comment: '명확하고 도움이 되는 안내',
    },
    {
      ...mockFeedback[1],
      query: '최신 스프린트 회고 노트를 요약해 주세요',
      response: 'Confluence 페이지를 기반으로 스프린트 회고의 주요 내용은 다음과 같습니다: 1) 배포 파이프라인 개선으로 빌드 시간 40% 단축, 2) 코드 리뷰 역량 강화 필요, 3) 고객 피드백 루프 단축 필요.',
    },
    {
      ...mockFeedback[2],
      query: '현재 배포 상태가 어떻게 되나요?',
      response: '배포 상태를 조회할 수 없었습니다. 모니터링 엔드포인트에서 오류가 반환되었습니다.',
      comment: '재시도하거나 캐시된 데이터를 보여줬어야 함',
    },
    {
      ...mockFeedback[3],
      query: '이번 달 테넌트 acme-corp의 비용 내역을 계산해 주세요',
      response: '이번 달 acme-corp의 비용 내역: API 호출: $245.80, 토큰 사용: $1,892.50, 스토리지: $12.00. 합계: $2,150.30',
      comment: '정확한 수치, 깔끔한 포맷',
    },
  ].map((entry) => {
    const promotable = entry.feedbackId === 'fb-3'
    const promoted = promotedFeedbackIds.has(entry.feedbackId)
    const synced = syncedFeedbackIds.has(entry.feedbackId)
    return {
      ...entry,
      reviewStatus: synced || !promotable ? 'done' : 'inbox',
      reviewTags: synced
        ? ['promoted', 'langsmith', 'collection:rag-ingestion-candidate']
        : promoted ? ['promoted'] : [],
      reviewedBy: promoted ? 'admin-dev' : null,
      reviewedAt: promoted ? new Date(NOW).toISOString() : null,
      reviewNote: synced
        ? 'Promoted to regression eval and reviewed in hardening/LangSmith. Required readiness reports: hardening_suite, langsmith_eval_sync.'
        : promoted
          ? 'Eval case case_feedback_run_103 promoted from run-103; LangSmith sync pending.'
          : null,
      version: promoted ? 2 : 1,
      updatedAt: new Date(NOW).toISOString(),
      readyNextActionIds: promotable && !promoted ? ['promote-eval'] : [],
      blockedNextActionIds: promoted && !synced ? ['review-done'] : [],
      nextActionStates: promotable
        ? {
            'promote-eval': promoted ? 'passed' : 'ready',
            'review-done': synced ? 'passed' : 'blocked',
          }
        : {},
      nextActions: promotable ? [{
        id: 'promote-eval',
        label: 'Promote the feedback run into a source-controlled eval case',
        feedbackId: entry.feedbackId,
        evalCaseId: 'case_feedback_run_103',
        sourceRunId: 'run-103',
        feedbackTags: ['documents-ask', 'citation-failure'],
        workflowTags: ['collection:rag-ingestion-candidate'],
        expectedAnswers: ['[deployment_status:0]'],
        datasetName: 'reactor-release-regression',
        reportFile: 'reports/langsmith-eval-sync.json',
        requiredReadinessReports: ['langsmith_eval_sync'],
      }] : [],
    }
  })
}

const promotedFeedbackIds = new Set<string>()
const syncedFeedbackIds = new Set<string>()

export const feedbackHandlers = [
  http.post('/api/feedback', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({
      feedbackId: 'fb-rag-probe-1',
      query: body.query ?? '',
      response: body.response ?? '',
      rating: body.rating ?? 'thumbs_down',
      source: body.source ?? 'api',
      timestamp: new Date(NOW).toISOString(),
      comment: body.comment ?? null,
      runId: body.runId ?? null,
      tags: body.tags ?? [],
      reviewStatus: 'inbox',
      reviewTags: [],
      reviewedBy: null,
      reviewedAt: null,
      reviewNote: null,
      version: 1,
      updatedAt: new Date(NOW).toISOString(),
      readyNextActionIds: ['promote-eval-case'],
    }, { status: 201 })
  }),

  http.get('/api/feedback', () => {
    const items = getMockFeedback()
    return HttpResponse.json({
      items,
      nextCursor: null,
      prevCursor: null,
      approximateTotal: items.length,
    })
  }),

  http.get('/api/feedback/unreviewed-count', () => {
    const count = getMockFeedback().filter((entry) => entry.reviewStatus === 'inbox').length
    return HttpResponse.json({ count })
  }),

  http.get('/api/feedback/stats', () => {
    const entries = getMockFeedback()
    const positive = entries.filter((entry) => entry.rating === 'thumbs_up').length
    const negative = entries.length - positive
    return HttpResponse.json({
      period: { from: new Date(NOW - 7 * DAY).toISOString(), to: new Date(NOW).toISOString() },
      total: entries.length,
      positive,
      negative,
      negativeThisPeriod: negative,
      previousPeriodNegative: 1,
      negativeChange: 0,
      positiveRate: positive / entries.length,
      previousPeriodRate: 0.75,
      commentRate: 0.75,
      byDay: [],
      topNegativeDomains: [],
      topNegativeIntents: [],
      topNegativeTools: [],
      inboxCount: entries.filter((entry) => entry.reviewStatus === 'inbox').length,
      doneCount: entries.filter((entry) => entry.reviewStatus === 'done').length,
    })
  }),

  http.get('/api/admin/evals/runs', () => {
    return HttpResponse.json([{
      eval_run_id: 'eval-feedback-regression-1',
      total_cases: 12,
      pass_count: 12,
      avg_score: 1,
      avg_latency_ms: 0,
      total_tokens: 0,
      total_cost: 0,
      started_at: new Date(NOW - HOUR).toISOString(),
      ended_at: new Date(NOW - HOUR + 10_000).toISOString(),
    }])
  }),

  http.get('/api/admin/evals/pass-rate', () => {
    return HttpResponse.json([
      {
        day: new Date(NOW - 2 * DAY).toISOString().slice(0, 10),
        total: 10,
        passed: 8,
        avg_score: 0.84,
      },
      {
        day: new Date(NOW - DAY).toISOString().slice(0, 10),
        total: 12,
        passed: 12,
        avg_score: 1,
      },
    ])
  }),

  http.get('/api/admin/agent-eval/cases', () => {
    return HttpResponse.json(persistedEvalCases)
  }),

  http.get('/api/admin/followup-suggestions/stats', () => {
    return HttpResponse.json({
      windowHours: 24,
      totalImpressions: 40,
      totalClicks: 8,
      ctr: 0.2,
      byCategory: [],
    })
  }),

  http.get('/api/feedback/:id', ({ params }) => {
    const feedback = getMockFeedback()
    const entry = feedback.find(f => f.feedbackId === params.id)
    if (!entry) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json(entry)
  }),

  http.get('/api/feedback/export', () => {
    return HttpResponse.json({
      version: 1,
      exportedAt: new Date().toISOString(),
      source: 'reactor-admin',
      items: getMockFeedback(),
    })
  }),

  http.post('/api/admin/agent-eval/cases/promote', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json({
      id: body.id,
      name: body.name,
      sourceRunId: body.runId,
      tags: body.tags ?? [],
      enabled: true,
      assertionCount: 1,
      nextActions: [],
    })
  }),

  http.post('/api/admin/agent-eval/langsmith/sync', async ({ request }) => {
    const body = await request.json() as { datasetName: string; caseIds: string[] }
    const caseIds = body.caseIds.length > 0
      ? body.caseIds
      : persistedEvalCases.map((evalCase) => evalCase.id)
    const caseSourceRunIds = Object.fromEntries(
      persistedEvalCases
        .filter((evalCase) => caseIds.includes(evalCase.id))
        .map((evalCase) => [evalCase.id, evalCase.sourceRunId]),
    )
    return HttpResponse.json({
      ok: true,
      status: 'passed',
      scope: 'langsmith_persisted_eval_dataset_sync',
      mode: 'langsmith_dataset_sync',
      datasetName: body.datasetName,
      created: false,
      examples: caseIds.length,
      exampleIds: caseIds.map((caseId) => `example-${caseId}`),
      caseIds,
      metadataCaseIds: caseIds,
      sourceRunIds: Object.values(caseSourceRunIds),
      caseSourceRunIds,
      splitCounts: { regression: caseIds.length },
      secretFree: true,
      exampleContract: { secretScan: { enabled: true } },
      sdkContract: { sdk: 'langsmith', source: 'persisted_tenant_eval_cases' },
    })
  }),

  http.patch('/api/feedback/:id', async ({ params, request }) => {
    promotedFeedbackIds.add(String(params.id))
    const body = await request.json() as Record<string, unknown>
    if (body.status === 'done') syncedFeedbackIds.add(String(params.id))
    const entry = getMockFeedback().find((item) => item.feedbackId === params.id)
    if (!entry) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json({
      ...entry,
      reviewStatus: body.status ?? entry.reviewStatus,
      reviewTags: body.status === 'done'
        ? ['promoted', 'langsmith', 'collection:rag-ingestion-candidate']
        : ['promoted', 'collection:rag-ingestion-candidate'],
      reviewNote: body.note ?? entry.reviewNote,
      version: 2,
    })
  }),
]

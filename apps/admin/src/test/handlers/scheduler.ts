import { http, HttpResponse } from 'msw'
import { NOW, HOUR, DAY } from './shared'

export const mockSchedulerJobs = [
  {
    id: 'job-1',
    name: 'Daily Digest',
    description: 'Generate and post daily summary of Jira and Confluence updates to Slack',
    cronExpression: '0 9 * * *',
    timezone: 'Asia/Seoul',
    jobType: 'AGENT' as const,
    mcpServerName: null,
    toolName: null,
    toolArguments: {},
    agentPrompt: 'Summarize all Jira ticket updates and new Confluence pages from the last 24 hours. Format as a digest and post to the #daily-updates Slack channel.',
    personaId: 'persona-1',
    agentSystemPrompt: null,
    agentModel: 'claude-sonnet-4-20250514',
    agentMaxToolCalls: 20,
    slackChannelId: 'C0123DAILY',
    teamsWebhookUrl: null,
    retryOnFailure: true,
    maxRetryCount: 2,
    executionTimeoutMs: 120000,
    enabled: true,
    lastRunAt: NOW - 14 * HOUR,
    lastStatus: 'SUCCESS' as const,
    lastResult: 'Generated digest with 12 items',
    lastResultPreview: 'Generated digest with 12 items from Jira and Confluence',
    lastFailureReason: null,
    createdAt: NOW - 14 * DAY,
    updatedAt: NOW - 14 * HOUR,
  },
  {
    id: 'job-2',
    name: 'Swagger Sync',
    description: 'Sync all registered Swagger/OpenAPI spec sources',
    cronExpression: '0 */6 * * *',
    timezone: 'UTC',
    jobType: 'MCP_TOOL' as const,
    mcpServerName: 'swagger',
    toolName: 'swagger_sync_all',
    toolArguments: { includeArchived: false },
    agentPrompt: null,
    personaId: null,
    agentSystemPrompt: null,
    agentModel: null,
    agentMaxToolCalls: null,
    slackChannelId: null,
    teamsWebhookUrl: null,
    retryOnFailure: true,
    maxRetryCount: 3,
    executionTimeoutMs: 60000,
    enabled: true,
    lastRunAt: NOW - 26 * HOUR,
    lastStatus: 'SUCCESS' as const,
    lastResult: 'Synced 3 sources',
    lastResultPreview: 'Synced 3 spec sources, 0 changes detected',
    lastFailureReason: null,
    createdAt: NOW - 20 * DAY,
    updatedAt: NOW - 26 * HOUR,
  },
  {
    id: 'job-3',
    name: 'Weekly Report',
    description: 'Compile weekly metrics report and email to stakeholders',
    cronExpression: '0 8 * * 1',
    timezone: 'Asia/Seoul',
    jobType: 'AGENT' as const,
    mcpServerName: null,
    toolName: null,
    toolArguments: {},
    agentPrompt: 'Compile a weekly report of key platform metrics including API usage, tool call counts, feedback scores, and cost analysis. Send to ops@example.com.',
    personaId: null,
    agentSystemPrompt: 'You are an operations analyst assistant.',
    agentModel: 'claude-opus-4-20250514',
    agentMaxToolCalls: 30,
    slackChannelId: null,
    teamsWebhookUrl: null,
    retryOnFailure: false,
    maxRetryCount: 0,
    executionTimeoutMs: 300000,
    enabled: false,
    lastRunAt: NOW - 8 * DAY,
    lastStatus: 'FAILED' as const,
    lastResult: null,
    lastResultPreview: null,
    lastFailureReason: 'Email service unavailable',
    createdAt: NOW - 30 * DAY,
    updatedAt: NOW - 8 * DAY,
  },
]

function getMockSchedulerJobs() {
  return [
    {
      ...mockSchedulerJobs[0],
      name: '일일 요약',
      description: 'Jira와 Confluence 업데이트의 일일 요약을 생성하여 Slack에 게시',
      agentPrompt: '지난 24시간 동안의 모든 Jira 티켓 업데이트와 새 Confluence 페이지를 요약하세요. 다이제스트 형식으로 정리하여 #daily-updates Slack 채널에 게시하세요.',
      lastResult: '12개 항목으로 요약 생성 완료',
      lastResultPreview: 'Jira와 Confluence에서 12개 항목으로 요약 생성 완료',
    },
    {
      ...mockSchedulerJobs[1],
      name: 'Swagger 동기화',
      description: '등록된 모든 Swagger/OpenAPI 스펙 소스 동기화',
      lastResult: '3개 소스 동기화 완료',
      lastResultPreview: '3개 스펙 소스 동기화 완료, 변경 사항 없음',
    },
    {
      ...mockSchedulerJobs[2],
      name: '주간 보고서',
      description: '주간 메트릭 보고서를 작성하여 이해관계자에게 이메일 전송',
      agentPrompt: 'API 사용량, 도구 호출 횟수, 피드백 점수, 비용 분석을 포함한 주간 주요 플랫폼 메트릭 보고서를 작성하세요. ops@example.com로 전송하세요.',
      agentSystemPrompt: '당신은 운영 분석 어시스턴트입니다.',
      lastFailureReason: '이메일 서비스 사용 불가',
    },
  ]
}

export const mockSchedulerExecutions = [
  {
    id: 'exec-1',
    jobId: 'job-1',
    jobName: 'Daily Digest',
    status: 'SUCCESS' as const,
    result: 'Generated digest with 12 items from Jira and Confluence. Posted to #daily-updates.',
    resultPreview: 'Generated digest with 12 items from Jira and Confluence',
    failureReason: null,
    durationMs: 15400,
    dryRun: false,
    startedAt: NOW - 14 * HOUR,
    completedAt: NOW - 14 * HOUR + 15400,
  },
  {
    id: 'exec-2',
    jobId: 'job-1',
    jobName: 'Daily Digest',
    status: 'SUCCESS' as const,
    result: 'Generated digest with 8 items.',
    resultPreview: 'Generated digest with 8 items',
    failureReason: null,
    durationMs: 12300,
    dryRun: false,
    startedAt: NOW - 38 * HOUR,
    completedAt: NOW - 38 * HOUR + 12300,
  },
]

function getMockSchedulerExecutions() {
  return [
    {
      ...mockSchedulerExecutions[0],
      jobName: '일일 요약',
      result: 'Jira와 Confluence에서 12개 항목으로 요약 생성 완료. #daily-updates에 게시됨.',
      resultPreview: 'Jira와 Confluence에서 12개 항목으로 요약 생성 완료',
    },
    {
      ...mockSchedulerExecutions[1],
      jobName: '일일 요약',
      result: '8개 항목으로 요약 생성 완료.',
      resultPreview: '8개 항목으로 요약 생성 완료',
    },
  ]
}

export const schedulerHandlers = [
  http.get('/api/scheduler/jobs', () => {
    return HttpResponse.json(getMockSchedulerJobs())
  }),

  http.get('/api/scheduler/jobs/:id', ({ params }) => {
    const jobs = getMockSchedulerJobs()
    const job = jobs.find(j => j.id === params.id)
    if (!job) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json(job)
  }),

  http.post('/api/scheduler/jobs', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json(
      { id: 'job-new', ...body, enabled: true, lastRunAt: null, lastStatus: null, lastResult: null, lastResultPreview: null, lastFailureReason: null, createdAt: NOW, updatedAt: NOW },
      { status: 201 },
    )
  }),

  http.put('/api/scheduler/jobs/:id', async ({ params, request }) => {
    const body = await request.json() as Record<string, unknown>
    const jobs = getMockSchedulerJobs()
    const job = jobs.find(j => j.id === params.id)
    if (!job) return HttpResponse.json({ error: 'Not found' }, { status: 404 })
    return HttpResponse.json({ ...job, ...body, updatedAt: NOW })
  }),

  http.delete('/api/scheduler/jobs/:id', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/scheduler/jobs/:id/trigger', () => {
    return HttpResponse.json('작업이 성공적으로 트리거되었습니다')
  }),

  http.post('/api/scheduler/jobs/:id/dry-run', () => {
    return HttpResponse.json('드라이런 완료: 현재 설정으로 실행됩니다')
  }),

  http.get('/api/scheduler/jobs/:id/executions', () => {
    return HttpResponse.json(getMockSchedulerExecutions())
  }),
]

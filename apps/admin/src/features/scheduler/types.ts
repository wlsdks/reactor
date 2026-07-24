export type JobType = 'MCP_TOOL' | 'AGENT' | 'PROMPT_LAB_AUTO_OPTIMIZE'
export type JobExecutionStatus = 'SUCCESS' | 'FAILED' | 'RUNNING' | 'SKIPPED'

export interface ScheduledJobResponse {
  id: string
  name: string
  description: string | null
  cronExpression: string
  timezone: string
  jobType: JobType
  mcpServerName: string | null
  toolName: string | null
  toolArguments: Record<string, unknown>
  agentPrompt: string | null
  personaId: string | null
  agentSystemPrompt: string | null
  agentModel: string | null
  agentMaxToolCalls: number | null
  tags: string[]
  slackChannelId: string | null
  teamsWebhookUrl: string | null
  retryOnFailure: boolean
  maxRetryCount: number
  executionTimeoutMs: number | null
  enabled: boolean
  lastRunAt: number | null
  lastStatus: JobExecutionStatus | null
  lastResult: string | null
  lastResultPreview: string | null
  lastFailureReason: string | null
  createdAt: number
  updatedAt: number
}

export interface CreateScheduledJobRequest {
  name: string
  description?: string
  cronExpression: string
  timezone?: string
  jobType?: JobType
  mcpServerName?: string
  toolName?: string
  toolArguments?: Record<string, unknown>
  agentPrompt?: string
  personaId?: string
  agentSystemPrompt?: string
  agentModel?: string
  agentMaxToolCalls?: number
  tags?: string[]
  slackChannelId?: string
  teamsWebhookUrl?: string
  retryOnFailure?: boolean
  maxRetryCount?: number
  executionTimeoutMs?: number
  enabled?: boolean
}

export interface ScheduledJobExecutionResponse {
  id: string
  jobId: string
  jobName: string
  status: JobExecutionStatus
  result: string | null
  resultPreview: string | null
  failureReason: string | null
  durationMs: number
  dryRun: boolean
  startedAt: number
  completedAt: number | null
}

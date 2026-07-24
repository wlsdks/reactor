import { describe, expect, it } from 'vitest'
import {
  createEmptySchedulerJobForm,
  schedulerJobToForm,
  summarizeSchedulerFormReadiness,
  validateSchedulerJobForm,
} from '../schedulerForm'
import type { ScheduledJobResponse } from '../types'

function buildJob(overrides: Partial<ScheduledJobResponse> = {}): ScheduledJobResponse {
  return {
    id: 'job-1',
    name: 'Daily Ops Digest',
    description: 'Send a digest',
    cronExpression: '0 * * * *',
    timezone: 'Asia/Seoul',
    jobType: 'MCP_TOOL',
    mcpServerName: 'atlassian',
    toolName: 'jira_search',
    toolArguments: { projectKey: 'OPS' },
    agentPrompt: null,
    personaId: null,
    agentSystemPrompt: null,
    agentModel: null,
    agentMaxToolCalls: null,
    tags: ['ops', 'digest'],
    slackChannelId: 'C_OPS',
    teamsWebhookUrl: null,
    retryOnFailure: true,
    maxRetryCount: 4,
    executionTimeoutMs: 60000,
    enabled: true,
    lastRunAt: 1710000000000,
    lastStatus: 'SUCCESS',
    lastResult: 'ok',
    lastResultPreview: 'ok',
    lastFailureReason: null,
    createdAt: 1710000000000,
    updatedAt: 1710000000000,
    ...overrides,
  }
}

describe('schedulerForm', () => {
  it('hydrates hidden scheduler config into editable form state', () => {
    const form = schedulerJobToForm(buildJob())

    expect(form.toolArgumentsRaw).toContain('"projectKey": "OPS"')
    expect(form.executionTimeoutMs).toBe('60000')
    expect(form.maxRetryCount).toBe('4')
  })

  it('builds an MCP tool request from the full form state', () => {
    const form = schedulerJobToForm(buildJob())
    const result = validateSchedulerJobForm(form)

    expect('request' in result).toBe(true)
    if (!('request' in result)) return

    expect(result.request.mcpServerName).toBe('atlassian')
    expect(result.request.toolName).toBe('jira_search')
    expect(result.request.toolArguments).toEqual({ projectKey: 'OPS' })
    expect(result.request.executionTimeoutMs).toBe(60000)
    expect(result.request.maxRetryCount).toBe(4)
    expect(result.request.tags).toEqual(['ops', 'digest'])
  })

  it('rejects invalid MCP tool payloads and missing AGENT prompts', () => {
    const invalidToolForm = schedulerJobToForm(buildJob())
    invalidToolForm.toolArgumentsRaw = '[]'

    expect(validateSchedulerJobForm(invalidToolForm)).toEqual({
      errorId: 'toolArgumentsObjectRequired',
    })

    const invalidAgentForm = createEmptySchedulerJobForm()
    invalidAgentForm.name = 'Agent briefing'
    invalidAgentForm.agentPrompt = '   '

    expect(validateSchedulerJobForm(invalidAgentForm)).toEqual({
      errorId: 'agentPromptRequired',
    })
  })

  it('summarizes save readiness for scheduler jobs', () => {
    const form = schedulerJobToForm(buildJob({ slackChannelId: null, teamsWebhookUrl: null }))
    const summary = summarizeSchedulerFormReadiness(form)

    expect(summary.status).toBe('WARN')
    expect(summary.signals.find((signal) => signal.id === 'jobTarget')?.detailId).toBe('toolTargetReady')
    expect(summary.signals.find((signal) => signal.id === 'delivery')?.detailId).toBe('deliveryMissing')
  })

  it('preserves prompt optimization configuration and tags', () => {
    const form = schedulerJobToForm(buildJob({
      jobType: 'PROMPT_LAB_AUTO_OPTIMIZE',
      mcpServerName: null,
      toolName: null,
      toolArguments: { templateId: 'prompt-1' },
      tags: ['prompt-lab', 'nightly'],
    }))

    const result = validateSchedulerJobForm(form)

    expect('request' in result).toBe(true)
    if (!('request' in result)) return
    expect(result.request.toolArguments).toEqual({ templateId: 'prompt-1' })
    expect(result.request.tags).toEqual(['prompt-lab', 'nightly'])
  })
})

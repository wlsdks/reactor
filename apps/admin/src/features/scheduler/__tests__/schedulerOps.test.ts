import { describe, expect, it } from 'vitest'
import { classifyLoadIssue } from '../../../shared/lib/ops'
import { filterSchedulerJobs, summarizeSchedulerOps } from '../schedulerOps'
import type { ScheduledJobResponse } from '../types'

function buildJob(overrides: Partial<ScheduledJobResponse> = {}): ScheduledJobResponse {
  return {
    id: 'job-1',
    name: 'Daily Ops Digest',
    description: 'Send a digest',
    cronExpression: '0 * * * *',
    timezone: 'Asia/Seoul',
    jobType: 'AGENT',
    mcpServerName: null,
    toolName: null,
    toolArguments: {},
    agentPrompt: 'Summarize incidents',
    personaId: null,
    agentSystemPrompt: null,
    agentModel: 'gpt-5',
    agentMaxToolCalls: 4,
    tags: ['operations'],
    slackChannelId: 'C_OPS',
    teamsWebhookUrl: null,
    retryOnFailure: true,
    maxRetryCount: 3,
    executionTimeoutMs: 300000,
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

describe('schedulerOps', () => {
  it('classifies load failures for the recovery console', () => {
    expect(classifyLoadIssue('HTTP 404')).toBe('notAdvertised')
    expect(classifyLoadIssue('HTTP 403')).toBe('accessDenied')
    expect(classifyLoadIssue('socket hang up')).toBe('transportFailure')
    expect(classifyLoadIssue('HTTP 500')).toBe('httpError')
  })

  it('summarizes failed and stale enabled jobs as operator attention', () => {
    const summary = summarizeSchedulerOps([
      buildJob(),
      buildJob({
        id: 'job-2',
        name: 'Failed job',
        lastStatus: 'FAILED',
        lastFailureReason: 'upstream timeout',
      }),
      buildJob({
        id: 'job-3',
        name: 'Never ran',
        lastRunAt: null,
        lastStatus: null,
      }),
      buildJob({
        id: 'job-4',
        name: 'Disabled job',
        enabled: false,
        lastRunAt: null,
        lastStatus: null,
      }),
    ], null)

    expect(summary.status).toBe('FAIL')
    expect(summary.totalJobs).toBe(4)
    expect(summary.enabledJobs).toBe(3)
    expect(summary.failedJobs).toBe(1)
    expect(summary.staleJobs).toBe(1)
    expect(summary.attentionJobs).toBe(2)
    expect(summary.signals.find((signal) => signal.id === 'failureBacklog')?.detailId).toBe('failureBacklogPresent')
    expect(summary.signals.find((signal) => signal.id === 'historyCoverage')?.detailId).toBe('historyCoverageMissing')
  })

  it('filters the job table to operator-focused quick filters', () => {
    const jobs = [
      buildJob({
        id: 'job-failed-no-retry',
        name: 'Failed no retry',
        lastStatus: 'FAILED',
        retryOnFailure: false,
      }),
      buildJob({
        id: 'job-never-run',
        name: 'Never ran',
        lastRunAt: null,
        lastStatus: null,
      }),
      buildJob({
        id: 'job-healthy',
        name: 'Healthy',
      }),
    ]

    const summary = summarizeSchedulerOps(jobs, null)

    expect(filterSchedulerJobs(jobs, summary.attentionItems, 'attention').map((job) => job.id)).toEqual([
      'job-failed-no-retry',
      'job-never-run',
    ])
    expect(filterSchedulerJobs(jobs, summary.attentionItems, 'noRetry').map((job) => job.id)).toEqual([
      'job-failed-no-retry',
    ])
    expect(filterSchedulerJobs(jobs, summary.attentionItems, 'neverRun').map((job) => job.id)).toEqual([
      'job-never-run',
    ])
  })
})

import { summarizeStatus, classifyLoadIssue, type OpsStatus, type LoadIssue } from '../../shared/lib/ops'
import type { ScheduledJobResponse } from './types'

export interface SchedulerSignal {
  id: 'schedulerContract' | 'enabledCoverage' | 'failureBacklog' | 'historyCoverage'
  status: OpsStatus
  detailId:
    | 'contractHealthy'
    | 'contractMissing'
    | 'contractDenied'
    | 'contractTransport'
    | 'contractError'
    | 'enabledCoverageReady'
    | 'enabledCoverageMissing'
    | 'failureBacklogClear'
    | 'failureBacklogPresent'
    | 'historyCoverageReady'
    | 'historyCoverageMissing'
  meta?: {
    count?: number
    total?: number
  }
}

export interface SchedulerAttentionItem {
  id: string
  job: ScheduledJobResponse
  kind: 'failed' | 'failedNoRetry' | 'neverRun' | 'stuckRunning'
  status: OpsStatus
  detailId: 'lastRunFailed' | 'lastRunFailedNoRetry' | 'neverExecuted' | 'runningTooLong'
}

export interface SchedulerOpsSummary {
  status: OpsStatus
  loadIssue: LoadIssue | null
  totalJobs: number
  enabledJobs: number
  attentionJobs: number
  failedJobs: number
  staleJobs: number
  retryGapJobs: number
  signals: SchedulerSignal[]
  attentionItems: SchedulerAttentionItem[]
}

export type SchedulerQuickFilter =
  | 'all'
  | 'attention'
  | 'failed'
  | 'neverRun'
  | 'stuckRunning'
  | 'noRetry'

function summarizeContractSignal(loadIssue: LoadIssue | null): SchedulerSignal {
  if (loadIssue === 'notAdvertised') {
    return { id: 'schedulerContract', status: 'WARN', detailId: 'contractMissing' }
  }
  if (loadIssue === 'accessDenied') {
    return { id: 'schedulerContract', status: 'FAIL', detailId: 'contractDenied' }
  }
  if (loadIssue === 'transportFailure') {
    return { id: 'schedulerContract', status: 'FAIL', detailId: 'contractTransport' }
  }
  if (loadIssue === 'httpError') {
    return { id: 'schedulerContract', status: 'FAIL', detailId: 'contractError' }
  }
  return { id: 'schedulerContract', status: 'PASS', detailId: 'contractHealthy' }
}

function buildAttentionItems(jobs: ScheduledJobResponse[], now: number): SchedulerAttentionItem[] {
  const items: SchedulerAttentionItem[] = []

  for (const job of jobs) {
    if (job.lastStatus === 'FAILED') {
      items.push({
        id: `${job.id}:${job.retryOnFailure ? 'failed' : 'failed-no-retry'}`,
        job,
        kind: job.retryOnFailure ? 'failed' : 'failedNoRetry',
        status: job.retryOnFailure ? 'WARN' : 'FAIL',
        detailId: job.retryOnFailure ? 'lastRunFailed' : 'lastRunFailedNoRetry',
      })
      continue
    }

    if (job.enabled && job.lastRunAt == null) {
      items.push({
        id: `${job.id}:never-run`,
        job,
        kind: 'neverRun',
        status: 'WARN',
        detailId: 'neverExecuted',
      })
      continue
    }

    if (
      job.enabled
      && job.lastStatus === 'RUNNING'
      && job.lastRunAt != null
      && now - job.lastRunAt > 60 * 60 * 1000
    ) {
      items.push({
        id: `${job.id}:running-too-long`,
        job,
        kind: 'stuckRunning',
        status: 'FAIL',
        detailId: 'runningTooLong',
      })
    }
  }

  return items.sort((left, right) => {
    if (left.status !== right.status) {
      return left.status === 'FAIL' ? -1 : 1
    }
    return left.job.name.localeCompare(right.job.name)
  })
}

export function summarizeSchedulerOps(
  jobs: ScheduledJobResponse[],
  loadError: string | null,
  now = Date.now(),
): SchedulerOpsSummary {
  const loadIssue = classifyLoadIssue(loadError)
  const contractSignal = summarizeContractSignal(loadIssue)
  const attentionItems = buildAttentionItems(jobs, now)
  const enabledJobs = jobs.filter((job) => job.enabled).length
  const failedJobs = attentionItems.filter((item) => item.kind === 'failed' || item.kind === 'failedNoRetry').length
  const staleJobs = attentionItems.filter((item) => item.kind === 'neverRun').length
  const retryGapJobs = attentionItems.filter((item) => item.kind === 'failedNoRetry').length
  const jobsWithHistory = jobs.filter((job) => job.enabled && job.lastRunAt != null).length

  const signals: SchedulerSignal[] = [
    contractSignal,
    enabledJobs > 0
      ? {
          id: 'enabledCoverage',
          status: 'PASS',
          detailId: 'enabledCoverageReady',
          meta: { count: enabledJobs, total: jobs.length },
        }
      : {
          id: 'enabledCoverage',
          status: jobs.length === 0 ? 'WARN' : 'FAIL',
          detailId: 'enabledCoverageMissing',
        },
    failedJobs > 0
      ? {
          id: 'failureBacklog',
          status: 'FAIL',
          detailId: 'failureBacklogPresent',
          meta: { count: failedJobs },
        }
      : {
          id: 'failureBacklog',
          status: 'PASS',
          detailId: 'failureBacklogClear',
        },
    staleJobs > 0
      ? {
          id: 'historyCoverage',
          status: 'WARN',
          detailId: 'historyCoverageMissing',
          meta: { count: jobsWithHistory, total: enabledJobs },
        }
      : {
          id: 'historyCoverage',
          status: 'PASS',
          detailId: 'historyCoverageReady',
          meta: { count: jobsWithHistory, total: enabledJobs },
        },
  ]

  return {
    status: summarizeStatus(signals),
    loadIssue,
    totalJobs: jobs.length,
    enabledJobs,
    attentionJobs: attentionItems.length,
    failedJobs,
    staleJobs,
    retryGapJobs,
    signals,
    attentionItems,
  }
}

export function filterSchedulerJobs(
  jobs: ScheduledJobResponse[],
  attentionItems: SchedulerAttentionItem[],
  quickFilter: SchedulerQuickFilter,
): ScheduledJobResponse[] {
  if (quickFilter === 'all') return jobs

  const kindsByJobId = new Map<string, Set<SchedulerAttentionItem['kind']>>()
  for (const item of attentionItems) {
    const existing = kindsByJobId.get(item.job.id) ?? new Set<SchedulerAttentionItem['kind']>()
    existing.add(item.kind)
    kindsByJobId.set(item.job.id, existing)
  }

  return jobs.filter((job) => {
    const kinds = kindsByJobId.get(job.id)
    if (!kinds) return false

    switch (quickFilter) {
      case 'attention':
        return true
      case 'failed':
        return kinds.has('failed') || kinds.has('failedNoRetry')
      case 'neverRun':
        return kinds.has('neverRun')
      case 'stuckRunning':
        return kinds.has('stuckRunning')
      case 'noRetry':
        return kinds.has('failedNoRetry')
      default:
        return true
    }
  })
}

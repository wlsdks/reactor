import { describe, expect, it } from 'vitest'
import {
  dashboardExecutionTimestamp,
  deriveEmployeeValueFocus,
  describeTrustEventDetail,
  describeTrustEventScope,
  describeTrustEventType,
  humanizeAnswerMode,
  humanizeChannel,
  humanizeToolFamily,
  laneCoverageLabel,
  topBucketLabel,
} from '../presenters'

describe('dashboard presenters', () => {
  it('maps output guard events to stable dashboard labels', () => {
    expect(describeTrustEventType({
      occurredAt: 1,
      type: 'output_guard',
      severity: 'FAIL',
      action: 'rejected',
    })).toBe('OUTPUT_GUARD_REJECTED')
  })

  it('builds compact trust event detail strings', () => {
    expect(describeTrustEventDetail({
      occurredAt: 1,
      type: 'boundary_violation',
      severity: 'FAIL',
      queryLabel: 'Question cluster 93bd4b524029',
      violation: 'output_too_short',
      policy: 'fail',
    })).toBe('cluster:Question cluster 93bd4b524029 / output_too_short / policy:fail')
  })

  it('builds trust event scope with redacted channel and cluster id', () => {
    expect(describeTrustEventScope({
      occurredAt: 1,
      type: 'unverified_response',
      severity: 'WARN',
      channel: 'slack',
      queryCluster: '93bd4b524029',
    })).toBe('channel:slack / cluster:93bd4b524029')
  })

  it('prefers completed timestamp for scheduler executions', () => {
    expect(dashboardExecutionTimestamp({
      id: 'exec-1',
      jobId: 'job-1',
      jobName: 'Morning briefing',
      jobType: 'AGENT',
      status: 'SUCCESS',
      dryRun: false,
      durationMs: 1200,
      startedAt: 10,
      completedAt: 42,
    })).toBe(42)
  })

  it('humanizes value insight labels for dashboard display', () => {
    expect(humanizeAnswerMode('operational')).toBe('Operational')
    expect(humanizeChannel('slack')).toBe('Slack')
    expect(humanizeToolFamily('confluence')).toBe('Confluence')
    expect(topBucketLabel({ key: 'work', count: 3 })).toBe('Work: 3')
    expect(laneCoverageLabel(71)).toBe('71%')
  })

  it('derives routing focus when blocked traffic is dominated by unknown lane', () => {
    const hints = deriveEmployeeValueFocus({
      observedResponses: 5,
      groundedResponses: 1,
      groundedRatePercent: 20,
      blockedResponses: 4,
      interactiveResponses: 5,
      scheduledResponses: 0,
      answerModes: { unknown: 5 },
      lanes: [
        {
          answerMode: 'unknown',
          observedResponses: 5,
          groundedResponses: 1,
          blockedResponses: 4,
          groundedRatePercent: 20,
        },
      ],
      toolFamilies: [{ key: 'none', count: 5 }],
      topMissingQueries: [{
        queryCluster: 'f1e6a063a8d0',
        queryLabel: 'Question cluster f1e6a063a8d0',
        count: 4,
        lastOccurredAt: 1,
        blockReason: 'unverified_sources',
      }],
    })

    expect(hints[0]?.title).toBe('Routing or source coverage')
  })
})

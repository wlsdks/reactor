import { describe, expect, it } from 'vitest'
import {
  executionSummary,
  executionTimestamp,
  formatSchedulerDuration,
  formatSchedulerTimezone,
} from '../presenters'

describe('scheduler presenters', () => {
  it('prefers failure reason over generic preview', () => {
    expect(executionSummary({
      id: 'exec-1',
      jobId: 'job-1',
      jobName: 'Morning briefing',
      status: 'FAILED',
      result: "Job 'Morning briefing' failed: MCP server disconnected",
      resultPreview: "Job 'Morning briefing' failed: MCP server disconnected",
      failureReason: 'MCP server disconnected',
      durationMs: 1200,
      dryRun: false,
      startedAt: 10,
      completedAt: 20,
    })).toBe('MCP server disconnected')
  })

  it('uses completion time when available', () => {
    expect(executionTimestamp({
      id: 'exec-1',
      jobId: 'job-1',
      jobName: 'Morning briefing',
      status: 'SUCCESS',
      result: 'done',
      resultPreview: 'done',
      failureReason: null,
      durationMs: 1200,
      dryRun: false,
      startedAt: 10,
      completedAt: 42,
    })).toBe(42)
  })

  it('presents scheduling values in operator-facing Korean', () => {
    expect(formatSchedulerDuration(300_000)).toBe('5분')
    expect(formatSchedulerDuration(1_250)).toBe('1.3초')
    expect(formatSchedulerTimezone('Asia/Seoul')).toBe('한국 표준시 (서울)')
    expect(formatSchedulerTimezone('Europe/Paris')).toBe('Europe/Paris')
  })
})

import { describe, expect, it } from 'vitest'
import { classifyLoadIssue } from '../../../shared/lib/ops'
import { summarizeToolPolicyOps } from '../toolPolicyOps'
import type { ToolPolicyState } from '../types'

function buildState(overrides: Partial<ToolPolicyState> = {}): ToolPolicyState {
  return {
    configEnabled: true,
    dynamicEnabled: true,
    effective: {
      enabled: true,
      writeToolNames: ['write_file', 'apply_patch'],
      denyWriteChannels: ['commentary'],
      allowWriteToolNamesInDenyChannels: ['apply_patch'],
      allowWriteToolNamesByChannel: {
        summary: ['write_file'],
      },
      denyWriteMessage: 'Denied',
      createdAt: 1710000000000,
      updatedAt: 1710003600000,
    },
    stored: {
      enabled: true,
      writeToolNames: ['write_file'],
      denyWriteChannels: ['commentary'],
      allowWriteToolNamesInDenyChannels: [],
      allowWriteToolNamesByChannel: {},
      denyWriteMessage: 'Denied',
      createdAt: 1710000000000,
      updatedAt: 1710000000000,
    },
    ...overrides,
  }
}

describe('toolPolicyOps', () => {
  it('classifies tool policy load failures for operator runbooks', () => {
    expect(classifyLoadIssue('HTTP 404')).toBe('notAdvertised')
    expect(classifyLoadIssue('HTTP 403')).toBe('accessDenied')
    expect(classifyLoadIssue('socket hang up')).toBe('transportFailure')
    expect(classifyLoadIssue('HTTP 500')).toBe('httpError')
  })

  it('summarizes drift and coverage when policy data is available', () => {
    const summary = summarizeToolPolicyOps(buildState(), null)

    expect(summary.status).toBe('WARN')
    expect(summary.activeWriteTools).toBe(2)
    expect(summary.denyChannels).toBe(1)
    expect(summary.allowOverrides).toBe(2)
    expect(summary.diffFields).toEqual([
      'writeToolNames',
      'allowWriteToolNamesInDenyChannels',
      'allowWriteToolNamesByChannel',
    ])
  })

  it('returns degraded signals when the policy endpoint is unavailable', () => {
    const summary = summarizeToolPolicyOps(null, 'HTTP 404')

    expect(summary.status).toBe('WARN')
    expect(summary.loadIssue).toBe('notAdvertised')
    expect(summary.signals[0]).toMatchObject({
      id: 'policyContract',
      status: 'WARN',
      detailId: 'contractMissing',
    })
  })
})

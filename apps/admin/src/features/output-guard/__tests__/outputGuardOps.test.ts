import { describe, expect, it } from 'vitest'
import { getRegexIssue, summarizeOutputGuardOps, summarizeSimulation } from '../outputGuardOps'
import type { OutputGuardAuditLog, OutputGuardRule, SimulateOutputGuardResponse } from '../types'

function buildRule(overrides: Partial<OutputGuardRule> = {}): OutputGuardRule {
  return {
    id: 'rule-1',
    name: 'Credit card blocker',
    pattern: '\\b\\d{4}-\\d{4}-\\d{4}-\\d{4}\\b',
    action: 'REJECT',
    priority: 10,
    enabled: true,
    createdAt: 1710000000000,
    updatedAt: 1710003600000,
    ...overrides,
  }
}

function buildAudit(overrides: Partial<OutputGuardAuditLog> = {}): OutputGuardAuditLog {
  return {
    id: 'audit-1',
    ruleId: 'rule-1',
    action: 'SIMULATE',
    actor: 'ops-admin',
    detail: 'blocked sample content',
    createdAt: 1710007200000,
    ...overrides,
  }
}

function buildSimulation(
  overrides: Partial<SimulateOutputGuardResponse> = {},
): SimulateOutputGuardResponse {
  return {
    originalContent: 'card number: 4111-1111-1111-1111',
    resultContent: 'card number: [redacted]',
    blocked: false,
    modified: true,
    blockedByRuleId: null,
    blockedByRuleName: null,
    matchedRules: [],
    invalidRules: [],
    ...overrides,
  }
}

describe('outputGuardOps', () => {
  it('detects invalid regex patterns', () => {
    expect(getRegexIssue('(')).toMatch(/unterminated group/i)
    expect(getRegexIssue('\\bsecret\\b')).toBeNull()
  })

  it('marks coverage as pass when enabled reject rules and audits are available', () => {
    const summary = summarizeOutputGuardOps([buildRule()], [buildAudit()], null)

    expect(summary.status).toBe('PASS')
    expect(summary.enabledRules).toBe(1)
    expect(summary.rejectRules).toBe(1)
    expect(summary.auditRows).toBe(1)
    expect(summary.signals).toEqual([
      expect.objectContaining({ id: 'activeRules', status: 'PASS', detailId: 'activeRulesReady' }),
      expect.objectContaining({ id: 'regexValidity', status: 'PASS', detailId: 'regexValid' }),
      expect.objectContaining({ id: 'rejectCoverage', status: 'PASS', detailId: 'rejectCoverageReady' }),
      expect.objectContaining({ id: 'auditChannel', status: 'PASS', detailId: 'auditChannelReady' }),
    ])
  })

  it('surfaces fail and warn signals for missing active coverage and audit outages', () => {
    const summary = summarizeOutputGuardOps([
      buildRule({ id: 'rule-disabled', enabled: false, action: 'MASK' }),
      buildRule({ id: 'rule-bad', name: 'Broken detector', pattern: '(', enabled: true, action: 'MASK' }),
    ], [], 'audit feed unavailable')

    expect(summary.status).toBe('FAIL')
    expect(summary.invalidRules).toBe(1)
    expect(summary.rejectRules).toBe(0)
    expect(summary.signals).toEqual([
      expect.objectContaining({ id: 'activeRules', status: 'PASS', detailId: 'activeRulesReady' }),
      expect.objectContaining({
        id: 'regexValidity',
        status: 'FAIL',
        detailId: 'regexInvalid',
        meta: expect.objectContaining({ count: 1, names: ['Broken detector'] }),
      }),
      expect.objectContaining({ id: 'rejectCoverage', status: 'WARN', detailId: 'rejectCoverageMissing' }),
      expect.objectContaining({ id: 'auditChannel', status: 'WARN', detailId: 'auditChannelUnavailable' }),
    ])
  })

  it('summarizes simulation outcomes for blocked traffic and endpoint failures', () => {
    const blocked = summarizeSimulation(buildSimulation({
      blocked: true,
      modified: true,
      blockedByRuleName: 'Credit card blocker',
      matchedRules: [{ ruleId: 'rule-1', ruleName: 'Credit card blocker', action: 'REJECT', priority: 10 }],
      invalidRules: [{ ruleId: 'rule-bad', ruleName: 'Broken detector', reason: 'Unterminated group' }],
    }), null)
    const failed = summarizeSimulation(null, 'connection reset')

    expect(blocked).toEqual(expect.objectContaining({
      status: 'FAIL',
      blocked: true,
      modified: true,
      matchedRuleCount: 1,
      invalidRuleCount: 1,
      blockedBy: 'Credit card blocker',
      resultPreview: 'card number: [redacted]',
    }))
    expect(failed).toEqual(expect.objectContaining({
      status: 'FAIL',
      blocked: false,
      modified: false,
      resultPreview: 'connection reset',
    }))
  })
})

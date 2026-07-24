import { describe, expect, it } from 'vitest'
import ko from '../../../shared/i18n/ko.json'

describe('issue center translations', () => {
  it('covers every static issue title emitted by issueCenter', () => {
    expect(Object.keys(ko.issuesPage.titles).sort()).toEqual([
      'accessPolicy',
      'approvalRequest',
      'configReadiness',
      'preflight',
      'schedulerJob',
      'serverDetail',
      'serverDisconnected',
    ])
  })

  it('covers every static issue message emitted by issueCenter', () => {
    expect(Object.keys(ko.issuesPage.messages).sort()).toEqual([
      'detailUnavailable',
      'policyUnavailable',
      'preflightUnavailable',
    ])
  })

  it('covers every module label rendered by the optional topology', () => {
    expect(Object.keys(ko.issuesPage.topology)).toEqual(expect.arrayContaining([
      'toolPolicy',
      'outputGuard',
      'mcpSecurity',
      'audit',
      'scheduler',
      'approvals',
    ]))
  })

  it('covers MCP security and output guard signals emitted into the issue list', () => {
    expect(Object.keys(ko.mcpSecurityPage.signals).sort()).toEqual([
      'allowlistCoverage',
      'outputClamp',
      'policyContract',
      'policyDrift',
      'registryAlignment',
      'storedPolicy',
    ])
    expect(Object.keys(ko.outputGuardPage.signals).sort()).toEqual([
      'activeRules',
      'auditChannel',
      'regexValidity',
      'rejectCoverage',
    ])
  })

  it('covers every dynamic external-tool detail emitted by issueCenter', () => {
    expect(Object.keys(ko.mcpServers.configReadinessDetails).sort()).toEqual([
      'adminHmacDisabled',
      'adminHmacMissing',
      'adminHmacPlaceholder',
      'adminHmacReady',
      'adminTokenMissing',
      'adminTokenOptional',
      'adminTokenPlaceholder',
      'adminTokenReady',
      'adminUrlDerived',
      'adminUrlMissing',
      'adminUrlOptional',
      'adminUrlReady',
      'autoConnectDisabled',
      'autoConnectEnabled',
      'timeoutsDefault',
      'timeoutsNeedReview',
      'timeoutsReady',
      'transportCommandReady',
      'transportMissingCommand',
      'transportMissingUrl',
      'transportUrlReady',
    ])
    expect(Object.keys(ko.mcpServers.policySignalDetails).sort()).toEqual([
      'coverageOpenAll',
      'coveragePartiallyScoped',
      'coverageScoped',
      'directUrlLoadsAllowed',
      'directUrlLoadsBlocked',
      'dynamicModeDisabled',
      'dynamicModeEnabled',
      'dynamicModeUnknown',
      'dynamicPolicyDrifted',
      'dynamicPolicyInSync',
      'dynamicSnapshotMissing',
      'dynamicSnapshotNotUsed',
      'previewReadsAllowed',
      'previewReadsBlocked',
      'previewWritesAllowed',
      'previewWritesBlocked',
      'publishedOnlyEnforced',
      'publishedScopeOpen',
    ])
  })
})

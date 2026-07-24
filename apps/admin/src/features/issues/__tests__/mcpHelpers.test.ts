import { describe, it, expect } from 'vitest'
import {
  summarizeRegistryOverview,
  summarizePolicyDiagnostics,
  summarizeMcpSecurityOps,
  summarizeServerConfigReadiness,
  summarizeDraftConfigReadiness,
  classifyMcpSecurityLoadIssue,
  type ConfigReadinessSignal,
} from '../mcpHelpers'
import type { McpAccessPolicy, McpServerDetailResponse, McpServerResponse } from '../../mcp-servers/types'
import type { McpSecurityPolicyState, McpSecurityPolicyRuleSet } from '../../mcp-security/types'

// ──────────────────────────────────────────────────────────────────────────
// Builders
// ──────────────────────────────────────────────────────────────────────────

function buildServerResponse(overrides: Partial<McpServerResponse> = {}): McpServerResponse {
  return {
    id: 'srv',
    name: 'srv',
    description: null,
    transportType: 'SSE',
    autoConnect: true,
    status: 'CONNECTED',
    toolCount: 0,
    createdAt: 0,
    updatedAt: 0,
    ...overrides,
  }
}

function buildServerDetail(overrides: Partial<McpServerDetailResponse> = {}): McpServerDetailResponse {
  return {
    id: 'srv',
    name: 'atlassian',
    description: null,
    transportType: 'SSE',
    config: {},
    version: null,
    autoConnect: true,
    status: 'CONNECTED',
    tools: [],
    createdAt: 0,
    updatedAt: 0,
    ...overrides,
  }
}

function buildAtlassianPolicy(overrides: Partial<McpAccessPolicy> = {}): McpAccessPolicy {
  return {
    allowedJiraProjectKeys: [],
    allowedConfluenceSpaceKeys: [],
    allowedBitbucketRepositories: [],
    allowedSourceNames: [],
    allowPreviewReads: false,
    allowPreviewWrites: false,
    allowDirectUrlLoads: false,
    publishedOnly: true,
    ...overrides,
  }
}

function buildSwaggerPolicy(overrides: Partial<McpAccessPolicy> = {}): McpAccessPolicy {
  return {
    allowedJiraProjectKeys: [],
    allowedConfluenceSpaceKeys: [],
    allowedBitbucketRepositories: [],
    allowedSourceNames: [],
    allowPreviewReads: false,
    allowPreviewWrites: false,
    allowDirectUrlLoads: false,
    publishedOnly: true,
    ...overrides,
  }
}

function buildRuleSet(overrides: Partial<McpSecurityPolicyRuleSet> = {}): McpSecurityPolicyRuleSet {
  return {
    allowedServerNames: [],
    maxToolOutputLength: 65536,
    createdAt: 0,
    updatedAt: 0,
    ...overrides,
  }
}

function buildSecurityState(overrides: Partial<McpSecurityPolicyState> = {}): McpSecurityPolicyState {
  return {
    effective: buildRuleSet(),
    stored: null,
    configDefault: buildRuleSet(),
    ...overrides,
  }
}

// ──────────────────────────────────────────────────────────────────────────
// summarizeRegistryOverview
// ──────────────────────────────────────────────────────────────────────────

describe('summarizeRegistryOverview', () => {
  it('returns zero counts and null known servers when no servers exist', () => {
    const result = summarizeRegistryOverview([])
    expect(result.totalServers).toBe(0)
    expect(result.connectedCount).toBe(0)
    expect(result.disconnectedCount).toBe(0)
    expect(result.knownServers).toEqual([
      { id: 'atlassian', server: null },
      { id: 'swagger', server: null },
    ])
  })

  it('counts connected vs disconnected servers and matches the atlassian preset', () => {
    const result = summarizeRegistryOverview([
      buildServerResponse({ name: 'atlassian', status: 'CONNECTED' }),
      buildServerResponse({ name: 'other', status: 'DISCONNECTED' }),
    ])
    expect(result.totalServers).toBe(2)
    expect(result.connectedCount).toBe(1)
    expect(result.disconnectedCount).toBe(1)
    expect(result.knownServers.find((k) => k.id === 'atlassian')?.server?.name).toBe('atlassian')
    expect(result.knownServers.find((k) => k.id === 'swagger')?.server).toBeNull()
  })
})

// ──────────────────────────────────────────────────────────────────────────
// summarizeServerConfigReadiness / summarizeConfigReadiness branches
// ──────────────────────────────────────────────────────────────────────────

describe('summarizeServerConfigReadiness — transport signal', () => {
  it('returns FAIL when SSE transport has no URL', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({ transportType: 'SSE', config: {} }),
    )
    const transport = result.signals.find((s) => s.id === 'transportTarget')!
    expect(transport.status).toBe('FAIL')
    expect(transport.detailId).toBe('transportMissingUrl')
  })

  it('returns PASS when SSE transport has a valid http URL', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({
        transportType: 'SSE',
        name: 'atlassian',
        config: {
          url: 'https://example.com/sse',
          adminUrl: 'https://example.com/admin',
          adminToken: 'real-token',
        },
      }),
    )
    const transport = result.signals.find((s) => s.id === 'transportTarget')!
    expect(transport.status).toBe('PASS')
    expect(transport.detailId).toBe('transportUrlReady')
  })

  it('returns PASS when STDIO transport has a command', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({
        transportType: 'STDIO',
        config: { command: 'node server.js' },
      }),
    )
    const transport = result.signals.find((s) => s.id === 'transportTarget')!
    expect(transport.status).toBe('PASS')
    expect(transport.detailId).toBe('transportCommandReady')
  })

  it('returns FAIL when STDIO transport has no command', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({ transportType: 'STDIO', config: {} }),
    )
    const transport = result.signals.find((s) => s.id === 'transportTarget')!
    expect(transport.status).toBe('FAIL')
    expect(transport.detailId).toBe('transportMissingCommand')
  })
})

describe('summarizeServerConfigReadiness — admin URL signal', () => {
  it('returns PASS when adminUrl is a valid http URL', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({
        transportType: 'SSE',
        config: { url: 'https://x', adminUrl: 'https://admin', adminToken: 'real' },
      }),
    )
    const adminUrl = result.signals.find((s) => s.id === 'adminUrl')!
    expect(adminUrl.status).toBe('PASS')
    expect(adminUrl.detailId).toBe('adminUrlReady')
  })

  it('returns WARN (derivable) when atlassian SSE has a valid url but no adminUrl', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({
        name: 'atlassian',
        transportType: 'SSE',
        config: { url: 'https://atlassian', adminToken: 'real' },
      }),
    )
    const adminUrl = result.signals.find((s) => s.id === 'adminUrl')!
    expect(adminUrl.status).toBe('WARN')
    expect(adminUrl.detailId).toBe('adminUrlDerived')
  })

  it('returns FAIL when atlassian server lacks both adminUrl and a derivable URL', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({
        name: 'atlassian',
        transportType: 'STDIO',
        config: { command: 'node x.js', adminToken: 'real' },
      }),
    )
    const adminUrl = result.signals.find((s) => s.id === 'adminUrl')!
    expect(adminUrl.status).toBe('FAIL')
    expect(adminUrl.detailId).toBe('adminUrlMissing')
  })

  it('returns WARN (optional) when generic kind lacks adminUrl', () => {
    const result = summarizeDraftConfigReadiness(
      'STDIO',
      { command: 'node x.js' },
      true,
      'generic',
    )
    const adminUrl = result.signals.find((s) => s.id === 'adminUrl')!
    expect(adminUrl.status).toBe('WARN')
    expect(adminUrl.detailId).toBe('adminUrlOptional')
  })
})

describe('summarizeServerConfigReadiness — admin token & HMAC', () => {
  it('returns PASS adminToken when token is valid', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({
        config: { url: 'https://x', adminUrl: 'https://x', adminToken: 'real-token' },
      }),
    )
    const token = result.signals.find((s) => s.id === 'adminToken')!
    expect(token.status).toBe('PASS')
  })

  it('returns FAIL adminToken when token is a placeholder value', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({
        config: { url: 'https://x', adminUrl: 'https://x', adminToken: '<set-token>' },
      }),
    )
    const token = result.signals.find((s) => s.id === 'adminToken')!
    expect(token.status).toBe('FAIL')
    expect(token.detailId).toBe('adminTokenPlaceholder')
  })

  it('returns WARN adminToken (optional) when generic kind lacks adminUrl', () => {
    const result = summarizeDraftConfigReadiness(
      'STDIO',
      { command: 'node x.js' },
      true,
      'generic',
    )
    const token = result.signals.find((s) => s.id === 'adminToken')!
    expect(token.status).toBe('WARN')
    expect(token.detailId).toBe('adminTokenOptional')
  })

  it('returns FAIL adminToken when token is missing on a known kind', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({ name: 'atlassian', config: { url: 'https://x', adminUrl: 'https://x' } }),
    )
    const token = result.signals.find((s) => s.id === 'adminToken')!
    expect(token.status).toBe('FAIL')
    expect(token.detailId).toBe('adminTokenMissing')
  })

  it('returns WARN HMAC when not required', () => {
    const result = summarizeServerConfigReadiness(buildServerDetail({ config: { url: 'https://x' } }))
    const hmac = result.signals.find((s) => s.id === 'adminHmac')!
    expect(hmac.status).toBe('WARN')
    expect(hmac.detailId).toBe('adminHmacDisabled')
  })

  it('returns FAIL HMAC when required but secret is missing', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({ config: { adminHmacRequired: true } }),
    )
    const hmac = result.signals.find((s) => s.id === 'adminHmac')!
    expect(hmac.status).toBe('FAIL')
    expect(hmac.detailId).toBe('adminHmacMissing')
  })

  it('returns FAIL HMAC when secret is a placeholder', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({
        config: { adminHmacRequired: true, adminHmacSecret: 'change-me' },
      }),
    )
    const hmac = result.signals.find((s) => s.id === 'adminHmac')!
    expect(hmac.status).toBe('FAIL')
    expect(hmac.detailId).toBe('adminHmacPlaceholder')
  })

  it('returns PASS HMAC when secret is real', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({
        config: { adminHmacRequired: true, adminHmacSecret: 'real-secret-1234' },
      }),
    )
    const hmac = result.signals.find((s) => s.id === 'adminHmac')!
    expect(hmac.status).toBe('PASS')
  })
})

describe('summarizeServerConfigReadiness — timeouts & autoConnect', () => {
  it('returns WARN timeoutsDefault when both timeouts are absent', () => {
    const result = summarizeServerConfigReadiness(buildServerDetail())
    const timeouts = result.signals.find((s) => s.id === 'timeouts')!
    expect(timeouts.status).toBe('WARN')
    expect(timeouts.detailId).toBe('timeoutsDefault')
  })

  it('returns WARN timeoutsNeedReview when request timeout is too small', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({ config: { adminTimeoutMs: 50 } }),
    )
    const timeouts = result.signals.find((s) => s.id === 'timeouts')!
    expect(timeouts.status).toBe('WARN')
    expect(timeouts.detailId).toBe('timeoutsNeedReview')
  })

  it('returns WARN timeoutsNeedReview when connect exceeds request', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({ config: { adminTimeoutMs: 1000, adminConnectTimeoutMs: 5000 } }),
    )
    const timeouts = result.signals.find((s) => s.id === 'timeouts')!
    expect(timeouts.status).toBe('WARN')
  })

  it('returns PASS timeoutsReady for sane in-range values', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({ config: { adminTimeoutMs: 5000, adminConnectTimeoutMs: 1000 } }),
    )
    const timeouts = result.signals.find((s) => s.id === 'timeouts')!
    expect(timeouts.status).toBe('PASS')
    expect(timeouts.meta?.timeoutMs).toBe(5000)
  })

  it('returns WARN autoConnect when disabled', () => {
    const result = summarizeServerConfigReadiness(buildServerDetail({ autoConnect: false }))
    const auto = result.signals.find((s) => s.id === 'autoConnect')!
    expect(auto.status).toBe('WARN')
    expect(auto.detailId).toBe('autoConnectDisabled')
  })

  it('returns PASS autoConnect when enabled', () => {
    const result = summarizeServerConfigReadiness(buildServerDetail({ autoConnect: true }))
    const auto = result.signals.find((s) => s.id === 'autoConnect')!
    expect(auto.status).toBe('PASS')
  })

  it('aggregates summary status as FAIL when any signal fails', () => {
    const result = summarizeServerConfigReadiness(buildServerDetail({ transportType: 'STDIO', config: {} }))
    expect(result.status).toBe('FAIL')
    expect(result.failCount).toBeGreaterThan(0)
  })

  it('aggregates summary status as WARN when no fails but at least one warn', () => {
    const result = summarizeServerConfigReadiness(
      buildServerDetail({
        name: 'atlassian',
        config: {
          url: 'https://atlas',
          adminUrl: 'https://admin',
          adminToken: 'real-1234',
        },
      }),
    )
    // adminHmac defaults to WARN-disabled, timeouts defaults to WARN-default.
    expect(result.status).toBe('WARN')
    expect(result.warnCount).toBeGreaterThan(0)
  })

  it('parses adminTimeoutMs from a numeric string', () => {
    const result = summarizeDraftConfigReadiness(
      'SSE',
      { url: 'https://x', adminUrl: 'https://x', adminToken: 'real', adminTimeoutMs: '5000' },
      true,
      'generic',
    )
    const timeouts = result.signals.find((s) => s.id === 'timeouts')!
    expect(timeouts.meta?.timeoutMs).toBe(5000)
  })
})

// ──────────────────────────────────────────────────────────────────────────
// summarizePolicyDiagnostics — atlassian and swagger kinds
// ──────────────────────────────────────────────────────────────────────────

describe('summarizePolicyDiagnostics — atlassian', () => {
  it('returns PASS coverage when at least one allowed list is populated', () => {
    const result = summarizePolicyDiagnostics(
      'atlassian',
      buildAtlassianPolicy({
        allowedJiraProjectKeys: ['PROJ'],
        allowedConfluenceSpaceKeys: ['SPACE'],
        allowedBitbucketRepositories: ['repo'],
        dynamicEnabled: true,
      }),
    )
    const cov = result.signals.find((s) => s.id === 'resourceCoverage')!
    expect(cov.status).toBe('PASS')
    expect(cov.detailId).toBe('coverageScoped')
  })

  it('returns WARN partial coverage when one of the lists is empty', () => {
    const result = summarizePolicyDiagnostics(
      'atlassian',
      buildAtlassianPolicy({
        allowedJiraProjectKeys: ['PROJ'],
        allowedConfluenceSpaceKeys: [],
        allowedBitbucketRepositories: ['repo'],
        dynamicEnabled: true,
      }),
    )
    const cov = result.signals.find((s) => s.id === 'resourceCoverage')!
    expect(cov.status).toBe('WARN')
    expect(cov.detailId).toBe('coveragePartiallyScoped')
  })

  it('returns FAIL coverage when all atlassian coverage lists are empty', () => {
    const result = summarizePolicyDiagnostics('atlassian', buildAtlassianPolicy({ dynamicEnabled: true }))
    const cov = result.signals.find((s) => s.id === 'resourceCoverage')!
    expect(cov.status).toBe('FAIL')
    expect(cov.detailId).toBe('coverageOpenAll')
    expect(result.runbookSteps).toContain('tightenCoverage')
  })

  it('marks dynamicMode WARN with unknown when policySource is unknown', () => {
    const result = summarizePolicyDiagnostics(
      'atlassian',
      buildAtlassianPolicy({ policySource: 'unknown' }),
    )
    const mode = result.signals.find((s) => s.id === 'policyMode')!
    expect(mode.status).toBe('WARN')
    expect(mode.detailId).toBe('dynamicModeUnknown')
  })

  it('marks dynamicMode WARN with disabled when dynamicEnabled is false', () => {
    const result = summarizePolicyDiagnostics(
      'atlassian',
      buildAtlassianPolicy({ dynamicEnabled: false, policySource: 'config' }),
    )
    const mode = result.signals.find((s) => s.id === 'policyMode')!
    expect(mode.status).toBe('WARN')
    expect(mode.detailId).toBe('dynamicModeDisabled')
  })

  it('marks dynamicDrift WARN when dynamicEnabled but snapshot missing', () => {
    const result = summarizePolicyDiagnostics(
      'atlassian',
      buildAtlassianPolicy({ dynamicEnabled: true }),
    )
    const drift = result.signals.find((s) => s.id === 'dynamicDrift')!
    expect(drift.status).toBe('WARN')
    expect(drift.detailId).toBe('dynamicSnapshotMissing')
    expect(result.runbookSteps).toContain('reconcileDynamicPolicy')
  })

  it('marks dynamicDrift PASS when dynamic snapshot matches effective', () => {
    const policy = buildAtlassianPolicy({
      allowedJiraProjectKeys: ['PROJ'],
      dynamicEnabled: true,
      dynamicPolicy: {
        allowedJiraProjectKeys: ['PROJ'],
        allowedConfluenceSpaceKeys: [],
        allowedBitbucketRepositories: [],
        allowedSourceNames: [],
        allowPreviewReads: false,
        allowPreviewWrites: false,
        allowDirectUrlLoads: false,
        publishedOnly: true,
      },
    })
    const result = summarizePolicyDiagnostics('atlassian', policy)
    const drift = result.signals.find((s) => s.id === 'dynamicDrift')!
    expect(drift.status).toBe('PASS')
  })

  it('marks dynamicDrift WARN drifted when dynamic snapshot differs', () => {
    const policy = buildAtlassianPolicy({
      allowedJiraProjectKeys: ['PROJ'],
      dynamicEnabled: true,
      dynamicPolicy: {
        allowedJiraProjectKeys: ['DIFF'],
        allowedConfluenceSpaceKeys: [],
        allowedBitbucketRepositories: [],
        allowedSourceNames: [],
        allowPreviewReads: false,
        allowPreviewWrites: false,
        allowDirectUrlLoads: false,
        publishedOnly: true,
      },
    })
    const result = summarizePolicyDiagnostics('atlassian', policy)
    const drift = result.signals.find((s) => s.id === 'dynamicDrift')!
    expect(drift.status).toBe('WARN')
    expect(drift.detailId).toBe('dynamicPolicyDrifted')
    expect(drift.meta?.count).toBeGreaterThan(0)
  })
})

describe('summarizePolicyDiagnostics — swagger', () => {
  it('emits the swagger-only signals (preview reads/writes, direct URL, published scope)', () => {
    const result = summarizePolicyDiagnostics(
      'swagger',
      buildSwaggerPolicy({
        allowedSourceNames: ['source-a'],
        allowPreviewReads: true,
        allowPreviewWrites: true,
        allowDirectUrlLoads: true,
        publishedOnly: false,
        dynamicEnabled: true,
      }),
    )
    const ids = result.signals.map((s) => s.id)
    expect(ids).toContain('previewReads')
    expect(ids).toContain('previewWrites')
    expect(ids).toContain('directUrlLoads')
    expect(ids).toContain('publishedScope')
    expect(result.signals.find((s) => s.id === 'previewReads')!.status).toBe('WARN')
    expect(result.signals.find((s) => s.id === 'publishedScope')!.detailId).toBe('publishedScopeOpen')
    expect(result.runbookSteps).toContain('lockPreviewSurface')
  })

  it('returns PASS for swagger preview signals when all surfaces are blocked', () => {
    const result = summarizePolicyDiagnostics(
      'swagger',
      buildSwaggerPolicy({
        allowedSourceNames: ['s1'],
        allowPreviewReads: false,
        allowPreviewWrites: false,
        allowDirectUrlLoads: false,
        publishedOnly: true,
        dynamicEnabled: true,
      }),
    )
    expect(result.signals.find((s) => s.id === 'previewReads')!.status).toBe('PASS')
    expect(result.signals.find((s) => s.id === 'previewWrites')!.status).toBe('PASS')
    expect(result.signals.find((s) => s.id === 'directUrlLoads')!.status).toBe('PASS')
    expect(result.signals.find((s) => s.id === 'publishedScope')!.detailId).toBe('publishedOnlyEnforced')
  })

  it('reaches steady-state runbook step when nothing needs attention', () => {
    const result = summarizePolicyDiagnostics(
      'swagger',
      buildSwaggerPolicy({
        allowedSourceNames: ['source-a'],
        allowPreviewReads: false,
        allowPreviewWrites: false,
        allowDirectUrlLoads: false,
        publishedOnly: true,
        dynamicEnabled: true,
        policySource: 'config',
        dynamicPolicy: {
          allowedJiraProjectKeys: [],
          allowedConfluenceSpaceKeys: [],
          allowedBitbucketRepositories: [],
          allowedSourceNames: ['source-a'],
          allowPreviewReads: false,
          allowPreviewWrites: false,
          allowDirectUrlLoads: false,
          publishedOnly: true,
        },
      }),
    )
    expect(result.runbookSteps).toContain('steadyState')
  })
})

// ──────────────────────────────────────────────────────────────────────────
// classifyMcpSecurityLoadIssue
// ──────────────────────────────────────────────────────────────────────────

describe('classifyMcpSecurityLoadIssue', () => {
  it('returns null for null or empty input', () => {
    expect(classifyMcpSecurityLoadIssue(null)).toBeNull()
    expect(classifyMcpSecurityLoadIssue('')).toBeNull()
    expect(classifyMcpSecurityLoadIssue('   ')).toBeNull()
  })

  it('classifies HTTP 404 as notAdvertised', () => {
    expect(classifyMcpSecurityLoadIssue('Got HTTP 404')).toBe('notAdvertised')
  })

  it('classifies HTTP 401/403 as accessDenied', () => {
    expect(classifyMcpSecurityLoadIssue('HTTP 401 Unauthorized')).toBe('accessDenied')
    expect(classifyMcpSecurityLoadIssue('HTTP 403 Forbidden')).toBe('accessDenied')
  })

  it('classifies network failures as transportFailure', () => {
    expect(classifyMcpSecurityLoadIssue('socket hang up')).toBe('transportFailure')
    expect(classifyMcpSecurityLoadIssue('Failed to fetch')).toBe('transportFailure')
    expect(classifyMcpSecurityLoadIssue('NetworkError when attempting')).toBe('transportFailure')
    expect(classifyMcpSecurityLoadIssue('empty reply from server')).toBe('transportFailure')
  })

  it('falls back to httpError for unrecognized errors', () => {
    expect(classifyMcpSecurityLoadIssue('Some other error')).toBe('httpError')
  })
})

// ──────────────────────────────────────────────────────────────────────────
// summarizeMcpSecurityOps
// ──────────────────────────────────────────────────────────────────────────

describe('summarizeMcpSecurityOps', () => {
  it('returns hasPolicy=false stub when state is null', () => {
    const result = summarizeMcpSecurityOps(null, null, ['srv-1'], null)
    expect(result.hasPolicy).toBe(false)
    expect(result.registeredCount).toBe(1)
    expect(result.signals).toHaveLength(1)
    expect(result.signals[0].id).toBe('policyContract')
  })

  it('flags blocked registered servers as FAIL', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: ['allowed'] }),
    })
    const result = summarizeMcpSecurityOps(state, null, ['allowed', 'blocked'], null)
    expect(result.blockedRegisteredCount).toBe(1)
    expect(result.blockedRegisteredNames).toEqual(['blocked'])
    expect(result.signals.find((s) => s.id === 'registryAlignment')!.status).toBe('FAIL')
  })

  it('flags stale allowed servers as WARN when registry has no extras', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: ['ghost'] }),
    })
    const result = summarizeMcpSecurityOps(state, null, [], null)
    expect(result.staleAllowedCount).toBe(1)
    // registryEmpty wins because registeredServerNames.length === 0
    expect(result.signals.find((s) => s.id === 'registryAlignment')!.detailId).toBe('registryEmpty')
  })

  it('reports allowlistEmpty WARN when allowedServerNames is empty', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: [] }),
    })
    const result = summarizeMcpSecurityOps(state, null, ['srv'], null)
    const cov = result.signals.find((s) => s.id === 'allowlistCoverage')!
    expect(cov.status).toBe('WARN')
    expect(cov.detailId).toBe('allowlistEmpty')
  })

  it('reports outputClampHigh WARN when maxToolOutputLength exceeds 200_000', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: ['srv'], maxToolOutputLength: 500_000 }),
    })
    const result = summarizeMcpSecurityOps(state, null, ['srv'], null)
    expect(result.signals.find((s) => s.id === 'outputClamp')!.detailId).toBe('outputClampHigh')
  })

  it('reports outputClampTight WARN when maxToolOutputLength below 4096', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: ['srv'], maxToolOutputLength: 1000 }),
    })
    const result = summarizeMcpSecurityOps(state, null, ['srv'], null)
    expect(result.signals.find((s) => s.id === 'outputClamp')!.detailId).toBe('outputClampTight')
  })

  it('reports policyDriftDetected FAIL when stored differs from effective', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: ['srv-a'] }),
      stored: buildRuleSet({ allowedServerNames: ['srv-b'] }),
    })
    const result = summarizeMcpSecurityOps(state, null, ['srv-a'], null)
    expect(result.storedExists).toBe(true)
    expect(result.signals.find((s) => s.id === 'policyDrift')!.detailId).toBe('policyDriftDetected')
    expect(result.diffFields).toContain('allowedServerNames')
  })

  it('reports storedOverrideApplied WARN when stored equals effective but exists', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: ['srv'] }),
      stored: buildRuleSet({ allowedServerNames: ['srv'] }),
    })
    const result = summarizeMcpSecurityOps(state, null, ['srv'], null)
    expect(result.signals.find((s) => s.id === 'policyDrift')!.detailId).toBe('storedOverrideApplied')
    expect(result.signals.find((s) => s.id === 'storedPolicy')!.detailId).toBe('storedPolicyPresent')
  })

  it('reports policyInSync PASS when no stored override and config matches effective', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: ['srv'] }),
      stored: null,
      configDefault: buildRuleSet({ allowedServerNames: ['srv'] }),
    })
    const result = summarizeMcpSecurityOps(state, null, ['srv'], null)
    expect(result.signals.find((s) => s.id === 'policyDrift')!.detailId).toBe('policyInSync')
    expect(result.signals.find((s) => s.id === 'storedPolicy')!.detailId).toBe('configDefaultActive')
  })

  it('flags configDrift FAIL when no stored but configDefault differs from effective', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: ['srv-a'] }),
      stored: null,
      configDefault: buildRuleSet({ allowedServerNames: ['srv-b'] }),
    })
    const result = summarizeMcpSecurityOps(state, null, ['srv-a'], null)
    expect(result.signals.find((s) => s.id === 'policyDrift')!.detailId).toBe('policyDriftDetected')
  })

  it('flags registryUnavailable WARN when registry error is present', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: ['srv'] }),
    })
    const result = summarizeMcpSecurityOps(state, null, ['srv'], 'fetch failed')
    expect(result.signals.find((s) => s.id === 'registryAlignment')!.detailId).toBe('registryUnavailable')
  })

  it('reports registryCovered PASS when registry matches allowlist exactly', () => {
    const state = buildSecurityState({
      effective: buildRuleSet({ allowedServerNames: ['srv-a'] }),
    })
    const result = summarizeMcpSecurityOps(state, null, ['srv-a'], null)
    const sig = result.signals.find((s) => s.id === 'registryAlignment')!
    expect(sig.detailId).toBe('registryCovered')
    expect(sig.meta?.count).toBe(1)
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Existing smoke tests preserved
// ──────────────────────────────────────────────────────────────────────────

describe('mcpHelpers — preserved smoke tests', () => {
  it('summarizeRegistryOverview returns overview from empty server list', () => {
    expect(summarizeRegistryOverview([]).totalServers).toBe(0)
  })

  it('summarizeMcpSecurityOps returns summary from empty state', () => {
    const result = summarizeMcpSecurityOps(buildSecurityState(), null, [], null)
    expect(result.status).toBeDefined()
  })

  it('summarizePolicyDiagnostics returns summary for atlassian kind with one allowed key', () => {
    const result = summarizePolicyDiagnostics(
      'atlassian',
      buildAtlassianPolicy({ allowedJiraProjectKeys: ['PROJ'] }),
    )
    expect(result.status).toBeDefined()
    expect(result.signals.length).toBeGreaterThan(0)
  })

  it('exposes the correct signal id type via re-exports', () => {
    const sample: ConfigReadinessSignal = {
      id: 'transportTarget',
      status: 'PASS',
      detailId: 'transportUrlReady',
    }
    expect(sample.id).toBe('transportTarget')
  })
})

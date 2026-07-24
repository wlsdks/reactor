import { describe, expect, it } from 'vitest'
import { buildIssueCenterSnapshot } from '../issueCenter'
import type {
  IssueCenterSnapshotInput,
  McpIssueSnapshot,
} from '../types'

// ──────────────────────────────────────────────────────────────────────────
// Empty / minimal fixture builders. Each test starts from `buildEmptyInput`
// and mutates only the slice under test — keeps assertions focused on the
// branch we are exercising.
// ──────────────────────────────────────────────────────────────────────────

function buildEmptyInput(): IssueCenterSnapshotInput {
  return {
    generatedAt: 1_700_000_000_000,
    controlPlaneRecovery: {
      status: 'PASS',
      attentionCount: 0,
      failCount: 0,
      transportFailureCount: 0,
      missingContractCount: 0,
      declaredBrokenCount: 0,
      manifestDriftCount: 0,
      items: [],
    },
    registryOverview: {
      totalServers: 0,
      connectedCount: 0,
      disconnectedCount: 0,
      knownServers: [],
    },
    mcpServers: [],
    scheduler: {
      status: 'PASS',
      loadIssue: null,
      totalJobs: 0,
      enabledJobs: 0,
      attentionJobs: 0,
      failedJobs: 0,
      staleJobs: 0,
      retryGapJobs: 0,
      signals: [],
      attentionItems: [],
    },
    approvals: {
      status: 'PASS',
      loadIssue: null,
      totalApprovals: 0,
      pendingCount: 0,
      timedOutCount: 0,
      stalePendingCount: 0,
      attentionCount: 0,
      coveredCount: 0,
      oldestPendingMinutes: null,
      signals: [],
      attentionItems: [],
    },
    toolPolicy: {
      status: 'PASS',
      loadIssue: null,
      hasPolicy: true,
      storedExists: true,
      activeWriteTools: 0,
      denyChannels: 0,
      allowOverrides: 0,
      diffFields: [],
      signals: [],
      diffs: [],
    },
    mcpSecurity: {
      status: 'PASS',
      loadIssue: null,
      hasPolicy: true,
      effectiveAllowedCount: 0,
      registeredCount: 0,
      blockedRegisteredCount: 0,
      staleAllowedCount: 0,
      storedExists: false,
      diffFields: [],
      blockedRegisteredNames: [],
      staleAllowedNames: [],
      signals: [],
      diffs: [],
    },
    outputGuard: {
      status: 'PASS',
      totalRules: 0,
      enabledRules: 0,
      disabledRules: 0,
      rejectRules: 0,
      maskRules: 0,
      invalidRules: 0,
      auditRows: 0,
      signals: [],
    },
    audit: {
      status: 'PASS',
      totalLogs: 0,
      uniqueActors: 0,
      uniqueResources: 0,
      detailedLogs: 0,
      rollbackReadyCount: 0,
      highRiskCount: 0,
      signals: [],
      categories: [],
      resourceBundles: [],
    },
  }
}

function buildServerDetail(overrides: Partial<McpIssueSnapshot['server']> = {}): McpIssueSnapshot['server'] {
  return {
    id: 'srv-1',
    name: 'atlassian',
    description: null,
    transportType: 'SSE',
    config: {},
    version: null,
    autoConnect: true,
    status: 'CONNECTED',
    tools: [],
    createdAt: 1,
    updatedAt: 2,
    ...overrides,
  }
}

function buildMcpSnapshot(overrides: Partial<McpIssueSnapshot> = {}): McpIssueSnapshot {
  return {
    kind: 'atlassian',
    server: buildServerDetail(),
    detailError: null,
    configReadiness: null,
    preflight: null,
    preflightError: null,
    policyDiagnostics: null,
    policyError: null,
    ...overrides,
  }
}

// ──────────────────────────────────────────────────────────────────────────
// Snapshot defaults
// ──────────────────────────────────────────────────────────────────────────

describe('buildIssueCenterSnapshot — empty defaults', () => {
  it('returns a healthy snapshot when no inputs report problems', () => {
    const snapshot = buildIssueCenterSnapshot(buildEmptyInput())

    expect(snapshot.total).toBe(0)
    expect(snapshot.criticalCount).toBe(0)
    expect(snapshot.warningCount).toBe(0)
    expect(snapshot.items).toEqual([])
    expect(snapshot.sources).toEqual([])
    expect(snapshot.generatedAt).toBe(1_700_000_000_000)
  })

  it('falls back to Date.now when generatedAt is omitted', () => {
    const input = buildEmptyInput()
    delete input.generatedAt
    const before = Date.now()
    const snapshot = buildIssueCenterSnapshot(input)
    const after = Date.now()

    expect(snapshot.generatedAt).toBeGreaterThanOrEqual(before)
    expect(snapshot.generatedAt).toBeLessThanOrEqual(after)
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Control-plane recovery → integrations issues
// ──────────────────────────────────────────────────────────────────────────

describe('buildIssueCenterSnapshot — control plane', () => {
  it('classifies FAIL status as critical', () => {
    const input = buildEmptyInput()
    input.controlPlaneRecovery.items.push({
      probe: {
        id: 'toolPolicy',
        path: '/api/tool-policy',
        routePath: '/tool-policy',
        status: 'FAIL',
        reason: 'probeFailed',
        manifestDeclared: true,
        httpStatus: 500,
        durationMs: 10,
        detail: 'boom',
      },
      status: 'FAIL',
      kind: 'transportFailure',
      route: { path: '/safety-rules?tab=tool-policy', labelKey: 'nav.safetyRules' },
      stepIds: ['probeDirect'],
    })

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'control-plane:toolPolicy')!
    expect(issue.severity).toBe('critical')
    expect(issue.source).toBe('integrations')
    expect(issue.routePath).toBe('/safety-rules?tab=tool-policy')
    expect(issue.evidence).toContain('/api/tool-policy')
    expect(issue.evidence).toContain('HTTP 500 · boom')
  })

  it('classifies WARN status as warning and uses bare detail when httpStatus is null', () => {
    const input = buildEmptyInput()
    input.controlPlaneRecovery.items.push({
      probe: {
        id: 'mcpRegistry',
        path: '/api/mcp/servers',
        routePath: '/mcp-servers',
        status: 'WARN',
        reason: 'reachableUndeclared',
        manifestDeclared: false,
        httpStatus: null,
        durationMs: 5,
        detail: 'undeclared',
      },
      status: 'WARN',
      kind: 'manifestDrift',
      route: { path: '/mcp-servers', labelKey: 'nav.mcpServers' },
      stepIds: ['checkManifest'],
    })

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'control-plane:mcpRegistry')!
    expect(issue.severity).toBe('warning')
    // No HTTP prefix when httpStatus is null
    expect(issue.evidence).toContain('undeclared')
    expect(issue.evidence.some((line) => line.startsWith('HTTP'))).toBe(false)
  })

  it('marks /scheduler as degraded so scheduler signals are suppressed', () => {
    const input = buildEmptyInput()
    input.controlPlaneRecovery.items.push({
      probe: {
        id: 'schedulerJobs',
        path: '/api/scheduler/jobs',
        routePath: '/scheduler',
        status: 'FAIL',
        reason: 'probeFailed',
        manifestDeclared: true,
        httpStatus: 500,
        durationMs: 1,
        detail: 'down',
      },
      status: 'FAIL',
      kind: 'transportFailure',
      route: { path: '/scheduler', labelKey: 'nav.scheduler' },
      stepIds: ['probeDirect'],
    })
    // A scheduler signal that would normally surface — should be suppressed.
    input.scheduler.signals.push({
      id: 'schedulerContract',
      status: 'FAIL',
      detailId: 'contractTransport',
    })

    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.items.some((i) => i.id === 'scheduler-signal:schedulerContract')).toBe(false)
    expect(snapshot.items.some((i) => i.id === 'control-plane:schedulerJobs')).toBe(true)
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Registry / MCP server issues
// ──────────────────────────────────────────────────────────────────────────

describe('buildIssueCenterSnapshot — MCP registry & server snapshots', () => {
  it('emits a missing-server issue when a known server is absent (atlassian)', () => {
    const input = buildEmptyInput()
    input.registryOverview.knownServers.push({ id: 'atlassian', server: null })

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-missing:atlassian')!
    expect(issue.severity).toBe('critical')
    expect(issue.title.key).toBe('mcpServers.knownServerAtlassian')
  })

  it('uses the swagger label key for the swagger missing-server issue', () => {
    const input = buildEmptyInput()
    input.registryOverview.knownServers.push({ id: 'swagger', server: null })

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-missing:swagger')!
    expect(issue.title.key).toBe('mcpServers.knownServerSwagger')
  })

  it('does not emit a missing-server issue when the known server is present', () => {
    const input = buildEmptyInput()
    input.registryOverview.knownServers.push({
      id: 'atlassian',
      server: {
        id: 's1',
        name: 'atlassian',
        description: null,
        transportType: 'SSE',
        autoConnect: true,
        status: 'CONNECTED',
        toolCount: 1,
        createdAt: 1,
        updatedAt: 2,
      },
    })

    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.items.some((i) => i.id.startsWith('mcp-missing:'))).toBe(false)
  })

  it('reports a disconnected server as critical', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ status: 'DISCONNECTED', name: 'jira' }),
      }),
    )

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-disconnected:jira')!
    expect(issue.severity).toBe('critical')
    expect(issue.title.values).toEqual({ name: 'Jira' })
    expect(issue.evidence).toContain('DISCONNECTED')
  })

  it('emits a detail-error issue when detailError is set', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'detail-broken' }),
        detailError: 'fetch failed',
      }),
    )

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-detail:detail-broken')!
    expect(issue.severity).toBe('critical')
    expect(issue.evidence).toEqual(['fetch failed'])
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Config readiness (mcp-config)
// ──────────────────────────────────────────────────────────────────────────

describe('buildIssueCenterSnapshot — config readiness', () => {
  it('returns no issue when configReadiness is PASS', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        configReadiness: {
          status: 'PASS',
          passCount: 1,
          warnCount: 0,
          failCount: 0,
          signals: [],
        },
      }),
    )

    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.items.some((i) => i.id.startsWith('mcp-config:'))).toBe(false)
  })

  it('classifies FAIL configReadiness as critical and surfaces lead signal details', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'cfg-fail' }),
        configReadiness: {
          status: 'FAIL',
          passCount: 0,
          warnCount: 0,
          failCount: 1,
          signals: [
            {
              id: 'transportTarget',
              status: 'FAIL',
              detailId: 'transportMissingUrl',
              meta: { timeoutMs: 5000, connectTimeoutMs: 1000 },
            },
          ],
        },
      }),
    )

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-config:cfg-fail')!
    expect(issue.severity).toBe('critical')
    expect(issue.summary.key).toBe('mcpServers.configReadinessDetails.transportMissingUrl')
    expect(issue.summary.values).toEqual({ timeoutMs: 5000, connectTimeoutMs: 1000 })
    expect(issue.evidence).toEqual(['transportTarget'])
  })

  it('classifies WARN configReadiness as warning with default values when meta is absent', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'cfg-warn' }),
        configReadiness: {
          status: 'WARN',
          passCount: 0,
          warnCount: 1,
          failCount: 0,
          signals: [
            {
              id: 'autoConnect',
              status: 'WARN',
              detailId: 'autoConnectDisabled',
            },
          ],
        },
      }),
    )

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-config:cfg-warn')!
    expect(issue.severity).toBe('warning')
    // Falls back to '-' when meta is missing
    expect(issue.summary.values).toEqual({ timeoutMs: '-', connectTimeoutMs: '-' })
  })

  it('uses the operator-facing external-tool name in an issue title', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'atlassian' }),
        configReadiness: {
          status: 'FAIL',
          passCount: 0,
          warnCount: 0,
          failCount: 1,
          signals: [{ id: 'adminUrl', status: 'FAIL', detailId: 'adminUrlMissing' }],
        },
      }),
    )

    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.items.find((item) => item.id === 'mcp-config:atlassian')?.title.values).toEqual({
      name: 'Atlassian',
    })
  })

  it('falls back to the generic description when no non-PASS signal exists', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'cfg-nosignal' }),
        configReadiness: {
          // status non-PASS triggers the issue, but the signals array
          // contains only PASS signals — defends the lead-signal fallback.
          status: 'WARN',
          passCount: 1,
          warnCount: 0,
          failCount: 0,
          signals: [
            { id: 'autoConnect', status: 'PASS', detailId: 'autoConnectEnabled' },
          ],
        },
      }),
    )

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-config:cfg-nosignal')!
    expect(issue.summary.key).toBe('mcpServers.configReadinessDescription')
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Preflight
// ──────────────────────────────────────────────────────────────────────────

describe('buildIssueCenterSnapshot — preflight', () => {
  it('emits a critical preflight-error issue when preflightError is set', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'pf-err' }),
        preflightError: 'timed out',
      }),
    )

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-preflight-error:pf-err')!
    expect(issue.severity).toBe('critical')
    expect(issue.evidence).toEqual(['timed out'])
  })

  it('returns no issue when preflight is null', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(buildMcpSnapshot())
    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.items.some((i) => i.id.startsWith('mcp-preflight:'))).toBe(false)
  })

  it('returns no issue when preflight is readyForProduction', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        preflight: {
          ok: true,
          readyForProduction: true,
          policySource: 'config',
          checkedAt: '2024-01-01T00:00:00Z',
          summary: { passCount: 5, warnCount: 0, failCount: 0 },
          checks: [],
        },
      }),
    )
    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.items.some((i) => i.id.startsWith('mcp-preflight:'))).toBe(false)
  })

  it('classifies preflight as warning when ok=true but not readyForProduction', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'pf-warn' }),
        preflight: {
          ok: true,
          readyForProduction: false,
          policySource: 'config',
          checkedAt: '2024-01-01T00:00:00Z',
          summary: { passCount: 4, warnCount: 1, failCount: 0 },
          checks: [],
        },
      }),
    )
    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-preflight:pf-warn')!
    expect(issue.severity).toBe('warning')
    expect(issue.summary.key).toBe('mcpServers.preflightNeedsAttention')
    expect(issue.evidence).toEqual(['PASS 4', 'WARN 1', 'FAIL 0'])
    expect(issue.detectedAt).toBe(Date.parse('2024-01-01T00:00:00Z'))
  })

  it('classifies preflight as critical when ok=false', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'pf-crit' }),
        preflight: {
          ok: false,
          readyForProduction: false,
          policySource: 'config',
          checkedAt: 'not-a-real-date',
          summary: { passCount: 1, warnCount: 1, failCount: 3 },
          checks: [],
        },
      }),
    )
    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-preflight:pf-crit')!
    expect(issue.severity).toBe('critical')
    expect(issue.summary.key).toBe('mcpServers.preflightFailed')
    // toEpoch returns null for unparseable strings
    expect(issue.detectedAt).toBeNull()
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Policy diagnostics
// ──────────────────────────────────────────────────────────────────────────

describe('buildIssueCenterSnapshot — policy diagnostics', () => {
  it('emits a policy-error issue when policyError is set', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'pol-err' }),
        policyError: 'denied',
      }),
    )
    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-policy-error:pol-err')!
    expect(issue.severity).toBe('critical')
    expect(issue.evidence).toEqual(['denied'])
  })

  it('returns no issue when policyDiagnostics is PASS', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        policyDiagnostics: {
          status: 'PASS',
          effectiveCoverageCount: 1,
          dynamicCoverageCount: 1,
          attentionCount: 0,
          riskySurfaceCount: 0,
          diffFields: [],
          signals: [],
          runbookSteps: [],
        },
      }),
    )
    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.items.some((i) => i.id.startsWith('mcp-policy:'))).toBe(false)
  })

  it('classifies WARN policy diagnostics with lead signal values', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'pol-warn' }),
        policyDiagnostics: {
          status: 'WARN',
          effectiveCoverageCount: 0,
          dynamicCoverageCount: null,
          attentionCount: 1,
          riskySurfaceCount: 0,
          diffFields: [{ id: 'allowedJiraProjectKeys', effective: [], dynamic: [] }],
          signals: [
            {
              id: 'resourceCoverage',
              status: 'WARN',
              detailId: 'coveragePartiallyScoped',
              meta: { count: 0, openCount: 1, totalCount: 3 },
            },
          ],
          runbookSteps: ['tightenCoverage'],
        },
      }),
    )
    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-policy:pol-warn')!
    expect(issue.severity).toBe('warning')
    expect(issue.summary.key).toBe('mcpServers.policySignalDetails.coveragePartiallyScoped')
    expect(issue.summary.values).toEqual({ count: 0, openCount: 1, totalCount: 3 })
    expect(issue.evidence).toEqual(['attention:1', 'drift:1'])
  })

  it('falls back to the access-policy description when no non-PASS signal exists', () => {
    const input = buildEmptyInput()
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'pol-nosignal' }),
        policyDiagnostics: {
          status: 'WARN',
          effectiveCoverageCount: 1,
          dynamicCoverageCount: 1,
          attentionCount: 0,
          riskySurfaceCount: 0,
          diffFields: [],
          signals: [
            { id: 'policyMode', status: 'PASS', detailId: 'dynamicModeEnabled' },
          ],
          runbookSteps: [],
        },
      }),
    )
    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'mcp-policy:pol-nosignal')!
    expect(issue.summary.key).toBe('mcpServers.accessPolicyDescription')
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Scheduler signals & attention items
// ──────────────────────────────────────────────────────────────────────────

describe('buildIssueCenterSnapshot — scheduler', () => {
  it('emits scheduler-signal issues for non-PASS signals when route is healthy', () => {
    const input = buildEmptyInput()
    input.scheduler.signals.push(
      { id: 'schedulerContract', status: 'PASS', detailId: 'contractHealthy' },
      { id: 'failureBacklog', status: 'WARN', detailId: 'failureBacklogPresent', meta: { count: 2 } },
      { id: 'enabledCoverage', status: 'FAIL', detailId: 'enabledCoverageMissing', meta: { count: 0, total: 3 } },
    )

    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.items.some((i) => i.id === 'scheduler-signal:schedulerContract')).toBe(false)
    const failureBacklog = snapshot.items.find((i) => i.id === 'scheduler-signal:failureBacklog')!
    expect(failureBacklog.severity).toBe('warning')
    expect(failureBacklog.summary.values).toEqual({ count: 2, total: 0 })
    const enabled = snapshot.items.find((i) => i.id === 'scheduler-signal:enabledCoverage')!
    expect(enabled.severity).toBe('critical')
  })

  it('emits scheduler-attention issues independent of degraded route', () => {
    const input = buildEmptyInput()
    input.scheduler.attentionItems.push({
      id: 'job-9:never-run',
      kind: 'neverRun',
      status: 'WARN',
      detailId: 'neverExecuted',
      job: {
        id: 'job-9',
        name: 'sync-data',
        description: null,
        cronExpression: '*/5 * * * *',
        timezone: 'UTC',
        jobType: 'MCP_TOOL',
        mcpServerName: 'atlassian',
        toolName: 'sync',
        toolArguments: {},
        agentPrompt: null,
        personaId: null,
        agentSystemPrompt: null,
        agentModel: null,
        agentMaxToolCalls: null,
        slackChannelId: null,
        teamsWebhookUrl: null,
        retryOnFailure: false,
        maxRetryCount: 0,
        executionTimeoutMs: null,
        enabled: true,
        lastRunAt: null,
        lastStatus: null,
        lastResult: null,
        lastResultPreview: null,
        lastFailureReason: null,
        createdAt: 1,
        updatedAt: 2,
      },
    })

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'scheduler-attention:job-9:never-run')!
    expect(issue.severity).toBe('warning')
    // Defaults to UNKNOWN when lastStatus is null
    expect(issue.evidence).toContain('UNKNOWN')
    expect(issue.evidence).toContain('*/5 * * * *')
    expect(issue.detectedAt).toBeNull()
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Approval signals & attention items
// ──────────────────────────────────────────────────────────────────────────

describe('buildIssueCenterSnapshot — approvals', () => {
  it('emits approval-signal issues for non-PASS signals when route is healthy', () => {
    const input = buildEmptyInput()
    input.approvals.signals.push(
      { id: 'pendingQueue', status: 'WARN', detailId: 'pendingQueueActive', meta: { count: 3, total: 5 } },
      { id: 'timeoutDebt', status: 'FAIL', detailId: 'timeoutDebtPresent', meta: { count: 2, total: 2 } },
    )

    const snapshot = buildIssueCenterSnapshot(input)
    const pending = snapshot.items.find((i) => i.id === 'approvals-signal:pendingQueue')!
    expect(pending.severity).toBe('warning')
    expect(pending.summary.values).toEqual({ count: 3, total: 5 })
    const timeout = snapshot.items.find((i) => i.id === 'approvals-signal:timeoutDebt')!
    expect(timeout.severity).toBe('critical')
  })

  it('suppresses approval-signal issues when /approvals route is degraded', () => {
    const input = buildEmptyInput()
    input.controlPlaneRecovery.items.push({
      probe: {
        id: 'approvals',
        path: '/api/approvals',
        routePath: '/approvals',
        status: 'FAIL',
        reason: 'probeFailed',
        manifestDeclared: true,
        httpStatus: 503,
        durationMs: 1,
        detail: 'down',
      },
      status: 'FAIL',
      kind: 'transportFailure',
      route: { path: '/approvals', labelKey: 'nav.approvals' },
      stepIds: ['probeDirect'],
    })
    input.approvals.signals.push({
      id: 'pendingQueue',
      status: 'WARN',
      detailId: 'pendingQueueActive',
      meta: { count: 1, total: 1 },
    })

    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.items.some((i) => i.id === 'approvals-signal:pendingQueue')).toBe(false)
  })

  it('emits approval-attention issues with parsed requestedAt', () => {
    const input = buildEmptyInput()
    const requestedAt = '2024-06-01T10:00:00Z'
    input.approvals.attentionItems.push({
      id: 'approval-1',
      kind: 'pending',
      status: 'WARN',
      ageMinutes: 42,
      detailId: 'pendingReview',
      approval: {
        id: 'approval-1',
        runId: 'run-1',
        toolName: 'send_email',
        arguments: {},
        requestedAt,
        status: 'PENDING',
      },
    })

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'approvals-attention:approval-1')!
    expect(issue.severity).toBe('warning')
    expect(issue.title.values).toEqual({ tool: '이메일 보내기' })
    expect(issue.summary.values).toEqual({ ageMinutes: 42 })
    expect(issue.detectedAt).toBe(Date.parse(requestedAt))
    expect(issue.evidence).toEqual(['run-1', 'PENDING'])
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Tool policy / MCP security / output guard / audit signal mappers
// ──────────────────────────────────────────────────────────────────────────

describe('buildIssueCenterSnapshot — tool policy / mcp security / output guard / audit', () => {
  it('emits tool-policy issues on the safety rules route and respects degraded safety rules', () => {
    const healthy = buildEmptyInput()
    healthy.toolPolicy.signals.push(
      { id: 'exceptionReview', status: 'WARN', detailId: 'exceptionReviewNeeded', meta: { count: 4 } },
      { id: 'storedDrift', status: 'FAIL', detailId: 'storedDriftDetected', meta: { count: 1 } },
    )
    const healthySnapshot = buildIssueCenterSnapshot(healthy)
    const warningIssue = healthySnapshot.items.find((i) => i.id === 'tool-policy:exceptionReview')!
    expect(warningIssue.routePath).toBe('/safety-rules?tab=tool-policy')
    expect(warningIssue.routeLabelKey).toBe('nav.safetyRules')
    expect(healthySnapshot.items.find((i) => i.id === 'tool-policy:storedDrift')!.severity).toBe('critical')

    const degraded = buildEmptyInput()
    degraded.controlPlaneRecovery.items.push({
      probe: {
        id: 'toolPolicy',
        path: '/api/tool-policy',
        routePath: '/tool-policy',
        status: 'FAIL',
        reason: 'probeFailed',
        manifestDeclared: true,
        httpStatus: 500,
        durationMs: 1,
        detail: 'down',
      },
      status: 'FAIL',
      kind: 'transportFailure',
      route: { path: '/safety-rules?tab=tool-policy', labelKey: 'nav.safetyRules' },
      stepIds: ['probeDirect'],
    })
    degraded.toolPolicy.signals.push({
      id: 'exceptionReview',
      status: 'WARN',
      detailId: 'exceptionReviewNeeded',
      meta: { count: 1 },
    })
    const degradedSnapshot = buildIssueCenterSnapshot(degraded)
    expect(degradedSnapshot.items.some((i) => i.id === 'tool-policy:exceptionReview')).toBe(false)
  })

  it('emits mcp-security issues on the mcp servers route and respects degraded mcp servers', () => {
    const healthy = buildEmptyInput()
    healthy.mcpSecurity.signals.push({
      id: 'allowlistCoverage',
      status: 'WARN',
      detailId: 'allowlistEmpty',
    })
    const healthyIssue = buildIssueCenterSnapshot(healthy).items.find((i) => i.id === 'mcp-security:allowlistCoverage')!
    expect(healthyIssue.routePath).toBe('/mcp-servers')
    expect(healthyIssue.routeLabelKey).toBe('nav.mcpServers')

    const degraded = buildEmptyInput()
    degraded.controlPlaneRecovery.items.push({
      probe: {
        id: 'mcpSecurity',
        path: '/api/mcp/security',
        routePath: '/mcp-security',
        status: 'FAIL',
        reason: 'probeFailed',
        manifestDeclared: true,
        httpStatus: 500,
        durationMs: 1,
        detail: 'down',
      },
      status: 'FAIL',
      kind: 'transportFailure',
      route: { path: '/mcp-servers', labelKey: 'nav.mcpServers' },
      stepIds: ['probeDirect'],
    })
    degraded.mcpSecurity.signals.push({
      id: 'allowlistCoverage',
      status: 'WARN',
      detailId: 'allowlistEmpty',
    })
    expect(
      buildIssueCenterSnapshot(degraded).items.some((i) => i.id === 'mcp-security:allowlistCoverage'),
    ).toBe(false)
  })

  it('emits output-guard issues regardless of routes (no degraded gate)', () => {
    const input = buildEmptyInput()
    input.outputGuard.signals.push({
      id: 'regexValidity',
      status: 'FAIL',
      detailId: 'regexValid',
      meta: { count: 2, names: ['rule-a', 'rule-b'] },
    })

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'output-guard:regexValidity')!
    expect(issue.severity).toBe('critical')
    expect(issue.routePath).toBe('/safety-rules?tab=output-guard')
    expect(issue.routeLabelKey).toBe('nav.safetyRules')
    expect(issue.summary.values).toEqual({ count: 2, names: 'rule-a, rule-b' })
  })

  it('falls back to "-" when output-guard signal has no names meta', () => {
    const input = buildEmptyInput()
    input.outputGuard.signals.push({
      id: 'activeRules',
      status: 'WARN',
      detailId: 'activeRulesReady',
    })

    const snapshot = buildIssueCenterSnapshot(input)
    const issue = snapshot.items.find((i) => i.id === 'output-guard:activeRules')!
    expect(issue.summary.values).toEqual({ count: 0, names: '-' })
  })

  it('emits audit issues and respects the degraded /audit route', () => {
    const healthy = buildEmptyInput()
    healthy.audit.signals.push({
      id: 'auditChannel',
      status: 'WARN',
      detailId: 'auditChannelReady',
      meta: { count: 1, total: 2 },
    })
    expect(buildIssueCenterSnapshot(healthy).items.some((i) => i.id === 'audit:auditChannel')).toBe(true)

    const degraded = buildEmptyInput()
    degraded.controlPlaneRecovery.items.push({
      probe: {
        id: 'auditLogs',
        path: '/api/admin/audits?limit=5',
        routePath: '/audit',
        status: 'FAIL',
        reason: 'probeFailed',
        manifestDeclared: true,
        httpStatus: 500,
        durationMs: 1,
        detail: 'down',
      },
      status: 'FAIL',
      kind: 'transportFailure',
      route: { path: '/audit', labelKey: 'nav.audit' },
      stepIds: ['probeDirect'],
    })
    degraded.audit.signals.push({
      id: 'auditChannel',
      status: 'WARN',
      detailId: 'auditChannelReady',
      meta: { count: 1, total: 2 },
    })
    expect(buildIssueCenterSnapshot(degraded).items.some((i) => i.id === 'audit:auditChannel')).toBe(false)
  })
})

// ──────────────────────────────────────────────────────────────────────────
// Sorting & source aggregation
// ──────────────────────────────────────────────────────────────────────────

describe('buildIssueCenterSnapshot — sorting & aggregation', () => {
  it('sorts critical before warning, then by detectedAt desc, then by SOURCE_ORDER', () => {
    const input = buildEmptyInput()
    // Two warnings with different detectedAt
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'older' }),
        preflight: {
          ok: true,
          readyForProduction: false,
          policySource: 'config',
          checkedAt: '2024-01-01T00:00:00Z',
          summary: { passCount: 1, warnCount: 1, failCount: 0 },
          checks: [],
        },
      }),
      buildMcpSnapshot({
        server: buildServerDetail({ name: 'newer' }),
        preflight: {
          ok: true,
          readyForProduction: false,
          policySource: 'config',
          checkedAt: '2024-06-01T00:00:00Z',
          summary: { passCount: 1, warnCount: 1, failCount: 0 },
          checks: [],
        },
      }),
    )
    // One critical signal
    input.outputGuard.signals.push({
      id: 'regexValidity',
      status: 'FAIL',
      detailId: 'regexValid',
    })

    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.items[0].severity).toBe('critical')
    const warningIds = snapshot.items
      .filter((i) => i.severity === 'warning')
      .map((i) => i.id)
    expect(warningIds.indexOf('mcp-preflight:newer')).toBeLessThan(warningIds.indexOf('mcp-preflight:older'))
  })

  it('breaks ties by SOURCE_ORDER when severity and detectedAt are equal', () => {
    const input = buildEmptyInput()
    // Two critical issues, both with detectedAt=null
    input.mcpServers.push(
      buildMcpSnapshot({
        server: buildServerDetail({ status: 'DISCONNECTED', name: 'srv-disconnected' }),
      }),
    )
    input.outputGuard.signals.push({
      id: 'regexValidity',
      status: 'FAIL',
      detailId: 'regexValid',
    })

    const snapshot = buildIssueCenterSnapshot(input)
    const ids = snapshot.items.map((i) => i.id)
    expect(ids.indexOf('mcp-disconnected:srv-disconnected')).toBeLessThan(
      ids.indexOf('output-guard:regexValidity'),
    )
  })

  it('aggregates source counts only for sources with at least one issue', () => {
    const input = buildEmptyInput()
    input.outputGuard.signals.push(
      { id: 'regexValidity', status: 'FAIL', detailId: 'regexValid' },
      { id: 'activeRules', status: 'WARN', detailId: 'activeRulesReady' },
    )

    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.sources).toHaveLength(1)
    expect(snapshot.sources[0]).toMatchObject({
      source: 'outputGuard',
      total: 2,
      criticalCount: 1,
      warningCount: 1,
    })
  })

  it('counts critical and warning totals across sources', () => {
    const input = buildEmptyInput()
    input.outputGuard.signals.push({ id: 'regexValidity', status: 'FAIL', detailId: 'regexValid' })
    input.audit.signals.push({
      id: 'auditChannel',
      status: 'WARN',
      detailId: 'auditChannelReady',
    })

    const snapshot = buildIssueCenterSnapshot(input)
    expect(snapshot.total).toBe(2)
    expect(snapshot.criticalCount).toBe(1)
    expect(snapshot.warningCount).toBe(1)
  })
})

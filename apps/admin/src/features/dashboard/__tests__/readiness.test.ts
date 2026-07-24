import { describe, expect, it } from 'vitest'
import { classifyMcpReadiness, classifyPlatformReadiness, summarizeMcpReadiness } from '../readiness'
import type { McpPreflightResponse, McpServerResponse } from '../../mcp-servers/types'
import type { DashboardMcpReadinessSummary } from '../types'

function server(status: string, name = 'atlassian'): McpServerResponse {
  return {
    id: `${name}-id`,
    name,
    description: null,
    transportType: 'STREAMABLE_HTTP',
    autoConnect: true,
    status,
    toolCount: 12,
    createdAt: 0,
    updatedAt: 0,
  }
}

function preflight(overrides: Partial<McpPreflightResponse> = {}): McpPreflightResponse {
  return {
    ok: true,
    readyForProduction: true,
    policySource: 'environment',
    checkedAt: '2026-03-07T09:00:00Z',
    summary: {
      passCount: 8,
      warnCount: 0,
      failCount: 0,
    },
    checks: [],
    ...overrides,
  }
}

function mcpSummary(overrides: Partial<DashboardMcpReadinessSummary> = {}): DashboardMcpReadinessSummary {
  return {
    totalServers: 2,
    checkedServers: 2,
    readyCount: 2,
    attentionCount: 0,
    unsupportedCount: 0,
    disconnectedCount: 0,
    ...overrides,
  }
}

describe('dashboard readiness summary', () => {
  it('classifies connected server with clean preflight as ready', () => {
    const result = classifyMcpReadiness(server('CONNECTED'), preflight(), null)

    expect(result.state).toBe('READY')
    expect(result.checked).toBe(true)
  })

  it('classifies preflight warnings as attention', () => {
    const result = classifyMcpReadiness(
      server('CONNECTED'),
      preflight({
        readyForProduction: false,
        summary: { passCount: 6, warnCount: 1, failCount: 0 },
      }),
      null,
    )

    expect(result.state).toBe('ATTENTION')
    expect(result.checked).toBe(true)
  })

  it('treats disconnected server separately from unsupported preflight', () => {
    const disconnected = classifyMcpReadiness(server('DISCONNECTED'), null, null)
    const unsupported = classifyMcpReadiness(server('CONNECTED', 'wiki'), null, new Error('HTTP 404'))

    const summary = summarizeMcpReadiness([disconnected, unsupported])

    expect(summary.disconnectedCount).toBe(1)
    expect(summary.unsupportedCount).toBe(1)
    expect(summary.attentionCount).toBe(0)
  })
})

describe('platform readiness', () => {
  it('returns RED when backend is unreachable', () => {
    const result = classifyPlatformReadiness({ backendReachable: false, mcpSummary: null })
    expect(result.level).toBe('RED')
    expect(result.labelKey).toBe('dashboard.readiness.backendUnreachable')
  })

  it('returns RED when no MCP servers are registered', () => {
    const result = classifyPlatformReadiness({
      backendReachable: true,
      mcpSummary: mcpSummary({ totalServers: 0, checkedServers: 0, readyCount: 0 }),
    })
    expect(result.level).toBe('RED')
    expect(result.labelKey).toBe('dashboard.readiness.notConfigured')
  })

  it('returns RED when mcpSummary is null', () => {
    const result = classifyPlatformReadiness({ backendReachable: true, mcpSummary: null })
    expect(result.level).toBe('RED')
    expect(result.labelKey).toBe('dashboard.readiness.notConfigured')
  })

  it('returns RED when all servers are disconnected', () => {
    const result = classifyPlatformReadiness({
      backendReachable: true,
      mcpSummary: mcpSummary({ totalServers: 3, readyCount: 0, checkedServers: 0, disconnectedCount: 3 }),
    })
    expect(result.level).toBe('RED')
    expect(result.labelKey).toBe('dashboard.readiness.allDisconnected')
  })

  it('returns YELLOW when some servers are disconnected', () => {
    const result = classifyPlatformReadiness({
      backendReachable: true,
      mcpSummary: mcpSummary({ totalServers: 3, readyCount: 2, disconnectedCount: 1 }),
    })
    expect(result.level).toBe('YELLOW')
    expect(result.labelKey).toBe('dashboard.readiness.partiallyConfigured')
  })

  it('returns YELLOW when some servers need attention', () => {
    const result = classifyPlatformReadiness({
      backendReachable: true,
      mcpSummary: mcpSummary({ totalServers: 2, readyCount: 1, attentionCount: 1, disconnectedCount: 0 }),
    })
    expect(result.level).toBe('YELLOW')
    expect(result.labelKey).toBe('dashboard.readiness.partiallyConfigured')
  })

  it('returns GREEN when all servers are ready', () => {
    const result = classifyPlatformReadiness({
      backendReachable: true,
      mcpSummary: mcpSummary({ totalServers: 2, readyCount: 2, attentionCount: 0, disconnectedCount: 0 }),
    })
    expect(result.level).toBe('GREEN')
    expect(result.labelKey).toBe('dashboard.readiness.allHealthy')
  })

  it('returns YELLOW when servers exist but none are classified as ready', () => {
    const result = classifyPlatformReadiness({
      backendReachable: true,
      mcpSummary: mcpSummary({ totalServers: 2, readyCount: 0, attentionCount: 0, unsupportedCount: 2, disconnectedCount: 0 }),
    })
    expect(result.level).toBe('YELLOW')
    expect(result.labelKey).toBe('dashboard.readiness.partiallyConfigured')
  })
})

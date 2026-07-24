import { describe, expect, it } from 'vitest'
import {
  deriveAuditEntryInsight,
  parseAuditDetail,
  summarizeAuditLogs,
} from '../auditOps'
import type { AuditLogEntry } from '../types'

function buildEntry(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: 'audit-1',
    category: 'MCP_SERVER',
    action: 'UPDATE',
    actor: 'ops-admin',
    resourceType: 'server',
    resourceId: 'atlassian',
    detail: '{"before":{"status":"DISCONNECTED"},"after":{"status":"CONNECTED"},"changes":{"status":["DISCONNECTED","CONNECTED"]}}',
    createdAt: 1710000000000,
    ...overrides,
  }
}

describe('auditOps', () => {
  it('parses structured detail and extracts changed fields', () => {
    const detail = parseAuditDetail(buildEntry().detail)

    expect(detail.isJson).toBe(true)
    expect(detail.hasBeforeAfter).toBe(true)
    expect(detail.changeKeys).toEqual(['status'])
    expect(detail.formatted).toContain('"before"')
  })

  it('derives rollback insight and recovery route from the entry scope', () => {
    const insight = deriveAuditEntryInsight(buildEntry())

    expect(insight.highRisk).toBe(true)
    expect(insight.rollbackReady).toBe(true)
    expect(insight.recoveryRoute).toEqual({
      path: '/mcp-servers',
      labelKey: 'nav.mcpServers',
    })
  })

  it('summarizes audit feed readiness and resource bundles', () => {
    const summary = summarizeAuditLogs([
      buildEntry(),
      buildEntry({
        id: 'audit-2',
        action: 'DISABLE',
        resourceId: 'swagger',
        detail: 'temporarily disabled server',
      }),
      buildEntry({
        id: 'audit-3',
        category: 'OUTPUT_GUARD',
        action: 'UPDATE',
        resourceType: 'rule',
        resourceId: 'block-password',
        detail: '{"changes":{"pattern":["old","new"]}}',
      }),
    ], null)

    expect(summary.status).toBe('PASS')
    expect(summary.totalLogs).toBe(3)
    expect(summary.uniqueActors).toBe(1)
    expect(summary.uniqueResources).toBe(3)
    expect(summary.rollbackReadyCount).toBe(3)
    expect(summary.categories[0]).toEqual({ category: 'MCP_SERVER', count: 2 })
    expect(summary.resourceBundles).toContainEqual(expect.objectContaining({
      label: 'rule:block-password',
      rollbackReadyCount: 1,
    }))
  })

  it('routes mcp-prefixed policy categories to mcp-servers, not tool-policy', () => {
    const mcpAccess = deriveAuditEntryInsight(buildEntry({
      category: 'mcp_access_policy',
      resourceType: 'McpAccessPolicy',
      resourceId: 'atlassian',
    }))
    expect(mcpAccess.recoveryRoute).toEqual({
      path: '/mcp-servers',
      labelKey: 'nav.mcpServers',
    })

    const mcpSecurity = deriveAuditEntryInsight(buildEntry({
      category: 'mcp_security',
      resourceType: 'McpSecurityPolicy',
      resourceId: 'atlassian',
    }))
    expect(mcpSecurity.recoveryRoute).toEqual({
      path: '/mcp-servers',
      labelKey: 'nav.mcpServers',
    })
  })

  it('routes safety-rule audit entries to the consolidated safety rules page', () => {
    const toolPolicy = deriveAuditEntryInsight(buildEntry({
      category: 'TOOL_POLICY',
      resourceType: 'policy',
      resourceId: 'default',
    }))
    expect(toolPolicy.recoveryRoute).toEqual({
      path: '/safety-rules?tab=tool-policy',
      labelKey: 'nav.safetyRules',
    })

    const outputGuard = deriveAuditEntryInsight(buildEntry({
      category: 'OUTPUT_GUARD',
      resourceType: 'rule',
      resourceId: 'block-secret',
    }))
    expect(outputGuard.recoveryRoute).toEqual({
      path: '/safety-rules?tab=output-guard',
      labelKey: 'nav.safetyRules',
    })
  })

})

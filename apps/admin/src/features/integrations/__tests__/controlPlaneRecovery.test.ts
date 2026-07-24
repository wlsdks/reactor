import { describe, expect, it } from 'vitest'
import { summarizeControlPlaneRecovery } from '../controlPlaneRecovery'
import type { ControlPlaneProbeSnapshot } from '../controlPlaneProbes'

function buildProbe(overrides: Partial<ControlPlaneProbeSnapshot>): ControlPlaneProbeSnapshot {
  return {
    id: 'toolPolicy',
    path: '/api/tool-policy',
    routePath: '/tool-policy',
    status: 'WARN',
    reason: 'notAdvertised',
    manifestDeclared: false,
    httpStatus: 404,
    durationMs: 12,
    detail: 'HTTP 404',
    ...overrides,
  }
}

describe('controlPlaneRecovery', () => {
  it('classifies missing contracts and transport failures for operator recovery', () => {
    const summary = summarizeControlPlaneRecovery([
      buildProbe({ id: 'toolPolicy', path: '/api/tool-policy', routePath: '/tool-policy' }),
      buildProbe({
        id: 'mcpSecurity',
        path: '/api/mcp/security',
        routePath: '/mcp-security',
        status: 'FAIL',
        reason: 'probeFailed',
        manifestDeclared: true,
        httpStatus: null,
        detail: 'Failed to fetch',
      }),
    ])

    expect(summary.status).toBe('FAIL')
    expect(summary.attentionCount).toBe(2)
    expect(summary.transportFailureCount).toBe(1)
    expect(summary.missingContractCount).toBe(1)
    expect(summary.items[0]).toMatchObject({
      kind: 'transportFailure',
      route: { path: '/mcp-servers', labelKey: 'nav.mcpServers' },
      stepIds: ['probeDirect', 'inspectProxy', 'reopenConsole'],
    })
    expect(summary.items[1]).toMatchObject({
      kind: 'missingContract',
      route: { path: '/safety-rules?tab=tool-policy', labelKey: 'nav.safetyRules' },
      stepIds: ['checkManifest', 'reopenConsole'],
    })
  })

  it('ignores healthy probes when building the attention queue', () => {
    const summary = summarizeControlPlaneRecovery([
      buildProbe({
        id: 'capabilities',
        path: '/api/admin/capabilities',
        routePath: '/integrations',
        status: 'PASS',
        reason: 'ready',
        manifestDeclared: true,
        httpStatus: 200,
        detail: 'OK',
      }),
    ])

    expect(summary.status).toBe('PASS')
    expect(summary.attentionCount).toBe(0)
    expect(summary.items).toEqual([])
  })
})

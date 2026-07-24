import { describe, expect, it } from 'vitest'
import {
  findKnownProjectServer,
  summarizeReactorConnection,
  summarizeKnownProjectConnection,
} from '../projectConnections'

describe('project connection helpers', () => {
  it('marks Reactor as healthy when required contracts are present', () => {
    const summary = summarizeReactorConnection(new Set([
      '/api/admin/capabilities',
      '/api/ops/dashboard',
      '/api/mcp/servers',
      '/api/tool-policy',
    ]))

    expect(summary.status).toBe('PASS')
    expect(summary.missingPaths).toHaveLength(0)
  })

  it('finds known MCP servers by configured project kind', () => {
    const atlassian = findKnownProjectServer('atlassian', [
      {
        id: '1',
        name: 'custom-atlassian',
        description: null,
        transportType: 'SSE',
        autoConnect: true,
        status: 'CONNECTED',
        toolCount: 10,
        createdAt: 0,
        updatedAt: 0,
      },
    ])

    expect(atlassian?.name).toBe('custom-atlassian')
  })

  it('surfaces preflight warnings and swagger source counts', () => {
    const snapshot = summarizeKnownProjectConnection(
      'swagger',
      {
        id: 'swagger-1',
        name: 'swagger',
        description: null,
        transportType: 'SSE',
        autoConnect: true,
        status: 'CONNECTED',
        toolCount: 12,
        createdAt: 0,
        updatedAt: 0,
      },
      {
        ok: true,
        readyForProduction: false,
        policySource: 'dynamic',
        checkedAt: '2026-03-12T00:00:00Z',
        summary: {
          passCount: 4,
          warnCount: 1,
          failCount: 0,
        },
        checks: [],
      },
      undefined,
      {
        sourceCount: 3,
        publishedSourceCount: 2,
      },
    )

    expect(snapshot.status).toBe('WARN')
    expect(snapshot.sourceCount).toBe(3)
    expect(snapshot.publishedSourceCount).toBe(2)
  })

  it('marks the connection as failed when the registry cannot be reached', () => {
    const snapshot = summarizeKnownProjectConnection('atlassian', null, null, 'registry offline')

    expect(snapshot.status).toBe('FAIL')
    expect(snapshot.error).toBe('registry offline')
  })
})

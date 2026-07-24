import { describe, expect, it } from 'vitest'
import { buildFleetActionReport, summarizeFleetAttention } from '../fleetActions'
import type { McpServerResponse } from '../types'

function server(name: string, status: string): McpServerResponse {
  return {
    id: name,
    name,
    description: null,
    transportType: 'SSE',
    autoConnect: true,
    status,
    toolCount: 0,
    createdAt: 1,
    updatedAt: 1,
  }
}

describe('fleetActions', () => {
  it('separates recovery and preflight targets from the registry', () => {
    const summary = summarizeFleetAttention([
      server('atlassian', 'CONNECTED'),
      server('swagger', 'DISCONNECTED'),
      server('ops', 'FAILED'),
      server('local', 'ERROR'),
      server('preview', 'PENDING'),
    ])

    expect(summary.preflightTargets.map((item) => item.name)).toEqual(['atlassian'])
    expect(summary.recoveryTargets.map((item) => item.name)).toEqual(['swagger', 'ops', 'local'])
  })

  it('builds a WARN fleet report when any item needs attention', () => {
    const report = buildFleetActionReport('preflightConnected', [
      { name: 'atlassian', action: 'preflightConnected', status: 'PASS', detail: 'ready' },
      { name: 'swagger', action: 'preflightConnected', status: 'WARN', detail: 'unsupported' },
    ])

    expect(report.status).toBe('WARN')
    expect(report.total).toBe(2)
    expect(report.passCount).toBe(1)
    expect(report.warnCount).toBe(1)
    expect(report.failCount).toBe(0)
  })
})

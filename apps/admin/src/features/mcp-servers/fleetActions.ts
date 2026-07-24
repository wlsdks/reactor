import type { OperatorStatus } from './types'
import type { McpPreflightResponse, McpServerResponse } from './types'

export type FleetActionKind = 'recoverAttention' | 'preflightConnected'

export interface FleetAttentionSummary {
  recoveryTargets: McpServerResponse[]
  preflightTargets: McpServerResponse[]
}

export interface FleetActionItemReport {
  name: string
  action: FleetActionKind
  status: OperatorStatus
  detail: string
  checkedAt?: string
  preflight?: McpPreflightResponse
}

export interface FleetActionReport {
  action: FleetActionKind
  status: OperatorStatus
  generatedAt: string
  total: number
  passCount: number
  warnCount: number
  failCount: number
  items: FleetActionItemReport[]
}

const RECOVERY_STATUSES = new Set(['DISCONNECTED', 'FAILED', 'ERROR'])

export function summarizeFleetAttention(servers: McpServerResponse[]): FleetAttentionSummary {
  return {
    recoveryTargets: servers.filter((server) => RECOVERY_STATUSES.has(server.status)),
    preflightTargets: servers.filter((server) => server.status === 'CONNECTED'),
  }
}

export function buildFleetActionReport(
  action: FleetActionKind,
  items: FleetActionItemReport[],
): FleetActionReport {
  const passCount = items.filter((item) => item.status === 'PASS').length
  const warnCount = items.filter((item) => item.status === 'WARN').length
  const failCount = items.filter((item) => item.status === 'FAIL').length

  return {
    action,
    status: failCount > 0 ? 'FAIL' : warnCount > 0 ? 'WARN' : 'PASS',
    generatedAt: new Date().toISOString(),
    total: items.length,
    passCount,
    warnCount,
    failCount,
    items,
  }
}

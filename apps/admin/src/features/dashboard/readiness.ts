import type { McpPreflightResponse, McpServerResponse } from '../mcp-servers/types'
import type { DashboardMcpReadinessSummary } from './types'
import { getErrorMessage } from '../../shared/lib/getErrorMessage'

export type McpReadinessState = 'READY' | 'ATTENTION' | 'UNSUPPORTED' | 'DISCONNECTED'

export interface McpReadinessSnapshot {
  name: string
  state: McpReadinessState
  checked: boolean
}

export function classifyMcpReadiness(
  server: McpServerResponse,
  preflight?: McpPreflightResponse | null,
  error?: unknown,
): McpReadinessSnapshot {
  if (server.status !== 'CONNECTED') {
    return { name: server.name, state: 'DISCONNECTED', checked: false }
  }
  if (preflight) {
    const hasAttention = preflight.summary.failCount > 0 || preflight.summary.warnCount > 0 || !preflight.readyForProduction
    return {
      name: server.name,
      state: hasAttention ? 'ATTENTION' : 'READY',
      checked: true,
    }
  }
  if (isUnsupportedPreflight(error)) {
    return { name: server.name, state: 'UNSUPPORTED', checked: false }
  }
  // preflight 가 null 이고 에러도 없으면 백엔드가 204(admin token 미설정) 를 반환한
  // 케이스 → 서버 자체는 CONNECTED 이므로 READY 로 분류. (과거 ATTENTION 으로 잘못
  // 분류되어 대시보드/이슈센터가 빨간색으로 표시되던 회귀 수정)
  if (!error) {
    return { name: server.name, state: 'READY', checked: false }
  }
  return { name: server.name, state: 'ATTENTION', checked: false }
}

export function summarizeMcpReadiness(items: McpReadinessSnapshot[]): DashboardMcpReadinessSummary {
  return {
    totalServers: items.length,
    checkedServers: items.filter((item) => item.checked).length,
    readyCount: items.filter((item) => item.state === 'READY').length,
    attentionCount: items.filter((item) => item.state === 'ATTENTION').length,
    unsupportedCount: items.filter((item) => item.state === 'UNSUPPORTED').length,
    disconnectedCount: items.filter((item) => item.state === 'DISCONNECTED').length,
  }
}

function isUnsupportedPreflight(error?: unknown): boolean {
  if (!error) return false
  const msg = getErrorMessage(error)
  return msg.includes('HTTP 404') || msg.includes('Unsupported')
}

export type PlatformReadinessLevel = 'GREEN' | 'YELLOW' | 'RED'

export interface PlatformReadiness {
  level: PlatformReadinessLevel
  labelKey: string
  actionKey: string
}

export interface PlatformReadinessInput {
  backendReachable: boolean
  mcpSummary: DashboardMcpReadinessSummary | null
}

export function classifyPlatformReadiness(input: PlatformReadinessInput): PlatformReadiness {
  if (!input.backendReachable) {
    return { level: 'RED', labelKey: 'dashboard.readiness.backendUnreachable', actionKey: 'dashboard.readiness.actionBackendUnreachable' }
  }
  if (!input.mcpSummary || input.mcpSummary.totalServers === 0) {
    return { level: 'RED', labelKey: 'dashboard.readiness.notConfigured', actionKey: 'dashboard.readiness.actionNotConfigured' }
  }
  const { totalServers, disconnectedCount, attentionCount, readyCount } = input.mcpSummary
  if (disconnectedCount === totalServers) {
    return { level: 'RED', labelKey: 'dashboard.readiness.allDisconnected', actionKey: 'dashboard.readiness.actionAllDisconnected' }
  }
  if (disconnectedCount > 0 || attentionCount > 0) {
    return { level: 'YELLOW', labelKey: 'dashboard.readiness.partiallyConfigured', actionKey: 'dashboard.readiness.actionPartiallyConfigured' }
  }
  if (readyCount === totalServers) {
    return { level: 'GREEN', labelKey: 'dashboard.readiness.allHealthy', actionKey: 'dashboard.readiness.actionAllHealthy' }
  }
  return { level: 'YELLOW', labelKey: 'dashboard.readiness.partiallyConfigured', actionKey: 'dashboard.readiness.actionPartiallyConfigured' }
}

const LEVEL_TO_BADGE: Record<PlatformReadinessLevel, string> = { GREEN: 'PASS', YELLOW: 'WARN', RED: 'FAIL' }
const LEVEL_TO_CSS: Record<PlatformReadinessLevel, string> = { GREEN: '--green', YELLOW: '--yellow', RED: '--red' }

export function readinessBadgeStatus(level: PlatformReadinessLevel): string { return LEVEL_TO_BADGE[level] }
export function readinessCssVar(level: PlatformReadinessLevel): string { return LEVEL_TO_CSS[level] }

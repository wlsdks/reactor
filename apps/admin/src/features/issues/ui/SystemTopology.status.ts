/**
 * SystemTopology — status / count derivation + view persistence helpers.
 *
 * Pure functions split out of `SystemTopology.tsx` so the orchestrator stays
 * focused on React Flow wiring. No React imports here — keep this side-effect
 * free for easy unit reuse.
 */
import type { IssueCenterSnapshot, IssueSource } from '../types'
import type { TopologyData } from '../query'

export type NodeStatus = 'healthy' | 'warning' | 'critical'

export const STATUS_COLOR: Record<NodeStatus, string> = {
  healthy: 'var(--green)',
  warning: 'var(--yellow)',
  critical: 'var(--red)',
}

export type TopologyView = 'graph' | 'list'
export const VIEW_STORAGE_KEY = 'reactor-admin-issues-view'

export function readInitialView(): TopologyView {
  if (typeof window === 'undefined') return 'list'
  try {
    const raw = window.localStorage.getItem(VIEW_STORAGE_KEY)
    return raw === 'graph' ? 'graph' : 'list'
  } catch {
    return 'list'
  }
}

export function persistView(view: TopologyView): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(VIEW_STORAGE_KEY, view)
  } catch {
    // ignore quota / access errors — view preference is non-critical.
  }
}

// ─────────────────────────────────────────────────────────────────────────
// 데이터 → 노드 status / count 계산
// ─────────────────────────────────────────────────────────────────────────
export function nodeStatus(source: IssueSource, snap: IssueCenterSnapshot): NodeStatus {
  const s = snap.sources.find((x) => x.source === source)
  if (!s) return 'healthy'
  if (s.criticalCount > 0) return 'critical'
  if (s.warningCount > 0) return 'warning'
  return 'healthy'
}

/**
 * MCP 서버 노드 상태 계산. serverId 는 registry 의 server.name.
 *
 * 이슈 센터 item.id 가 server.name 의 substring 을 포함하는지로 매칭하며,
 * topology.projects 에서 연결 상태도 반영한다. kind 하드코딩 없이 동적 서버명 지원.
 */
export function mcpStatus(
  serverId: string,
  snap: IssueCenterSnapshot,
  topo: TopologyData,
): NodeStatus {
  const project = topo.projects.find((p) => p.id === serverId)
  const isDisconnected = project?.status === 'DISCONNECTED' || project?.status === 'FAIL'
  const needle = serverId.toLowerCase()
  const hasCritical = snap.items.some(
    (it) => it.source === 'mcpServers' && it.severity === 'critical' && it.id.toLowerCase().includes(needle),
  )
  const hasWarning = snap.items.some(
    (it) => it.source === 'mcpServers' && it.severity === 'warning' && it.id.toLowerCase().includes(needle),
  )
  if (isDisconnected || hasCritical) return 'critical'
  if (hasWarning) return 'warning'
  return 'healthy'
}

export function sourceCount(source: IssueSource, snap: IssueCenterSnapshot): number {
  const s = snap.sources.find((x) => x.source === source)
  return (s?.criticalCount ?? 0) + (s?.warningCount ?? 0)
}

export function mcpCount(serverId: string, snap: IssueCenterSnapshot): number {
  const needle = serverId.toLowerCase()
  return snap.items.filter(
    (it) => it.source === 'mcpServers' && it.id.toLowerCase().includes(needle) &&
      (it.severity === 'critical' || it.severity === 'warning'),
  ).length
}

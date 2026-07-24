/**
 * SystemTopology — node placement / layout helpers.
 *
 * Governance / monitoring nodes use fixed coordinates while MCP servers are
 * placed dynamically based on registry data. Pure functions, no React.
 */
import type { TopologyData } from '../query'

export type ClusterName = 'mcp' | 'governance' | 'monitoring'

export interface NodePlacement {
  x: number
  y: number
  cluster: ClusterName
  label: string
}

type FixedPlacement = Omit<NodePlacement, 'label'> & { labelKey: string }

const FIXED_POSITIONS_RAW: Record<string, FixedPlacement> = {
  toolPolicy:   { x: 580, y: 30,  cluster: 'governance', labelKey: 'issuesPage.topology.toolPolicy' },
  outputGuard:  { x: 660, y: 140, cluster: 'governance', labelKey: 'issuesPage.topology.outputGuard' },
  mcpSecurity:  { x: 600, y: 250, cluster: 'governance', labelKey: 'issuesPage.topology.mcpSecurity' },
  audit:        { x: 200, y: 320, cluster: 'monitoring', labelKey: 'issuesPage.topology.audit' },
  scheduler:    { x: 350, y: 340, cluster: 'monitoring', labelKey: 'issuesPage.topology.scheduler' },
  approvals:    { x: 480, y: 320, cluster: 'monitoring', labelKey: 'issuesPage.topology.approvals' },
}

export function resolveFixedPositions(t: (key: string) => string): Record<string, NodePlacement> {
  return Object.fromEntries(
    Object.entries(FIXED_POSITIONS_RAW).map(([id, { labelKey, ...rest }]) => [
      id,
      { ...rest, label: t(labelKey) },
    ]),
  )
}

const MCP_COLUMN_X = 60
const MCP_ROW_BASE_Y = 50
const MCP_ROW_STEP = 80

/** 서버 이름을 사용자 친화적 레이블로 변환 (예: `atlassian-mcp-server` → `Atlassian`). */
export function humanizeMcpLabel(name: string): string {
  const stripped = name.replace(/[-_]?mcp[-_]?server$/i, '').replace(/[-_]+/g, ' ').trim()
  const base = stripped.length > 0 ? stripped : name
  return base.split(' ').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

/**
 * registry 프로젝트를 동적 MCP 노드 좌표로 변환한다.
 * 세로 스택 배치 (x=60 고정, y 간격 [MCP_ROW_STEP]).
 */
export function buildMcpPlacements(projects: TopologyData['projects']): Record<string, NodePlacement> {
  return projects.reduce<Record<string, NodePlacement>>((acc, project, idx) => {
    acc[project.id] = {
      x: MCP_COLUMN_X,
      y: MCP_ROW_BASE_Y + idx * MCP_ROW_STEP,
      cluster: 'mcp',
      label: humanizeMcpLabel(project.label || project.id),
    }
    return acc
  }, {})
}

export const CENTER_POS = { x: 330, y: 175 }

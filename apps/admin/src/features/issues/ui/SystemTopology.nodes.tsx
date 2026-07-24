/**
 * SystemTopology — custom React Flow node + edge renderers.
 *
 * Visual primitives split out of `SystemTopology.tsx`. Each component only
 * receives props from React Flow; status / count logic lives in
 * the orchestrator and `SystemTopology.status.ts`.
 */
import {
  Handle,
  Position,
  getBezierPath,
  type Node,
  type Edge,
  type NodeProps,
  type EdgeProps,
} from '@xyflow/react'
import { STATUS_COLOR, type NodeStatus } from './SystemTopology.status'

// ─────────────────────────────────────────────────────────────────────────
// Service node — MCP / governance / monitoring service representation
// ─────────────────────────────────────────────────────────────────────────
export interface ServiceNodeData extends Record<string, unknown> {
  label: string
  status: NodeStatus
  count: number
  cluster: 'mcp' | 'governance' | 'monitoring'
  isActive: boolean
  isDimmed: boolean
  sourceId: string
}

export function ServiceNode({ data }: NodeProps<Node<ServiceNodeData>>) {
  const { label, status, count, isActive, isDimmed, sourceId } = data
  const color = STATUS_COLOR[status]

  return (
    <div
      className={`topo-rf-node ${isActive ? 'topo-rf-node--active' : ''} ${isDimmed ? 'topo-rf-node--dimmed' : ''}`}
      data-status={status}
      data-source={sourceId}
      style={{ ['--topo-color' as string]: color }}
    >
      {/* React Flow 가 edge 를 anchor 시키기 위해 invisible handle 필요 */}
      <Handle type="target" position={Position.Left} className="topo-rf-handle" />
      <Handle type="source" position={Position.Right} className="topo-rf-handle" />

      <span className="topo-rf-node__body">
        <span className="topo-rf-node__dot" />
        <span className="topo-rf-node__label">{label}</span>
        {count > 0 && (
          <span className="topo-rf-node__count">{count > 99 ? '99+' : count}</span>
        )}
      </span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────
// Center node — Reactor (label bound to i18n key `issuesPage.topology.centerLabel`)
// ─────────────────────────────────────────────────────────────────────────
export interface CenterNodeData extends Record<string, unknown> {
  isAllSelected: boolean
  label: string
}

export function CenterNode({ data }: NodeProps<Node<CenterNodeData>>) {
  const classes = [
    'topo-rf-center',
    data.isAllSelected ? 'topo-rf-center--active' : '',
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <div className={classes}>
      <Handle type="source" position={Position.Top}    id="t" className="topo-rf-handle" />
      <Handle type="source" position={Position.Right}  id="r" className="topo-rf-handle" />
      <Handle type="source" position={Position.Bottom} id="b" className="topo-rf-handle" />
      <Handle type="source" position={Position.Left}   id="l" className="topo-rf-handle" />
      <span className="topo-rf-center__core">
        <span className="topo-rf-center__brand">{data.label}</span>
      </span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────
// Status edge — color by status, dashed when a service is disconnected.
// ─────────────────────────────────────────────────────────────────────────
export interface StatusEdgeData extends Record<string, unknown> {
  status: NodeStatus
  isDisconnected: boolean
}

export function StatusEdge({
  sourceX, sourceY, targetX, targetY,
  sourcePosition, targetPosition,
  data,
}: EdgeProps<Edge<StatusEdgeData>>) {
  const [path] = getBezierPath({
    sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition,
    curvature: 0.3,
  })
  const color = STATUS_COLOR[data?.status ?? 'healthy']
  const dashed = data?.isDisconnected
  return (
    <g className="topo-rf-edge" data-status={data?.status ?? 'healthy'}>
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeOpacity={0.35}
        strokeWidth={dashed ? 1.2 : 1.6}
        strokeDasharray={dashed ? '5 4' : undefined}
      />
    </g>
  )
}

export const NODE_TYPES = { service: ServiceNode, center: CenterNode } as const
export const EDGE_TYPES = { status: StatusEdge } as const

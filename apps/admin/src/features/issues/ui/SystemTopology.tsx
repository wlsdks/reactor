import { useMemo, useCallback, useEffect, useState } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type ReactFlowInstance,
  type NodeMouseHandler,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useTranslation } from 'react-i18next'
import type { IssueCenterSnapshot, IssueSource } from '../types'
import type { TopologyData } from '../query'
import {
  STATUS_COLOR,
  mcpCount,
  mcpStatus,
  nodeStatus,
  persistView,
  readInitialView,
  sourceCount,
  type TopologyView,
} from './SystemTopology.status'
import {
  CENTER_POS,
  buildMcpPlacements,
  resolveFixedPositions,
  type NodePlacement,
} from './SystemTopology.layout'
import {
  EDGE_TYPES,
  NODE_TYPES,
  type CenterNodeData,
  type ServiceNodeData,
  type StatusEdgeData,
} from './SystemTopology.nodes'

/**
 * 토폴로지 노드 식별자 — IssueSource (governance/monitoring 고정) 또는
 * registry 로부터 동적으로 로드된 MCP 서버 이름 (예: `atlassian-mcp-server`).
 * 하드코딩 kind 대신 문자열로 수용해 사용자가 등록한 모든 MCP 서버 클릭 가능.
 */
export type TopologyNodeId = IssueSource | string

interface SystemTopologyProps {
  snapshot: IssueCenterSnapshot
  topology: TopologyData
  activeSource: TopologyNodeId | null
  onNodeClick: (source: TopologyNodeId | null) => void
  onCenterClick: () => void
}

// ─────────────────────────────────────────────────────────────────────────
// 메인 컴포넌트
// ─────────────────────────────────────────────────────────────────────────
function TopologyInner({
  snapshot, topology, activeSource, onNodeClick, onCenterClick,
}: SystemTopologyProps) {
  const { t } = useTranslation()

  // MCP 는 registry 기반 동적 배치 — topology.projects 변경 시 재계산.
  const positions = useMemo<Record<string, NodePlacement>>(() => {
    return { ...buildMcpPlacements(topology.projects), ...resolveFixedPositions(t) }
  }, [topology.projects, t])

  const mcpIds = useMemo(() => topology.projects.map((p) => p.id), [topology.projects])

  const centerLabel = t('issuesPage.topology.centerLabel')

  // 초기 노드/엣지 — positions 변화에 대응하여 재계산
  const initialNodes = useMemo<Node[]>(() => {
    const ns: Node[] = []
    ns.push({
      id: 'center',
      type: 'center',
      position: CENTER_POS,
        data: {
          isAllSelected: false,
          label: centerLabel,
      } as CenterNodeData,
      draggable: false,
      selectable: false,
    })
    Object.entries(positions).forEach(([id, pos]) => {
      ns.push({
        id,
        type: 'service',
        position: { x: pos.x, y: pos.y },
        data: {
          label: pos.label,
          status: 'healthy', count: 0, cluster: pos.cluster,
          isActive: false, isDimmed: false,
          sourceId: id,
        } as ServiceNodeData,
        draggable: false,
      })
    })
    return ns
  }, [positions, centerLabel])

  const initialEdges = useMemo<Edge[]>(() => {
    return Object.entries(positions).map(([id, pos]) => {
      const handleId = pos.cluster === 'mcp' ? 'l'
        : pos.cluster === 'governance' ? 'r'
        : 'b'
      return {
        id: `e-center-${id}`,
        source: 'center',
        sourceHandle: handleId,
        target: id,
        type: 'status',
        data: {
          status: 'healthy',
          isDisconnected: false,
        } as StatusEdgeData,
      }
    })
  }, [positions])

  const [nodes, setNodes] = useNodesState(initialNodes)
  const [edges, setEdges] = useEdgesState(initialEdges)

  // 노드 집합이 변하면(topology.projects 추가/제거) nodes/edges 재초기화
  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const mcpIdSet = useMemo(() => new Set(mcpIds), [mcpIds])

  // snapshot/topology/activeSource 변경 시 status/count/active 만 업데이트.
  // The relation view is intentionally static: it orients the operator but
  // does not compete with the issue queue through simulated motion.
  useEffect(() => {
    setNodes((prev) => prev.map((n) => {
      if (n.id === 'center') {
        return { ...n, data: {
          ...n.data,
          isAllSelected: activeSource === null,
          label: centerLabel,
        } as CenterNodeData }
      }
      const id = n.id
      const isMcp = mcpIdSet.has(id)
      const status = isMcp
        ? mcpStatus(id, snapshot, topology)
        : nodeStatus(id as IssueSource, snapshot)
      const count = isMcp
        ? mcpCount(id, snapshot)
        : sourceCount(id as IssueSource, snapshot)
      const isActive = activeSource === id
      const isDimmed = activeSource !== null && activeSource !== id
      return { ...n, data: { ...n.data, status, count, isActive, isDimmed } as ServiceNodeData }
    }))
    setEdges((prev) => prev.map((e) => {
      const id = e.target
      const pos = positions[id]
      if (!pos) return e
      const isMcp = mcpIdSet.has(id)
      const status = isMcp
        ? mcpStatus(id, snapshot, topology)
        : nodeStatus(id as IssueSource, snapshot)
      const isDisconnected = isMcp
        ? topology.projects.find((p) => p.id === id)?.status === 'DISCONNECTED' ||
          topology.projects.find((p) => p.id === id)?.status === 'FAIL'
        : false
      return { ...e, data: { status, isDisconnected } as StatusEdgeData }
    }))
  }, [
    snapshot,
    topology,
    activeSource,
    positions,
    mcpIdSet,
    setNodes,
    setEdges,
    centerLabel,
  ])

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_evt, node) => {
      if (node.id === 'center') {
        onCenterClick()
      } else {
        onNodeClick(activeSource === node.id ? null : (node.id as TopologyNodeId))
      }
    },
    [activeSource, onCenterClick, onNodeClick],
  )

  const onInit = useCallback((rf: ReactFlowInstance) => {
    // 초기 fit + 약간의 padding
    rf.fitView({ padding: 0.18, duration: 0 })
  }, [])

  // 카운트 (legend) — positions 기반 동적 집계
  const nodeStatuses = Object.keys(positions).map((id) => ({
    id,
    label: positions[id]?.label ?? id,
    cluster: positions[id]?.cluster ?? 'mcp',
    status: mcpIdSet.has(id)
      ? mcpStatus(id, snapshot, topology)
      : nodeStatus(id as IssueSource, snapshot),
    count: mcpIdSet.has(id)
      ? mcpCount(id, snapshot)
      : sourceCount(id as IssueSource, snapshot),
  }))
  const healthy = nodeStatuses.filter((n) => n.status === 'healthy').length
  const warning = nodeStatuses.filter((n) => n.status === 'warning').length
  const critical = nodeStatuses.filter((n) => n.status === 'critical').length
  const total = nodeStatuses.length

  // The queue-first list is the default. Operators can open the static map when
  // they need spatial orientation, and their explicit preference is persisted.
  const [view, setView] = useState<TopologyView>(() => readInitialView())
  const handleViewChange = useCallback((next: TopologyView) => {
    setView(next)
    persistView(next)
  }, [])

  const ariaLabel = t('issuesPage.topology.ariaLabel', {
    total, healthy, warning, critical,
  })

  return (
    <div className="system-topology-wrapper">
      <div role="tablist" aria-label={t('issuesPage.topology.view.tablistLabel')} className="topo-view-tabs">
        <button
          role="tab"
          type="button"
          id="topo-view-tab-graph"
          aria-selected={view === 'graph'}
          aria-controls="topo-view-panel-graph"
          tabIndex={view === 'graph' ? 0 : -1}
          className={`topo-view-tab${view === 'graph' ? ' topo-view-tab--active' : ''}`}
          onClick={() => handleViewChange('graph')}
        >
          {t('issuesPage.topology.view.graph')}
        </button>
        <button
          role="tab"
          type="button"
          id="topo-view-tab-list"
          aria-selected={view === 'list'}
          aria-controls="topo-view-panel-list"
          tabIndex={view === 'list' ? 0 : -1}
          className={`topo-view-tab${view === 'list' ? ' topo-view-tab--active' : ''}`}
          onClick={() => handleViewChange('list')}
        >
          {t('issuesPage.topology.view.list')}
        </button>
      </div>

      <div
        role="tabpanel"
        id="topo-view-panel-graph"
        aria-labelledby="topo-view-tab-graph"
        hidden={view !== 'graph'}
      >
        {view === 'graph' && (
          <div
            className="system-topology"
            role="img"
            aria-label={ariaLabel}
          >
            <div className="topo-rf-clusters">
              <span className="topo-rf-cluster topo-rf-cluster--mcp">{t('issuesPage.topology.clusterMcpServers')}</span>
              <span className="topo-rf-cluster topo-rf-cluster--governance">{t('issuesPage.topology.clusterGovernance')}</span>
              <span className="topo-rf-cluster topo-rf-cluster--monitoring">{t('issuesPage.topology.clusterMonitoring')}</span>
            </div>

            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              edgeTypes={EDGE_TYPES}
              onNodeClick={handleNodeClick}
              onInit={onInit}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
              panOnDrag={false}
              zoomOnScroll={false}
              zoomOnPinch={false}
              zoomOnDoubleClick={false}
              fitView
              proOptions={{ hideAttribution: true }}
              minZoom={0.5}
              maxZoom={2}
            />

            <div className="topo-rf-legend" aria-hidden="true">
              <span>
                <span className="topo-rf-legend__dot" style={{ background: 'var(--green)' }} />
                {t('issuesPage.topology.legend.healthyNodes', { count: healthy })}
              </span>
              <span>
                <span className="topo-rf-legend__dot" style={{ background: 'var(--yellow)' }} />
                {t('issuesPage.topology.legend.warningNodes', { count: warning })}
              </span>
              <span>
                <span className="topo-rf-legend__dot" style={{ background: 'var(--red)' }} />
                {t('issuesPage.topology.legend.criticalNodes', { count: critical })}
              </span>
              <span className="topo-rf-legend__suffix">
                {t('issuesPage.topology.legend.nodesSuffix')}
              </span>
            </div>
          </div>
        )}
      </div>

      <div
        role="tabpanel"
        id="topo-view-panel-list"
        aria-labelledby="topo-view-tab-list"
        hidden={view !== 'list'}
      >
        {view === 'list' && (
          <ul className="topo-node-list" aria-label={ariaLabel}>
            {nodeStatuses.map((n) => {
              const isActive = activeSource === n.id
              const statusLabel = t(`issuesPage.topology.listNode.${n.status}` as const)
              return (
                <li key={n.id} className="topo-node-list__item" data-status={n.status}>
                  <button
                    type="button"
                    className={`topo-node-list__btn${isActive ? ' topo-node-list__btn--active' : ''}`}
                    onClick={() => onNodeClick(isActive ? null : n.id)}
                    aria-pressed={isActive}
                  >
                    <span
                      className="topo-node-list__dot"
                      style={{ background: STATUS_COLOR[n.status] }}
                      aria-hidden="true"
                    />
                    <span className="topo-node-list__label">{n.label}</span>
                    <span className="topo-node-list__status">{statusLabel}</span>
                    {n.count > 0 && (
                      <span className="topo-node-list__count">
                        {t('issuesPage.topology.listNode.issues', { count: n.count })}
                      </span>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

export function SystemTopology(props: SystemTopologyProps) {
  return (
    <ReactFlowProvider>
      <TopologyInner {...props} />
    </ReactFlowProvider>
  )
}

// Default export to support React.lazy() in IssueCenterManager.
// The named export is preserved for direct (non-lazy) imports such as tests.
export default SystemTopology

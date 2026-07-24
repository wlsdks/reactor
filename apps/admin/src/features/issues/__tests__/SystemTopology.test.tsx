import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'
import { render, screen } from '../../../test/utils'
import { fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SystemTopology } from '../ui/SystemTopology'
import type { IssueCenterSnapshot } from '../types'
import type { TopologyData } from '../query'

function buildSnapshot(overrides?: Partial<IssueCenterSnapshot>): IssueCenterSnapshot {
  return {
    generatedAt: Date.now(),
    total: 0,
    criticalCount: 0,
    warningCount: 0,
    sources: [],
    items: [],
    ...overrides,
  }
}

const emptyTopology: TopologyData = {
  reactor: { status: 'PASS', apiBase: 'same-origin', missingPaths: [] },
  projects: [],
}

describe('SystemTopology', () => {
  beforeEach(() => {
    // Most node contract tests exercise the optional map explicitly.
    window.localStorage.setItem('reactor-admin-issues-view', 'graph')
  })

  afterEach(() => {
    window.localStorage.removeItem('reactor-admin-issues-view')
  })

  it('defaults to the readable list until an operator opens the relationship map', () => {
    window.localStorage.removeItem('reactor-admin-issues-view')
    const { container } = render(
      <SystemTopology
        snapshot={buildSnapshot()}
        topology={emptyTopology}
        activeSource={null}
        onNodeClick={vi.fn()}
        onCenterClick={vi.fn()}
      />
    )

    expect(screen.getByRole('tab', { name: /list|목록/i })).toHaveAttribute('aria-selected', 'true')
    expect(container.querySelector('.system-topology')).toBeNull()
  })

  it('renders Reactor center node (post-rebrand)', () => {
    render(
      <SystemTopology
        snapshot={buildSnapshot()}
        topology={emptyTopology}
        activeSource={null}
        onNodeClick={vi.fn()}
        onCenterClick={vi.fn()}
      />
    )
    // Single "Reactor" label — bound to i18n key `issuesPage.topology.centerLabel`.
    expect(screen.getByText('Reactor')).toBeInTheDocument()
  })

  it('renders cluster labels', () => {
    render(
      <SystemTopology
        snapshot={buildSnapshot()}
        topology={emptyTopology}
        activeSource={null}
        onNodeClick={vi.fn()}
        onCenterClick={vi.fn()}
      />
    )
    expect(screen.getByText('MCP SERVERS')).toBeInTheDocument()
    expect(screen.getByText('GOVERNANCE')).toBeInTheDocument()
    expect(screen.getByText('MONITORING')).toBeInTheDocument()
  })

  it('renders a node for each topology source', () => {
    render(
      <SystemTopology
        snapshot={buildSnapshot()}
        topology={emptyTopology}
        activeSource={null}
        onNodeClick={vi.fn()}
        onCenterClick={vi.fn()}
      />
    )
    // Governance nodes — labels resolved via i18n; the test instance returns
    // the i18n key when no translation is registered for it.
    expect(screen.getByText('issuesPage.topology.toolPolicy')).toBeInTheDocument()
    expect(screen.getByText('issuesPage.topology.mcpSecurity')).toBeInTheDocument()
    expect(screen.getByText('issuesPage.topology.outputGuard')).toBeInTheDocument()
    // Monitoring nodes
    expect(screen.getByText('issuesPage.topology.scheduler')).toBeInTheDocument()
    expect(screen.getByText('issuesPage.topology.approvals')).toBeInTheDocument()
    expect(screen.getByText('issuesPage.topology.audit')).toBeInTheDocument()
  })

  it('assigns critical status color when source has criticalCount > 0', () => {
    const { container } = render(
      <SystemTopology
        snapshot={buildSnapshot({
          sources: [{ source: 'scheduler', total: 1, criticalCount: 1, warningCount: 0 }],
        })}
        topology={emptyTopology}
        activeSource={null}
        onNodeClick={vi.fn()}
        onCenterClick={vi.fn()}
      />
    )
    const schedulerNode = container.querySelector('[data-source="scheduler"]')
    expect(schedulerNode).toHaveAttribute('data-status', 'critical')
  })

  it('calls onNodeClick with source when a service node is clicked', () => {
    const onNodeClick = vi.fn()
    render(
      <SystemTopology
        snapshot={buildSnapshot()}
        topology={emptyTopology}
        activeSource={null}
        onNodeClick={onNodeClick}
        onCenterClick={vi.fn()}
      />
    )
    fireEvent.click(screen.getByText('issuesPage.topology.scheduler'))
    expect(onNodeClick).toHaveBeenCalledWith('scheduler')
  })

  it('calls onNodeClick with null when clicking the already-active node (deselect)', () => {
    const onNodeClick = vi.fn()
    render(
      <SystemTopology
        snapshot={buildSnapshot()}
        topology={emptyTopology}
        activeSource="scheduler"
        onNodeClick={onNodeClick}
        onCenterClick={vi.fn()}
      />
    )
    fireEvent.click(screen.getByText('issuesPage.topology.scheduler'))
    expect(onNodeClick).toHaveBeenCalledWith(null)
  })

  it('applies role="img" + aria-label summarising node counts', () => {
    const { container } = render(
      <SystemTopology
        snapshot={buildSnapshot({
          sources: [
            { source: 'scheduler', total: 1, criticalCount: 1, warningCount: 0 },
            { source: 'audit', total: 1, criticalCount: 0, warningCount: 1 },
          ],
        })}
        topology={emptyTopology}
        activeSource={null}
        onNodeClick={vi.fn()}
        onCenterClick={vi.fn()}
      />
    )
    const graph = container.querySelector('[role="img"]')
    expect(graph).not.toBeNull()
    const label = graph?.getAttribute('aria-label') ?? ''
    // 6 fixed governance/monitoring nodes — 1 critical + 1 warning + 4 healthy.
    expect(label).toMatch(/6/)
    expect(label).toMatch(/1 critical|1 심각/)
  })

  it('keeps the optional relationship map static and free from decorative motion', () => {
    const { container } = render(
      <SystemTopology
        snapshot={buildSnapshot()}
        topology={emptyTopology}
        activeSource={null}
        onNodeClick={vi.fn()}
        onCenterClick={vi.fn()}
      />
    )

    expect(container.querySelector('.topo-rf-center__orbit')).toBeNull()
    expect(container.querySelector('.topo-rf-edge__flow')).toBeNull()
    expect(container.querySelector('.topo-rf-node__pulse')).toBeNull()
  })

  it('switches to the list view and persists the explicit preference', async () => {
    const user = userEvent.setup()
    render(
      <SystemTopology
        snapshot={buildSnapshot()}
        topology={emptyTopology}
        activeSource={null}
        onNodeClick={vi.fn()}
        onCenterClick={vi.fn()}
      />
    )
    const listTab = screen.getByRole('tab', { name: /list|목록/i })
    await user.click(listTab)
    expect(window.localStorage.getItem('reactor-admin-issues-view')).toBe('list')
    // List renders node labels inside a button — at least Scheduler should be present.
    const listPanel = document.querySelector('#topo-view-panel-list')
    expect(listPanel).not.toBeNull()
    expect(listPanel?.getAttribute('hidden')).toBeNull()
  })

  it('reads a list-view preference from localStorage on mount', () => {
    window.localStorage.setItem('reactor-admin-issues-view', 'list')
    render(
      <SystemTopology
        snapshot={buildSnapshot()}
        topology={emptyTopology}
        activeSource={null}
        onNodeClick={vi.fn()}
        onCenterClick={vi.fn()}
      />
    )
    const listTab = screen.getByRole('tab', { name: /list|목록/i })
    expect(listTab).toHaveAttribute('aria-selected', 'true')
  })
})

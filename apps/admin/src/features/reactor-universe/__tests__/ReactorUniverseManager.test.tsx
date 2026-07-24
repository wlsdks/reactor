import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor, fireEvent, i18n } from '../../../test/utils'
import { ReactorUniverseManager } from '../ui/ReactorUniverseManager'
import type { AgentSpec } from '../types'

vi.mock('../api', () => ({
  listAgentSpecs: vi.fn(),
  deleteAgentSpec: vi.fn(),
  updateAgentSpec: vi.fn(),
  createAgentSpec: vi.fn(),
  getAgentSpec: vi.fn(),
}))

vi.mock('../ui/AgentSpecModal', () => ({
  AgentSpecModal: ({ onClose }: { onClose: () => void }) => (
    <div role="dialog" aria-label="Agent editor">
      <button onClick={onClose}>Cancel editor</button>
    </div>
  ),
}))

import * as agentApi from '../api'
const listAgentSpecsMock = vi.mocked(agentApi.listAgentSpecs)

function buildAgent(overrides: Partial<AgentSpec> = {}): AgentSpec {
  return {
    id: 'a1',
    name: 'Test Agent',
    description: 'desc',
    mode: 'SPECIALIST',
    systemPromptPreview: null,
    hasSystemPrompt: false,
    independentExecution: true,
    keywords: ['k1'],
    toolNames: ['t1'],
    enabled: true,
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-01T00:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  i18n.addResourceBundle(
    'en',
    'translation',
    {
      'reactorUniverse.title': 'Reactor Universe',
      'reactorUniverse.description': 'Manage specialist agents',
      'reactorUniverse.createAgent': 'Add Agent',
      'reactorUniverse.emptyTitle': 'No agents yet',
      'reactorUniverse.emptyDescription': 'Create your first specialist agent',
      'reactorUniverse.createFirst': 'Create your first agent',
      'reactorUniverse.unavailableTitle': 'Agent roles unavailable',
      'reactorUniverse.unavailableDescription': 'The list could not be verified.',
      'reactorUniverse.openHealth': 'Open status',
      'reactorUniverse.recoveryGuideTitle': 'Recovery steps',
      'reactorUniverse.recoveryCheckAccount': 'Check account access.',
      'reactorUniverse.recoveryCheckStatus': 'Check Reactor status.',
      'reactorUniverse.recoveryRetry': 'Retry after recovery.',
      'reactorUniverse.technicalError': 'Technical detail',
      'reactorUniverse.deleted': 'Deleted',
      'reactorUniverse.statusLabel': 'Current state',
      'reactorUniverse.answerMode': 'Answer mode',
      'reactorUniverse.questionCriteria': 'Question criteria',
      'reactorUniverse.connectedFeatures': 'Connected features',
      'reactorUniverse.startUsing': 'Start using',
      'reactorUniverse.stopUsing': 'Stop using',
      'reactorUniverse.technicalDetails': 'Technical role information',
      'reactorUniverse.agentIdentifier': 'Role identifier',
      'reactorUniverse.deleteTitle': 'Delete role',
      'reactorUniverse.deleteConfirm': 'Delete {{name}}?',
      'reactorUniverse.toolCount': '{{count}} tools',
      'reactorUniverse.directoryLabel': 'Registered agents',
      'reactorUniverse.noDescription': 'No description',
      'reactorUniverse.noKeywords': 'No routing keywords',
      'reactorUniverse.moreKeywords': '{{count}} more',
      'reactorUniverse.columns.agent': 'Agent',
      'reactorUniverse.columns.routing': 'Routing keywords',
      'reactorUniverse.columns.runtime': 'Runtime',
      'reactorUniverse.columns.actions': 'Actions',
      'reactorUniverse.status.enabled': 'Enabled',
      'reactorUniverse.status.disabled': 'Disabled',
      'reactorUniverse.modes.unknown': 'Answer mode needs review',
      'reactorUniverse.guide.disclosure': 'How it works and example',
      'reactorUniverse.guide.step1Title': '1. Register',
      'reactorUniverse.guide.step1Body': 'Define expertise and tools.',
      'reactorUniverse.guide.step2Title': '2. Route',
      'reactorUniverse.guide.step2Body': 'Delegate to the best agent.',
      'reactorUniverse.guide.step3Title': '3. Combine',
      'reactorUniverse.guide.step3Body': 'Combine the result.',
      'reactorUniverse.guide.exampleTitle': 'Example',
      'reactorUniverse.guide.exampleName': 'Example agent',
      'reactorUniverse.guide.exampleBody': 'Handles people questions.',
      'common.edit': 'Edit',
      'common.delete': 'Delete',
    },
    true,
    true,
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ReactorUniverseManager — CTA dedup', () => {
  it('hides the top-right Add Agent button when the agents list is empty', async () => {
    listAgentSpecsMock.mockResolvedValue([])
    render(<MemoryRouter><ReactorUniverseManager /></MemoryRouter>)

    // Wait for the empty-state center CTA to appear.
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Create your first agent/i }),
      ).toBeInTheDocument()
    })

    // Top-right Add Agent CTA must be absent on empty state.
    expect(
      screen.queryByRole('button', { name: /^Add Agent$/i }),
    ).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Create your first agent/i })).toHaveLength(1)
  })

  it('keeps onboarding guidance collapsed and returns to the empty state after cancelling creation', async () => {
    listAgentSpecsMock.mockResolvedValue([])
    render(<ReactorUniverseManager />)
    await screen.findByText('No agents yet')

    expect(screen.getByText('Example agent')).not.toBeVisible()
    fireEvent.click(screen.getByText('How it works and example'))
    expect(screen.getByText('Example agent')).toBeVisible()

    fireEvent.click(screen.getByRole('button', { name: /Create your first agent/i }))
    expect(screen.getByRole('dialog', { name: 'Agent editor' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel editor' }))
    expect(screen.queryByRole('dialog', { name: 'Agent editor' })).not.toBeInTheDocument()
    expect(screen.getByText('No agents yet')).toBeInTheDocument()
  })

  it('shows the top-right Add Agent button when there is at least one agent', async () => {
    listAgentSpecsMock.mockResolvedValue([buildAgent()])
    render(<ReactorUniverseManager />)

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /^Add Agent$/i }),
      ).toBeInTheDocument()
    })

    // The "Create your first agent" center CTA should NOT be shown for populated state.
    expect(
      screen.queryByRole('button', { name: /Create your first agent/i }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Registered agents' })).toBeInTheDocument()
    expect(screen.getByText('Answer mode needs review')).toBeInTheDocument()
    expect(screen.queryByText('SPECIALIST')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('moves role changes into the selected detail', async () => {
    listAgentSpecsMock.mockResolvedValue([buildAgent({ mode: 'REACT' })])
    render(<ReactorUniverseManager />)

    await screen.findByText('Test Agent')
    fireEvent.click(screen.getByRole('button', { name: /Test Agent/i }))

    expect(screen.getByText('Current state')).toBeInTheDocument()
    expect(screen.getByText('Connected features')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Stop using' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    const technical = screen.getByText('Technical role information').closest('details')
    expect(technical).not.toHaveAttribute('open')
  })

  it('fails closed instead of rendering an empty directory when loading fails', async () => {
    listAgentSpecsMock.mockRejectedValueOnce(new Error('admin access required'))
    render(<MemoryRouter><ReactorUniverseManager /></MemoryRouter>)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Agent roles unavailable')
    expect(screen.queryByText('No agents yet')).toBeNull()
    expect(screen.queryByRole('button', { name: /Create your first agent/i })).toBeNull()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open status' })).toHaveAttribute('href', '/health')
  })
})

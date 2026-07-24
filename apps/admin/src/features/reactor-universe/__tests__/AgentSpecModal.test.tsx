import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render as rtlRender, screen, waitFor } from '@testing-library/react'
import { i18n } from '../../../test/utils'
import { I18nextProvider } from 'react-i18next'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'

import { AgentSpecModal } from '../ui/AgentSpecModal'
import type { AgentSpec } from '../types'
import * as agentApi from '../api'
import { queryKeys } from '../../../shared/lib/queryKeys'

vi.mock('../api', () => ({
  listAgentSpecs: vi.fn(),
  deleteAgentSpec: vi.fn(),
  updateAgentSpec: vi.fn(),
  createAgentSpec: vi.fn(),
  getAgentSpec: vi.fn(),
  getAgentSpecSystemPrompt: vi.fn(),
}))

function buildAgent(overrides: Partial<AgentSpec> = {}): AgentSpec {
  return {
    id: 'spec-1',
    name: 'Existing agent',
    description: 'desc',
    mode: 'REACT',
    systemPromptPreview: 'You are an agent.',
    hasSystemPrompt: true,
    independentExecution: true,
    keywords: ['k1'],
    toolNames: ['t1'],
    enabled: true,
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-01T00:00:00Z',
    ...overrides,
  }
}

function renderWithClient(ui: ReactElement, client: QueryClient) {
  return rtlRender(
    <QueryClientProvider client={client}>
      <I18nextProvider i18n={i18n}>{ui}</I18nextProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  i18n.addResourceBundle(
    'en',
    'translation',
    {
      'reactorUniverse.title': 'Reactor Universe',
      'reactorUniverse.editAgent': 'Edit agent',
      'reactorUniverse.createAgent': 'Add Agent',
      'reactorUniverse.updated': 'Updated',
      'reactorUniverse.created': 'Created',
      'reactorUniverse.saveUnavailable': 'Unable to save the role.',
      'reactorUniverse.form.name': 'Name',
      'reactorUniverse.form.namePlaceholder': 'name',
      'reactorUniverse.form.description': 'Description',
      'reactorUniverse.form.descriptionPlaceholder': 'desc',
      'reactorUniverse.form.keywords': 'Keywords',
      'reactorUniverse.form.keywordsPlaceholder': 'kw',
      'reactorUniverse.form.keywordsHint': 'comma sep',
      'reactorUniverse.form.toolNames': 'Tools',
      'reactorUniverse.form.toolNamesPlaceholder': 'tools',
      'reactorUniverse.form.toolNamesHint': 'comma sep tools',
      'reactorUniverse.form.systemPrompt': 'System prompt override',
      'reactorUniverse.form.systemPromptPlaceholder': 'sp placeholder',
      'reactorUniverse.form.mode': 'Mode',
      'reactorUniverse.form.enabled': 'Enabled',
      'reactorUniverse.systemPrompt.toggle': 'Reveal system prompt',
      'reactorUniverse.systemPrompt.regionLabel': 'System prompt body',
      'reactorUniverse.systemPrompt.refresh': 'Refresh',
      'reactorUniverse.systemPrompt.auditPillLabel': 'Logged to admin audit',
      'reactorUniverse.systemPrompt.auditPillTooltip': 'tooltip',
      'reactorUniverse.systemPrompt.auditPillAriaLabel': 'aria',
      'reactorUniverse.systemPrompt.loading': 'Loading…',
      'reactorUniverse.systemPrompt.error': 'Failed.',
      'reactorUniverse.systemPrompt.errorRetry': 'Retry',
      'reactorUniverse.systemPrompt.copyButtonLabel': 'system prompt',
      'reactorUniverse.systemPrompt.copiedAnnouncement': 'copied',
      'reactorUniverse.systemPrompt.refreshAnnouncement': 'refreshed',
      'reactorUniverse.systemPrompt.empty': 'No system prompt.',
      'common.cancel': 'Cancel',
      'common.save': 'Save',
      'common.copy.defaultLabel': 'value',
      'common.copy.aria': 'Copy {{label}}',
      'common.aria.loading': 'Loading',
      'common.validation.required': 'Required',
      'common.validation.maxLength': 'Max {{max}} characters',
      'common.errors.serverError': 'Server error',
    },
    true,
    true,
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AgentSpecModal — system prompt section', () => {
  it('shows the system prompt section in edit mode', () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    renderWithClient(
      <AgentSpecModal agent={buildAgent()} onClose={() => {}} />,
      client,
    )
    const disclosure = screen
      .getByText(/reveal system prompt/i)
      .closest('details')

    expect(disclosure).toBeInTheDocument()
    expect(disclosure).not.toHaveAttribute('open')
    expect(screen.queryByLabelText(/system prompt override/i)).not.toBeInTheDocument()
  })

  it('does NOT render the system prompt section in create mode', () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    renderWithClient(<AgentSpecModal agent={null} onClose={() => {}} />, client)
    expect(screen.queryByText(/reveal system prompt/i)).not.toBeInTheDocument()
    expect(screen.getByLabelText(/system prompt override/i)).toBeInTheDocument()
  })

  it('invalidates the system-prompt cache after a successful spec update', async () => {
    vi.spyOn(agentApi, 'updateAgentSpec').mockResolvedValue(buildAgent())
    const onClose = vi.fn()
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    // Pre-populate the system-prompt cache so we can observe invalidation.
    client.setQueryData(queryKeys.reactorUniverse.systemPrompt('spec-1'), {
      systemPrompt: 'old',
    })
    expect(
      client.getQueryState(queryKeys.reactorUniverse.systemPrompt('spec-1'))
        ?.isInvalidated,
    ).toBe(false)

    const user = userEvent.setup()
    renderWithClient(
      <AgentSpecModal agent={buildAgent()} onClose={onClose} />,
      client,
    )

    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(onClose).toHaveBeenCalled())
    expect(agentApi.updateAgentSpec).toHaveBeenCalledWith('spec-1', {
      name: 'Existing agent',
      description: 'desc',
      toolNames: ['t1'],
      keywords: ['k1'],
      mode: 'REACT',
      enabled: true,
    })
    // After the update mutation resolves, the system-prompt query must be
    // marked invalidated so a subsequent reveal re-fetches and re-logs audit.
    expect(
      client.getQueryState(queryKeys.reactorUniverse.systemPrompt('spec-1'))
        ?.isInvalidated,
    ).toBe(true)
  })
})

describe('AgentSpecModal — zod validation + ARIA', () => {
  it('blocks submit and surfaces required-field error with ARIA wiring on empty name', async () => {
    const createSpy = vi.spyOn(agentApi, 'createAgentSpec').mockResolvedValue(buildAgent())
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const user = userEvent.setup()
    renderWithClient(<AgentSpecModal agent={null} onClose={() => {}} />, client)

    // Submit without filling name (required)
    await user.click(screen.getByRole('button', { name: /add agent/i }))

    const nameInput = screen.getByLabelText(/^name$/i) as HTMLInputElement
    await waitFor(() => {
      expect(nameInput).toHaveAttribute('aria-invalid', 'true')
    })
    expect(nameInput).toHaveAttribute('aria-describedby', 'agent-spec-name-error')

    const errorEl = document.getElementById('agent-spec-name-error')
    expect(errorEl).not.toBeNull()
    expect(errorEl).toHaveAttribute('role', 'alert')
    // Zod emits SOME validation message for the empty name; we don't pin to a
    // specific i18n string here because the schema captures the message at
    // module-init time, before test resource bundles are loaded.
    expect(errorEl?.textContent?.length ?? 0).toBeGreaterThan(0)

    // Mutation must NOT have been called because zod blocked submit
    expect(createSpy).not.toHaveBeenCalled()
  })

  it('keeps a mutation failure readable and its raw cause closed', async () => {
    vi.spyOn(agentApi, 'updateAgentSpec').mockRejectedValue(new Error('boom'))
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const user = userEvent.setup()
    renderWithClient(
      <AgentSpecModal agent={buildAgent()} onClose={() => {}} />,
      client,
    )

    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => {
      const root = document.getElementById('agent-spec-form-error')
      expect(root).not.toBeNull()
      expect(root).toHaveTextContent('Unable to save the role.')
      expect(root?.querySelector('details')).not.toHaveAttribute('open')
    })
  })
})

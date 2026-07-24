import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, i18n } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'

import { SystemPromptSection } from '../ui/SystemPromptSection'
import * as agentApi from '../api'

beforeEach(() => {
  i18n.addResourceBundle(
    'en',
    'translation',
    {
      'reactorUniverse.systemPrompt.toggle': 'Reveal system prompt',
      'reactorUniverse.systemPrompt.regionLabel': 'System prompt body',
      'reactorUniverse.systemPrompt.refresh': 'Refresh',
      'reactorUniverse.systemPrompt.auditPillLabel': 'Logged to admin audit',
      'reactorUniverse.systemPrompt.auditPillTooltip':
        'Each expand/refresh writes an admin audit log entry.',
      'reactorUniverse.systemPrompt.auditPillAriaLabel':
        'This action is logged to the admin audit',
      'reactorUniverse.systemPrompt.loading': 'Loading…',
      'reactorUniverse.systemPrompt.error': 'Failed to load system prompt.',
      'reactorUniverse.systemPrompt.errorRetry': 'Retry',
      'reactorUniverse.systemPrompt.copyButtonLabel': 'system prompt',
      'reactorUniverse.systemPrompt.copiedAnnouncement':
        'System prompt copied to clipboard.',
      'reactorUniverse.systemPrompt.refreshAnnouncement':
        'System prompt re-fetched.',
      'reactorUniverse.systemPrompt.empty':
        'This agent has no system prompt configured.',
      'common.copy.defaultLabel': 'value',
      'common.copy.aria': 'Copy {{label}}',
      'common.aria.loading': 'Loading',
    },
    true,
    true,
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

function getSystemPromptDisclosure() {
  const disclosure = screen
    .getByText(/reveal system prompt/i)
    .closest('details')

  if (!(disclosure instanceof HTMLDetailsElement)) {
    throw new Error('System prompt disclosure is missing')
  }

  return disclosure
}

function getSystemPromptToggle() {
  const summary = screen
    .getByText(/reveal system prompt/i)
    .closest('summary')

  if (!(summary instanceof HTMLElement)) {
    throw new Error('System prompt disclosure toggle is missing')
  }

  return summary
}

describe('SystemPromptSection — initial render', () => {
  it('renders collapsed by default as a native disclosure', () => {
    renderWithClient(<SystemPromptSection specId="spec-1" />)
    expect(getSystemPromptDisclosure()).not.toHaveAttribute('open')
    expect(screen.queryByText(/you are an agent/i)).not.toBeInTheDocument()
  })

  it('shows the audit pill near the heading', () => {
    renderWithClient(<SystemPromptSection specId="spec-1" />)
    expect(screen.getByText(/logged to admin audit/i)).toBeInTheDocument()
  })

  it('does NOT call the API before the user expands the section', () => {
    const spy = vi
      .spyOn(agentApi, 'getAgentSpecSystemPrompt')
      .mockResolvedValue({ systemPrompt: 'unused' })
    renderWithClient(<SystemPromptSection specId="spec-1" />)
    expect(spy).not.toHaveBeenCalled()
  })
})

describe('SystemPromptSection — fetch and display', () => {
  it('fetches on first expand and shows the prompt body', async () => {
    const spy = vi
      .spyOn(agentApi, 'getAgentSpecSystemPrompt')
      .mockResolvedValue({ systemPrompt: 'YOU ARE AN AGENT' })
    const user = userEvent.setup()
    renderWithClient(<SystemPromptSection specId="spec-99" />)

    await user.click(getSystemPromptToggle())

    await waitFor(() =>
      expect(screen.getByText(/YOU ARE AN AGENT/)).toBeInTheDocument(),
    )
    expect(spy).toHaveBeenCalledWith('spec-99')
  })

  it('does NOT re-fetch when collapsed and re-expanded (staleTime: Infinity)', async () => {
    const spy = vi
      .spyOn(agentApi, 'getAgentSpecSystemPrompt')
      .mockResolvedValue({ systemPrompt: 'PROMPT' })
    const user = userEvent.setup()
    renderWithClient(<SystemPromptSection specId="spec-cache" />)

    const toggle = getSystemPromptToggle()
    await user.click(toggle) // expand
    await waitFor(() =>
      expect(screen.getByText('PROMPT')).toBeInTheDocument(),
    )
    await user.click(toggle) // collapse
    await user.click(toggle) // expand again

    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('renders prompt body with role="region" and tabIndex 0 for keyboard scroll', async () => {
    vi.spyOn(agentApi, 'getAgentSpecSystemPrompt').mockResolvedValue({
      systemPrompt: 'long prompt content',
    })
    const user = userEvent.setup()
    renderWithClient(<SystemPromptSection specId="spec-a11y" />)

    await user.click(getSystemPromptToggle())

    const region = await screen.findByRole('region', {
      name: /system prompt body/i,
    })
    expect(region).toHaveAttribute('tabindex', '0')
    expect(region.tagName).toBe('DIV')
  })

  it('shows an empty-state message when the agent has no system prompt', async () => {
    vi.spyOn(agentApi, 'getAgentSpecSystemPrompt').mockResolvedValue({
      systemPrompt: '',
    })
    const user = userEvent.setup()
    renderWithClient(<SystemPromptSection specId="spec-empty" />)

    await user.click(getSystemPromptToggle())

    await waitFor(() =>
      expect(
        screen.getByText(/no system prompt configured/i),
      ).toBeInTheDocument(),
    )
  })
})

describe('SystemPromptSection — refresh + error', () => {
  it('refresh button explicitly re-fetches', async () => {
    const spy = vi
      .spyOn(agentApi, 'getAgentSpecSystemPrompt')
      .mockResolvedValue({ systemPrompt: 'PROMPT' })
    const user = userEvent.setup()
    renderWithClient(<SystemPromptSection specId="spec-refresh" />)

    await user.click(getSystemPromptToggle())
    await waitFor(() =>
      expect(screen.getByText('PROMPT')).toBeInTheDocument(),
    )

    await user.click(screen.getByRole('button', { name: /^refresh$/i }))

    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
  })

  it('shows error UI with retry when the API fails', async () => {
    vi.spyOn(agentApi, 'getAgentSpecSystemPrompt').mockRejectedValue(
      new Error('boom'),
    )
    const user = userEvent.setup()
    renderWithClient(<SystemPromptSection specId="spec-fail" />)

    await user.click(getSystemPromptToggle())

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        /failed to load system prompt/i,
      ),
    )
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
  })
})

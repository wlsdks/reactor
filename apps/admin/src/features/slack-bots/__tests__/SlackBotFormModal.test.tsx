import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { i18n } from '../../../test/utils'
import { SlackBotFormModal } from '../ui/SlackBotFormModal'

// Mock the API so the component never hits MSW
vi.mock('../api', () => ({
  createSlackBot: vi.fn(),
  updateSlackBot: vi.fn(),
}))

beforeEach(() => {
  i18n.addResourceBundle('en', 'translation', {
    'common.name': 'Name',
    'common.description': 'Description',
    'common.cancel': 'Cancel',
    'common.save': 'Save',
    'common.active': 'Active',
    'slackBotsTab.addBot': 'Add Bot',
    'slackBotsTab.editBot': 'Edit Bot',
    'slackBotsTab.workspace': 'Workspace',
    'slackBotsTab.botToken': 'Bot Token',
    'slackBotsTab.appToken': 'App Token',
    'slackBotsTab.signingSecret': 'Signing Secret',
    'slackBotsTab.tokenPlaceholder': 'Leave empty to keep existing',
    'slackBotsTab.created': 'Created',
    'slackBotsTab.updated': 'Updated',
    'slackBotsTab.hint.name': 'Bot display name',
    'slackBotsTab.hint.workspace': 'Slack workspace ID',
    'slackBotsTab.hint.botToken': 'xoxb- token',
    'slackBotsTab.hint.appToken': 'xapp- token',
    'slackBotsTab.hint.signingSecret': 'Signing secret',
  }, true, true)
})

describe('SlackBotFormModal — real-time validation', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders required asterisks and aria-required for name + workspace', async () => {
    render(<SlackBotFormModal bot={null} onClose={vi.fn()} />)
    await act(async () => undefined)
    const nameInput = screen.getByLabelText(/^Name/)
    const workspaceInput = screen.getByLabelText(/^Workspace/)
    expect(nameInput).toHaveAttribute('aria-required', 'true')
    expect(workspaceInput).toHaveAttribute('aria-required', 'true')
  })

  it('exposes technical field explanations through help controls', async () => {
    render(<SlackBotFormModal bot={null} onClose={vi.fn()} />)
    await act(async () => undefined)
    expect(screen.getByRole('button', { name: 'Bot display name' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Slack workspace ID' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'xoxb- token' })).toBeInTheDocument()
  })

  it('shows valid (✓) indicator after typing a valid value past the debounce window', async () => {
    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) })
    render(<SlackBotFormModal bot={null} onClose={vi.fn()} />)

    const nameInput = screen.getByLabelText(/^Name/)
    await user.type(nameInput, 'helpdesk-bot')

    await act(async () => {
      vi.advanceTimersByTime(260)
    })

    await waitFor(() => {
      // The valid indicator is rendered as a span with role="status" labelled "Valid"
      const validIndicators = screen.getAllByLabelText('Valid')
      expect(validIndicators.length).toBeGreaterThan(0)
    })
  })

  it('submit button stays disabled until all required fields are valid', async () => {
    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) })
    render(<SlackBotFormModal bot={null} onClose={vi.fn()} />)

    const submit = screen.getByRole('button', { name: /Add Bot/i })
    expect(submit).toBeDisabled()

    await user.type(screen.getByLabelText(/^Name/), 'name')
    await user.type(screen.getByLabelText(/^Workspace/), 'ws')
    await user.type(screen.getByLabelText(/^Bot Token/), 'xoxb-x')
    await user.type(screen.getByLabelText(/^App Token/), 'xapp-x')
    await user.type(screen.getByLabelText(/^Signing Secret/), 'secret')

    await act(async () => { vi.advanceTimersByTime(300) })

    await waitFor(() => expect(submit).not.toBeDisabled())
  })
})

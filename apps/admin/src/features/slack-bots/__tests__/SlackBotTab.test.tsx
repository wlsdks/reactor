import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { fireEvent, render, screen, waitFor } from '../../../test/utils'
import { SlackBotTab } from '../ui/SlackBotTab'
import * as api from '../api'
import type { SlackBot } from '../types'

vi.mock('../api')
vi.mock('../ui/SlackBotFormModal', () => ({
  SlackBotFormModal: ({ onClose, bot }: { onClose: () => void; bot: SlackBot | null }) => (
    <div role="dialog" aria-label="form-modal">
      <span>{bot ? `editing ${bot.name}` : 'creating'}</span>
      <button onClick={onClose}>close form</button>
    </div>
  ),
}))

const sampleBots: SlackBot[] = [
  {
    id: 'bot-1',
    name: 'Jarvis 운영 봇',
    botToken: null,
    appToken: null,
    signingSecret: null,
    workspace: 'Reactor 운영 워크스페이스',
    description: '운영 알림과 관리자 명령을 처리합니다.',
    isActive: true,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-07-12T00:00:00Z',
  },
  {
    id: 'bot-2',
    name: '시험용 봇',
    botToken: null,
    appToken: null,
    signingSecret: null,
    workspace: '개발 시험 워크스페이스',
    description: null,
    isActive: false,
    createdAt: '2026-01-02T00:00:00Z',
    updatedAt: '2026-07-10T00:00:00Z',
  },
]

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderSlackBotTab(initialEntry = '/integrations?tab=bots') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <SlackBotTab />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('SlackBotTab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.listSlackBots).mockResolvedValue([...sampleBots])
    vi.mocked(api.deleteSlackBot).mockResolvedValue(undefined)
  })

  it('renders the operator-facing connection workspace', async () => {
    renderSlackBotTab()

    expect(screen.getByText('slackBotsTab.title')).toBeInTheDocument()
    expect(await screen.findByText('Jarvis 운영 봇')).toBeInTheDocument()
    expect(screen.getByText('Reactor 운영 워크스페이스')).toBeInTheDocument()
    expect(screen.getByText('slackBotsTab.statusActive')).toBeInTheDocument()
    expect(screen.getByText('slackBotsTab.statusInactive')).toBeInTheDocument()
  })

  it('does not expose edit or delete icon clusters in list rows', async () => {
    renderSlackBotTab()
    await screen.findByText('Jarvis 운영 봇')

    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('opens a URL-addressable connection detail drawer', async () => {
    renderSlackBotTab()
    fireEvent.click(await screen.findByText('Jarvis 운영 봇'))

    expect(await screen.findByRole('dialog', { name: 'Jarvis 운영 봇' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/integrations?tab=bots&bot=bot-1')
    expect(screen.getByText('slackBotsTab.statusActiveDescription')).toBeInTheDocument()
  })

  it('opens create form from URL state', async () => {
    renderSlackBotTab('/integrations?tab=bots&botAction=create')

    expect(await screen.findByRole('dialog', { name: 'form-modal' })).toHaveTextContent('creating')
  })

  it('opens edit form for the selected connection', async () => {
    const user = userEvent.setup()
    renderSlackBotTab('/integrations?tab=bots&bot=bot-1')
    await screen.findByRole('dialog', { name: 'Jarvis 운영 봇' })

    await user.click(screen.getByRole('button', { name: 'slackBotsTab.editSettings' }))

    expect(await screen.findByRole('dialog', { name: 'form-modal' })).toHaveTextContent('editing Jarvis 운영 봇')
    expect(screen.getByTestId('location')).toHaveTextContent('/integrations?tab=bots&bot=bot-1&botAction=edit')
  })

  it('uses one creation action and no placeholder detail for an empty list', async () => {
    vi.mocked(api.listSlackBots).mockResolvedValue([])
    renderSlackBotTab()

    expect(await screen.findByText('slackBotsTab.empty')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'slackBotsTab.addBot' })).toHaveLength(1)
    expect(screen.queryByText('slackBotsTab.detailsTitle')).not.toBeInTheDocument()
  })

  it('fails closed with retry and technical details when loading fails', async () => {
    vi.mocked(api.listSlackBots).mockRejectedValueOnce(new Error('HTTP 503'))
    renderSlackBotTab()

    expect(await screen.findByText('slackBotsTab.loadErrorTitle')).toBeInTheDocument()
    expect(screen.queryByText('slackBotsTab.empty')).not.toBeInTheDocument()
    expect(screen.getByText('HTTP 503')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await waitFor(() => expect(api.listSlackBots).toHaveBeenCalledTimes(2))
  })

  it('requires typed connection-name confirmation before deletion', async () => {
    const user = userEvent.setup()
    renderSlackBotTab('/integrations?tab=bots&bot=bot-1')
    await screen.findByRole('dialog', { name: 'Jarvis 운영 봇' })

    await user.click(screen.getByText('slackBotsTab.maintenanceTitle'))
    await user.click(screen.getByRole('button', { name: 'slackBotsTab.deleteConnection' }))
    const confirmButton = screen.getByRole('button', { name: 'Confirm' })
    expect(confirmButton).toBeDisabled()

    await user.type(screen.getByLabelText(/slackBotsTab.confirmDeleteLabel/), 'Jarvis 운영 봇')
    expect(confirmButton).toBeEnabled()
    await user.click(confirmButton)

    await waitFor(() => expect(api.deleteSlackBot).toHaveBeenCalledWith('bot-1', expect.anything()))
  })

  it('refreshes the connection list from the page action', async () => {
    renderSlackBotTab()
    await screen.findByText('Jarvis 운영 봇')

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => expect(api.listSlackBots).toHaveBeenCalledTimes(2))
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { fireEvent, render, screen, waitFor } from '../../../test/utils'
import { ProactiveChannelsManager } from '../ui/ProactiveChannelsManager'
import * as channelApi from '../api'
import type { ProactiveChannel } from '../types'

vi.mock('../api', () => ({
  listProactiveChannels: vi.fn(),
  addProactiveChannel: vi.fn(),
  removeProactiveChannel: vi.fn(),
}))

const listProactiveChannelsMock = vi.mocked(channelApi.listProactiveChannels)
const addProactiveChannelMock = vi.mocked(channelApi.addProactiveChannel)
const removeProactiveChannelMock = vi.mocked(channelApi.removeProactiveChannel)

function buildChannel(overrides: Partial<ProactiveChannel> = {}): ProactiveChannel {
  return {
    channelId: 'C0123456789',
    channelName: '#운영-알림',
    addedAt: 1710000000000,
    ...overrides,
  }
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderManager(initialEntry = '/integrations?tab=channels') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <ProactiveChannelsManager />
      <LocationProbe />
    </MemoryRouter>,
  )
}

describe('ProactiveChannelsManager', () => {
  beforeEach(() => {
    listProactiveChannelsMock.mockResolvedValue([
      buildChannel(),
      buildChannel({ channelId: 'C9876543210', channelName: '#서비스-소식', addedAt: 1710100000000 }),
    ])
    addProactiveChannelMock.mockImplementation(async request => ({
      channelId: request.channelId,
      channelName: request.channelName ?? null,
      addedAt: 1710200000000,
    }))
    removeProactiveChannelMock.mockResolvedValue()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders the operator-facing title and a single collection summary', async () => {
    renderManager()

    expect(screen.getByText('proactiveChannels.title')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/proactiveChannels.summary/)).toBeInTheDocument())
    expect(screen.queryByText('proactiveChannels.registeredChannels')).not.toBeInTheDocument()
    expect(screen.queryByText('proactiveChannels.selectChannel')).not.toBeInTheDocument()
  })

  it('shows channel identities without exposing destructive actions in the table', async () => {
    renderManager()

    await waitFor(() => expect(screen.getByText('#운영-알림')).toBeInTheDocument())
    expect(screen.getByText('C0123456789')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('opens channel details in a URL-addressable drawer while preserving the workspace tab', async () => {
    renderManager()
    await waitFor(() => expect(screen.getByText('#운영-알림')).toBeInTheDocument())

    fireEvent.click(screen.getByText('#운영-알림'))

    expect(await screen.findByRole('dialog', { name: '#운영-알림' })).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/integrations?tab=channels&channel=C0123456789',
    )
    expect(screen.getByText('proactiveChannels.deliveryEnabled')).toBeInTheDocument()
  })

  it('opens the add drawer from URL state', async () => {
    renderManager('/integrations?tab=channels&channelAction=add')

    expect(await screen.findByRole('dialog', { name: 'proactiveChannels.addTitle' })).toBeInTheDocument()
    expect(screen.getByLabelText('proactiveChannels.channelId')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'proactiveChannels.add' })).toBeDisabled()
  })

  it('validates a Slack channel ID before enabling registration', async () => {
    renderManager('/integrations?tab=channels&channelAction=add')
    const idInput = await screen.findByLabelText('proactiveChannels.channelId')
    const submit = screen.getByRole('button', { name: 'proactiveChannels.add' })

    fireEvent.change(idInput, { target: { value: 'general' } })
    expect(screen.getByText('proactiveChannels.channelIdInvalid')).toBeInTheDocument()
    expect(submit).toBeDisabled()

    fireEvent.change(idInput, { target: { value: 'c12345678' } })
    expect(submit).toBeEnabled()
  })

  it('normalizes and registers a valid channel, then selects it in URL state', async () => {
    renderManager('/integrations?tab=channels&channelAction=add')
    fireEvent.change(await screen.findByLabelText('proactiveChannels.channelId'), {
      target: { value: 'c12345678' },
    })
    fireEvent.change(screen.getByLabelText('proactiveChannels.channelName'), {
      target: { value: '  #긴급-알림  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'proactiveChannels.add' }))

    await waitFor(() => {
      expect(addProactiveChannelMock).toHaveBeenCalledWith(
        {
          channelId: 'C12345678',
          channelName: '#긴급-알림',
        },
        expect.anything(),
      )
    })
    expect(screen.getByTestId('location')).toHaveTextContent(
      '/integrations?tab=channels&channel=C12345678',
    )
  })

  it('uses one creation action and no detail placeholder for an empty collection', async () => {
    listProactiveChannelsMock.mockResolvedValueOnce([])
    renderManager()

    expect(await screen.findByText('proactiveChannels.empty')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'proactiveChannels.addAction' })).toHaveLength(1)
    expect(screen.queryByText('proactiveChannels.selectChannel')).not.toBeInTheDocument()
  })

  it('fails closed when the channel API is unavailable instead of showing an empty collection', async () => {
    listProactiveChannelsMock.mockRejectedValueOnce(new Error('HTTP 404'))
    renderManager()

    expect(await screen.findByText('proactiveChannels.loadErrorTitle')).toBeInTheDocument()
    expect(screen.queryByText('proactiveChannels.empty')).not.toBeInTheDocument()
    const recovery = screen.getByText('proactiveChannels.recoveryGuideTitle').closest('details')
    expect(recovery).not.toHaveAttribute('open')
  })

  it('retries the list request from the unavailable state', async () => {
    listProactiveChannelsMock.mockRejectedValueOnce(new Error('HTTP 500'))
    renderManager()
    await screen.findByText('proactiveChannels.loadErrorTitle')

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => expect(listProactiveChannelsMock).toHaveBeenCalledTimes(2))
  })

  it('keeps removal behind maintenance disclosure and typed confirmation', async () => {
    renderManager('/integrations?tab=channels&channel=C0123456789')
    await screen.findByRole('dialog', { name: '#운영-알림' })

    fireEvent.click(screen.getByText('proactiveChannels.maintenanceTitle'))
    fireEvent.click(screen.getByRole('button', { name: 'proactiveChannels.removeChannel' }))

    const confirmDialog = await screen.findByRole('dialog', { name: 'proactiveChannels.removeTitle' })
    const confirmButton = screen.getByRole('button', { name: 'Confirm' })
    expect(confirmDialog).toBeInTheDocument()
    expect(confirmButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/proactiveChannels.removeConfirmLabel/), {
      target: { value: 'C0123456789' },
    })
    expect(confirmButton).toBeEnabled()
    fireEvent.click(confirmButton)

    await waitFor(() => expect(removeProactiveChannelMock).toHaveBeenCalledWith('C0123456789'))
  })

  it('refreshes the collection from the page action', async () => {
    renderManager()
    await screen.findByText('#운영-알림')

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))

    await waitFor(() => expect(listProactiveChannelsMock).toHaveBeenCalledTimes(2))
  })
})

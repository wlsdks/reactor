import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { SessionInfoBar } from '../ui/Detail/SessionInfoBar'
import type { SessionDetailData } from '../types'

const mockSession: SessionDetailData = {
  sessionId: 'sess_test_a11y',
  userId: 'user_a11y',
  channel: 'web',
  personaId: null,
  personaName: null,
  model: null,
  messageCount: 5,
  duration: 60_000,
  startedAt: 1_700_000_000_000,
  lastActivity: 1_700_000_300_000,
  trust: 'clean',
  feedback: null,
  tags: [],
  messages: [],
}

function renderBar(overrides?: Partial<Parameters<typeof SessionInfoBar>[0]>) {
  const onExport = vi.fn()
  const onDelete = vi.fn()
  const onOpenInspector = vi.fn()
  const onFlag = vi.fn()

  const utils = render(
    <SessionInfoBar
      session={mockSession}
      onExport={onExport}
      onDelete={onDelete}
      onOpenInspector={onOpenInspector}
      onFlag={onFlag}
      {...overrides}
    />,
  )

  return { ...utils, onExport, onDelete, onOpenInspector, onFlag }
}

// Test i18n returns the key verbatim when no resource matches; that key text
// becomes the visible label and therefore the accessible name.
const FLAG_KEY = 'conversations.detail.flag'
const EXPORT_KEY = 'conversations.detail.export'
const OPEN_INSPECTOR_KEY = 'conversations.detail.openInspector'
const DELETE_KEY = 'conversations.detail.delete'
const MORE_KEY = 'conversations.detail.actions.more'

describe('SessionInfoBar a11y', () => {
  it('keeps destructive actions in a closed secondary-action disclosure', () => {
    const { container } = renderBar()

    expect(screen.getByRole('button', { name: OPEN_INSPECTOR_KEY })).toBeInTheDocument()
    expect(screen.getByText(MORE_KEY)).toBeInTheDocument()
    expect(container.querySelector('.session-info-bar__actions')).not.toHaveAttribute('open')
  })

  it('export trigger advertises menu state via aria-haspopup + aria-expanded', async () => {
    const user = userEvent.setup()
    renderBar()

    await user.click(screen.getByText(MORE_KEY))
    const trigger = screen.getByRole('button', {
      name: new RegExp(`^${EXPORT_KEY}`),
    })
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')

    await user.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')

    // The opened panel has role="menu" and is wired up via aria-controls.
    const menu = screen.getByRole('menu')
    expect(menu).toBeInTheDocument()
    expect(trigger).toHaveAttribute('aria-controls', menu.id)
  })

  it('clicking a menu item invokes onExport with the right format and restores focus', async () => {
    const user = userEvent.setup()
    const { onExport } = renderBar()

    await user.click(screen.getByText(MORE_KEY))
    const trigger = screen.getByRole('button', {
      name: new RegExp(`^${EXPORT_KEY}`),
    })
    await user.click(trigger)

    const items = screen.getAllByRole('menuitem')
    expect(items).toHaveLength(2)

    await user.click(items[0])
    expect(onExport).toHaveBeenCalledWith('json')
    // Menu closed and focus is back on the trigger.
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('Escape closes the export menu and returns focus to the trigger', async () => {
    const user = userEvent.setup()
    renderBar()

    await user.click(screen.getByText(MORE_KEY))
    const trigger = screen.getByRole('button', {
      name: new RegExp(`^${EXPORT_KEY}`),
    })
    await user.click(trigger)
    expect(screen.getByRole('menu')).toBeInTheDocument()

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('delete button invokes onDelete (parent owns the ConfirmDialog)', async () => {
    const user = userEvent.setup()
    const { onDelete } = renderBar()

    await user.click(screen.getByText(MORE_KEY))
    await user.click(screen.getByRole('button', { name: DELETE_KEY }))
    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  it('flag and open-inspector buttons invoke their handlers', async () => {
    const user = userEvent.setup()
    const { onFlag, onOpenInspector } = renderBar()

    await user.click(screen.getByText(MORE_KEY))
    await user.click(screen.getByRole('button', { name: FLAG_KEY }))
    expect(onFlag).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: OPEN_INSPECTOR_KEY }))
    expect(onOpenInspector).toHaveBeenCalledTimes(1)
  })
})

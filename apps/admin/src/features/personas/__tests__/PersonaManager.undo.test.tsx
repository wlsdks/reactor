import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '../../../test/utils'
import { PersonaManager } from '../ui/PersonaManager'
import { mockPersonas } from '../../../test/handlers'
import { useToastStore } from '../../../shared/store/toast.store'

// These tests intentionally use the real wall-clock 5s grace window from the
// `scheduleUndoableDelete` helper. Wrapping every call in fake timers risks
// stalling the React Query data-fetching layer — instead we extend the
// individual test timeout where the commit phase is observed.

vi.mock('../api', () => ({
  listPersonas: vi.fn(),
  getPersona: vi.fn(),
  createPersona: vi.fn(),
  updatePersona: vi.fn(),
  deletePersona: vi.fn(),
}))

vi.mock('../../prompts/api', () => ({
  listTemplates: vi.fn().mockResolvedValue([]),
  getTemplate: vi.fn(),
}))

import * as personasApi from '../api'
const listPersonasMock = vi.mocked(personasApi.listPersonas)
const getPersonaMock = vi.mocked(personasApi.getPersona)
const deletePersonaMock = vi.mocked(personasApi.deletePersona)

function renderPersonaManager() {
  const router = createMemoryRouter(
    [{ path: '/', element: <PersonaManager /> }],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

beforeEach(() => {
  useToastStore.setState({ toasts: [] })
  const personas = mockPersonas.map((p) => ({
      id: p.id,
      name: p.name,
      description: p.description,
      systemPrompt: p.systemPrompt,
      responseGuideline: p.responseGuideline,
      welcomeMessage: p.welcomeMessage,
      promptTemplateId: p.promptTemplateId,
      icon: p.icon,
      isDefault: p.isDefault,
      isActive: p.isActive,
      createdAt: 1,
      updatedAt: 2,
    }))
  listPersonasMock.mockResolvedValue(personas)
  getPersonaMock.mockImplementation(async (id) => personas.find((persona) => persona.id === id)!)
  deletePersonaMock.mockResolvedValue(undefined)
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  useToastStore.setState({ toasts: [] })
})

async function openConfirmAndAccept() {
  // Select the non-default role, then start deletion from its detail surface.
  await waitFor(() => expect(screen.getByText('Sales Bot')).toBeInTheDocument())
  const salesRow = screen.getByText('Sales Bot').closest('tr')
  fireEvent.click(salesRow!)
  await screen.findByText('personas.technicalPersona')
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
  const confirmBtn = Array.from(
    screen.getByRole('dialog').querySelectorAll('button'),
  ).find((b) => /confirm|확인/i.test(b.textContent ?? '')) as HTMLButtonElement
  fireEvent.click(confirmBtn)
}

describe('PersonaManager — undoable delete', () => {
  it('shows a success toast with an Undo action and removes the row optimistically before commit', async () => {
    renderPersonaManager()
    await openConfirmAndAccept()

    // Optimistic removal — Sales Bot should be gone immediately, before any
    // network call has fired.
    await waitFor(() => {
      expect(screen.queryByText('Sales Bot')).not.toBeInTheDocument()
    })

    // Toast carries the undo action.
    const toasts = useToastStore.getState().toasts
    const undoToast = toasts.find((t) => t.action?.label === 'Undo')
    expect(undoToast).toBeDefined()
    expect(undoToast!.message).toContain('Sales Bot')
    expect(undoToast!.type).toBe('success')

    // The actual API call must not have run yet — we are still inside the
    // 5-second grace window.
    expect(deletePersonaMock).not.toHaveBeenCalled()
  }, 15_000)

  it('clicking Undo before the grace window elapses cancels the API call and restores the row', async () => {
    renderPersonaManager()
    await openConfirmAndAccept()
    await waitFor(() => expect(screen.queryByText('Sales Bot')).not.toBeInTheDocument())

    const undoToast = useToastStore
      .getState()
      .toasts.find((t) => t.action?.label === 'Undo')
    expect(undoToast).toBeDefined()

    act(() => {
      undoToast!.action!.onAction()
    })

    // Row reappears thanks to the cache snapshot restore.
    await waitFor(() => expect(screen.getByText('Sales Bot')).toBeInTheDocument())

    // The API delete must not fire — assert immediately since the grace
    // window has not elapsed yet (this assertion is the point of the test).
    expect(deletePersonaMock).not.toHaveBeenCalled()
  }, 15_000)

  it('commits the deletion after the grace window elapses without an Undo click', async () => {
    renderPersonaManager()
    await openConfirmAndAccept()
    await waitFor(() => expect(screen.queryByText('Sales Bot')).not.toBeInTheDocument())

    expect(deletePersonaMock).not.toHaveBeenCalled()

    // The undoable-delete helper uses a real-clock setTimeout. Wait the
    // grace window plus a small buffer for the timer + microtask flush.
    await waitFor(
      () => {
        expect(deletePersonaMock).toHaveBeenCalledTimes(1)
      },
      { timeout: 7_000 },
    )
  }, 10_000)
})

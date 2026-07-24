import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '../../../test/utils'
import { PersonaManager } from '../ui/PersonaManager'
import { mockPersonas } from '../../../test/handlers'
import { ApiError } from '../../../shared/api/errors'
import { LiveAnnouncerProvider } from '../../../shared/ui/LiveAnnouncer'

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

function buildPersonaResponses() {
  return mockPersonas.map(p => ({
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
}

async function openPersonaDetail(name: string) {
  await screen.findByText(name)
  const row = screen.getByText(name).closest('tr')
  expect(row).not.toBeNull()
  fireEvent.click(row!)
  await screen.findByText('personas.technicalPersona')
}

function renderPersonaManager() {
  const router = createMemoryRouter(
    [{ path: '/', element: <PersonaManager /> }],
    { initialEntries: ['/'] },
  )
  return render(<RouterProvider router={router} />)
}

beforeEach(() => {
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  const personas = buildPersonaResponses()
  listPersonasMock.mockResolvedValue(personas)
  getPersonaMock.mockImplementation(async (id) => personas.find((persona) => persona.id === id)!)
  deletePersonaMock.mockResolvedValue(undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('PersonaManager', () => {
  it('shows loading spinner initially', () => {
    renderPersonaManager()
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
  })

  it('renders persona list after loading', async () => {
    const { container } = renderPersonaManager()
    await waitFor(() => {
      expect(screen.getByText('Support Bot')).toBeInTheDocument()
      expect(screen.getByText('Sales Bot')).toBeInTheDocument()
    })
    expect(screen.getByText('personas.listGuidance')).toBeInTheDocument()
    expect(container.querySelector('.split-layout--collapsed .personas-list')).toBeInTheDocument()
  })

  it('shows empty state when no personas', async () => {
    listPersonasMock.mockResolvedValueOnce([])
    renderPersonaManager()
    await waitFor(() => {
      expect(screen.queryByLabelText('Loading')).not.toBeInTheDocument()
    })
    expect(screen.queryByText('Support Bot')).not.toBeInTheDocument()
  })

  it('keeps one creation action and a collapsed example in the empty collection', async () => {
    listPersonasMock.mockResolvedValueOnce([])
    const { container } = renderPersonaManager()
    await waitFor(() => expect(screen.queryByLabelText('Loading')).not.toBeInTheDocument())

    const createButtons = screen.getAllByRole('button').filter((button) =>
      /Create Persona|페르소나 생성/.test(button.textContent ?? ''),
    )
    expect(createButtons).toHaveLength(1)
    expect(container.querySelectorAll('.stat-card')).toHaveLength(0)
    expect(container.querySelector('.personas-summary')).not.toBeInTheDocument()
    expect(container.querySelector('.empty-state')).not.toBeInTheDocument()
    expect(container.querySelector('.personas-empty__guide dl')).toBeInTheDocument()
    const disclosure = container.querySelector('.personas-empty__example') as HTMLDetailsElement
    expect(disclosure.open).toBe(false)
    expect(disclosure.querySelector('code')).not.toBeInTheDocument()
    expect(disclosure.querySelector('p')).toBeInTheDocument()
    fireEvent.click(disclosure.querySelector('summary') as HTMLElement)
    expect(disclosure.open).toBe(true)
  })

  it('gives each inline name editor a role-specific accessible action', async () => {
    renderPersonaManager()
    await screen.findByText('Support Bot')

    expect(screen.getAllByRole('button', { name: 'personas.renameName' })).toHaveLength(2)
    expect(screen.queryByRole('button', { name: 'Edit value' })).not.toBeInTheDocument()
  })

  it('keeps an unavailable persona list distinct from an empty collection and retries it', async () => {
    listPersonasMock.mockRejectedValueOnce(new ApiError(500, 'SERVER_ERROR', 'HTTP 500'))
    const { container } = renderPersonaManager()
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(container.querySelector('.personas-empty')).not.toBeInTheDocument()
    expect(container.querySelector('.split-layout')).not.toBeInTheDocument()
    const technicalDetails = screen.getByText(/HTTP 500/).closest('details')
    expect(technicalDetails).not.toHaveAttribute('open')

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    await waitFor(() => {
      expect(screen.getByText('Support Bot')).toBeInTheDocument()
    })
  })

  it('loads and shows persona detail when row clicked', async () => {
    renderPersonaManager()
    await openPersonaDetail('Support Bot')
    expect(screen.getByText('System Prompt')).toBeInTheDocument()
  })

  it('retains the persona list when the selected detail cannot load', async () => {
    getPersonaMock.mockRejectedValue(new Error('HTTP 503'))
    renderPersonaManager()
    await screen.findByText('Support Bot')

    const row = screen.getByText('Support Bot').closest('tr')
    fireEvent.click(row!)

    expect(await screen.findByText('personas.detailUnavailableTitle')).toBeInTheDocument()
    expect(screen.getByText('Sales Bot')).toBeInTheDocument()
    expect(screen.getByText('personas.technicalError').closest('details')).not.toHaveAttribute('open')
  })

  it('keeps mutations out of the persona table until a role is selected', async () => {
    const { container } = renderPersonaManager()
    await screen.findByText('Support Bot')
    expect(container.querySelector('.row-actions')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('renders create button', async () => {
    renderPersonaManager()
    await waitFor(() => expect(screen.queryByLabelText('Loading')).not.toBeInTheDocument())
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(0)
  })

  it('opens deletion confirmation from the selected role detail', async () => {
    renderPersonaManager()
    await openPersonaDetail('Sales Bot')

    const deleteBtn = screen.getByRole('button', { name: 'Delete' })
    expect(deleteBtn).not.toBeDisabled()
    fireEvent.click(deleteBtn)

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  it('keeps deletion unavailable for the default role in its selected detail', async () => {
    renderPersonaManager()
    await openPersonaDetail('Support Bot')
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
  })

  it('shows all personas from fixture data', async () => {
    renderPersonaManager()
    await waitFor(() => {
      mockPersonas.forEach(p => {
        expect(screen.getByText(p.name)).toBeInTheDocument()
      })
    })
  })

  it('opens role editing from the selected detail', async () => {
    renderPersonaManager()
    await openPersonaDetail('Sales Bot')
    fireEvent.click(screen.getByRole('button', { name: 'Edit' }))

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  it('opens form modal when create button is clicked', async () => {
    renderPersonaManager()
    await waitFor(() => expect(screen.queryByLabelText('Loading')).not.toBeInTheDocument())

    // Click the create button in the page header
    const createBtn = screen.getAllByRole('button').find(b =>
      b.textContent?.includes('Create Persona') || b.textContent?.includes('페르소나 생성'),
    )
    expect(createBtn).toBeDefined()
    if (createBtn) {
      fireEvent.click(createBtn)
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })
    }
  })

  it('posts a polite aria-live announcement when a persona is deleted', async () => {
    const router = createMemoryRouter(
      [{ path: '/', element: <PersonaManager /> }],
      { initialEntries: ['/'] },
    )
    render(
      <LiveAnnouncerProvider>
        <RouterProvider router={router} />
      </LiveAnnouncerProvider>,
    )

    await openPersonaDetail('Sales Bot')
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())

    // Confirm deletion — ConfirmDialog labels its confirm button with
    // `common.confirm`, not the row action text.
    const confirmBtn = Array.from(
      screen.getByRole('dialog').querySelectorAll('button'),
    ).find(b => /confirm|확인/i.test(b.textContent ?? '')) as HTMLButtonElement
    expect(confirmBtn).toBeDefined()
    fireEvent.click(confirmBtn)

    // Wait for the polite live region to announce the deletion.
    await waitFor(() => {
      const polite = screen.getByTestId('live-announcer-polite')
      expect(polite.textContent?.trim()).toContain('Deleted')
    })
  })

  it('renders the DataTable bulk-action bar and disables the default-persona checkbox', async () => {
    const { container } = renderPersonaManager()
    await waitFor(() => expect(screen.getByText('Sales Bot')).toBeInTheDocument())
    const checkboxes = container.querySelectorAll(
      '.data-table-select-cell input[type="checkbox"]',
    ) as NodeListOf<HTMLInputElement>
    expect(checkboxes.length).toBeGreaterThan(0)
    // The default persona has a disabled checkbox via `rowSelectable`.
    const defaultPersona = mockPersonas.find(p => p.isDefault)
    if (defaultPersona) {
      const row = screen.getByText(defaultPersona.name).closest('tr')
      const cb = row?.querySelector('.data-table-select-cell input[type="checkbox"]') as HTMLInputElement
      expect(cb.disabled).toBe(true)
    }
    // Selecting a non-default persona surfaces the bulk bar.
    const salesRow = screen.getByText('Sales Bot').closest('tr')
    const cb = salesRow?.querySelector('.data-table-select-cell input[type="checkbox"]') as HTMLInputElement
    fireEvent.click(cb)
    await waitFor(() => {
      expect(screen.getByText(/1 selected/)).toBeInTheDocument()
    })
    expect(
      screen.getByRole('button', { name: /Bulk activate/i }),
    ).toBeInTheDocument()
  })

  it('surfaces a localized error toast with retry action when delete fails (showApiErrorToast)', async () => {
    // Arrange: 500 from the delete endpoint should route through the new
    // shared helper and produce a toast with the localized server-error
    // message + a "다시 시도" recovery action. Note that with the undoable
    // delete pattern the API call only fires after the 5s grace window, so
    // we extend the waitFor timeout accordingly.
    const { useToastStore } = await import('../../../shared/store/toast.store')
    const before = useToastStore.getState().toasts.length
    deletePersonaMock.mockRejectedValueOnce(new ApiError(500, 'SERVER_ERROR', 'HTTP 500'))

    renderPersonaManager()
    await openPersonaDetail('Sales Bot')
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
    const confirmBtn = Array.from(
      screen.getByRole('dialog').querySelectorAll('button'),
    ).find(b => /confirm|확인/i.test(b.textContent ?? '')) as HTMLButtonElement
    fireEvent.click(confirmBtn)

    await waitFor(
      () => {
        const list = useToastStore.getState().toasts
        // The undoable success toast comes first; assert at least one toast
        // is present and find the error one.
        expect(list.length).toBeGreaterThan(before)
        const errorToast = list.find((t) => t.type === 'error')
        expect(errorToast).toBeDefined()
        expect(errorToast!.message).toBe('서버 오류가 발생했어요')
        expect(errorToast!.action?.label).toBe('다시 시도')
      },
      { timeout: 8000 },
    )
  }, 10_000)
})

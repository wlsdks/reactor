import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../../test/utils'
import { PersonaFormModal } from '../ui/PersonaFormModal'

vi.mock('../api', () => ({
  createPersona: vi.fn(),
  updatePersona: vi.fn(),
}))

vi.mock('../../prompts/api', () => ({
  listTemplates: vi.fn().mockResolvedValue([]),
}))

import * as personasApi from '../api'

const STORAGE_PREFIX = 'reactor-admin-draft:'
const CREATE_KEY = `${STORAGE_PREFIX}personas:create`

describe('PersonaFormModal — draft recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  afterEach(() => {
    window.localStorage.clear()
  })

  it('does not render the recovery banner when no draft exists', () => {
    render(<PersonaFormModal open={true} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(screen.queryByTestId('draft-recovery-banner')).not.toBeInTheDocument()
  })

  it('renders the recovery banner when a persisted draft exists', () => {
    window.localStorage.setItem(
      CREATE_KEY,
      JSON.stringify({
        values: { name: 'Recovered Bot', systemPrompt: 'You are recovered.' },
        savedAt: new Date().toISOString(),
      }),
    )

    render(<PersonaFormModal open={true} onClose={vi.fn()} onSaved={vi.fn()} />)
    expect(screen.getByTestId('draft-recovery-banner')).toBeInTheDocument()
  })

  it('applies the recovered draft to the form when accept is clicked', async () => {
    window.localStorage.setItem(
      CREATE_KEY,
      JSON.stringify({
        values: { name: 'Recovered Bot', systemPrompt: 'You are recovered.' },
        savedAt: new Date().toISOString(),
      }),
    )

    render(<PersonaFormModal open={true} onClose={vi.fn()} onSaved={vi.fn()} />)

    fireEvent.click(screen.getByTestId('draft-recovery-accept'))

    await waitFor(() => {
      const nameInput = screen.getByPlaceholderText(/name/i) as HTMLInputElement
      expect(nameInput.value).toBe('Recovered Bot')
    })

    // Banner is removed after acceptance.
    expect(screen.queryByTestId('draft-recovery-banner')).not.toBeInTheDocument()
  })

  it('clears the storage entry when dismiss is clicked', () => {
    window.localStorage.setItem(
      CREATE_KEY,
      JSON.stringify({
        values: { name: 'Stale', systemPrompt: 'old' },
        savedAt: new Date().toISOString(),
      }),
    )

    render(<PersonaFormModal open={true} onClose={vi.fn()} onSaved={vi.fn()} />)
    fireEvent.click(screen.getByTestId('draft-recovery-dismiss'))

    expect(window.localStorage.getItem(CREATE_KEY)).toBeNull()
    expect(screen.queryByTestId('draft-recovery-banner')).not.toBeInTheDocument()
  })

  it('clears the draft after a successful create', async () => {
    window.localStorage.setItem(
      CREATE_KEY,
      JSON.stringify({
        values: { name: 'Will be saved', systemPrompt: 'foo' },
        savedAt: new Date().toISOString(),
      }),
    )

    vi.mocked(personasApi.createPersona).mockResolvedValue({
      id: 'p-1',
      name: 'Submitted',
      systemPrompt: 'You are helpful.',
      isDefault: false,
      description: null,
      responseGuideline: null,
      welcomeMessage: null,
      promptTemplateId: null,
      icon: null,
      isActive: true,
      createdAt: 1,
      updatedAt: 2,
    })

    render(<PersonaFormModal open={true} onClose={vi.fn()} onSaved={vi.fn()} />)

    fireEvent.change(screen.getByPlaceholderText(/name/i), {
      target: { value: 'Submitted' },
    })
    const textareas = document.querySelectorAll('textarea')
    fireEvent.change(textareas[0], {
      target: { value: 'You are helpful.' },
    })

    fireEvent.click(screen.getByRole('button', { name: /create|생성/i }))

    await waitFor(() => {
      expect(window.localStorage.getItem(CREATE_KEY)).toBeNull()
    })
  })
})

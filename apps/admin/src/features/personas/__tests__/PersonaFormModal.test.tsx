import { render, screen, fireEvent, waitFor } from '../../../test/utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { PersonaFormModal } from '../ui/PersonaFormModal'
import type { PersonaResponse } from '../types'

vi.mock('../api', () => ({
  createPersona: vi.fn(),
  updatePersona: vi.fn(),
}))

vi.mock('../../prompts/api', () => ({
  listTemplates: vi.fn().mockResolvedValue([]),
}))

import * as personasApi from '../api'

const basePersona: PersonaResponse = {
  id: 'persona-1',
  name: 'Support Bot',
  systemPrompt: 'You are helpful.',
  isDefault: false,
  description: 'Support persona',
  responseGuideline: 'Be concise.',
  welcomeMessage: 'Hello!',
  promptTemplateId: null,
  icon: '\u{1F916}',
  isActive: true,
  createdAt: 1,
  updatedAt: 2,
}

describe('PersonaFormModal', () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    onSaved: vi.fn(),
    persona: null as PersonaResponse | null,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when closed', () => {
    const { container } = render(
      <PersonaFormModal open={false} onClose={vi.fn()} onSaved={vi.fn()} />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders create form when open with no persona', () => {
    render(<PersonaFormModal {...defaultProps} />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(document.getElementById('persona-name')).toBeInTheDocument()
    expect(document.getElementById('persona-system-prompt')).toBeInTheDocument()
    expect(document.querySelector('.emoji-picker')).not.toBeInTheDocument()
    expect(document.querySelector<HTMLDetailsElement>('.persona-form__optional')?.open).toBe(false)
  })

  it('shows validation errors on empty submit', async () => {
    render(<PersonaFormModal {...defaultProps} />)
    const submitBtn = screen.getByRole('button', { name: /create|생성/i })
    fireEvent.click(submitBtn)
    // Schema messages now go through i18n.t(); when running in unit test
    // environment without the global i18n initialized, zod falls back to its
    // default error. We assert the error element is rendered with non-empty text.
    await waitFor(() => {
      const errorEl = screen.getByText((_, el) =>
        el?.id === 'persona-name-error' && (el?.textContent ?? '').trim().length > 0,
      )
      expect(errorEl).toBeInTheDocument()
    })
  })

  it('calls onSaved on successful create', async () => {
    const created: PersonaResponse = {
      ...basePersona,
      id: '123',
      name: 'Test',
    }
    vi.mocked(personasApi.createPersona).mockResolvedValue(created)

    render(<PersonaFormModal {...defaultProps} />)

    fireEvent.change(screen.getByPlaceholderText(/name/i), {
      target: { value: 'Test Persona' },
    })
    const textareas = document.querySelectorAll('textarea')
    fireEvent.change(textareas[0], {
      target: { value: 'You are a test assistant' },
    })

    fireEvent.click(screen.getByRole('button', { name: /create|생성/i }))

    await waitFor(() => {
      expect(defaultProps.onSaved).toHaveBeenCalledWith(created)
    })
  })

  it('calls onClose when cancel is clicked', () => {
    render(<PersonaFormModal {...defaultProps} />)
    fireEvent.click(screen.getByRole('button', { name: /cancel|취소/i }))
    expect(defaultProps.onClose).toHaveBeenCalled()
  })

  it('renders edit form when persona is provided', () => {
    render(<PersonaFormModal {...defaultProps} persona={basePersona} />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    // Name should be pre-filled
    const nameInput = screen.getByPlaceholderText(/name/i) as HTMLInputElement
    expect(nameInput.value).toBe('Support Bot')
  })

  it('calls updatePersona in edit mode', async () => {
    const updated: PersonaResponse = { ...basePersona, name: 'Updated Bot' }
    vi.mocked(personasApi.updatePersona).mockResolvedValue(updated)

    render(<PersonaFormModal {...defaultProps} persona={basePersona} />)

    fireEvent.change(screen.getByPlaceholderText(/name/i), {
      target: { value: 'Updated Bot' },
    })

    fireEvent.click(screen.getByRole('button', { name: /save|저장/i }))

    await waitFor(() => {
      expect(personasApi.updatePersona).toHaveBeenCalledWith(
        'persona-1',
        expect.objectContaining({ name: 'Updated Bot' }),
      )
      expect(defaultProps.onSaved).toHaveBeenCalledWith(updated)
    })
  })
})

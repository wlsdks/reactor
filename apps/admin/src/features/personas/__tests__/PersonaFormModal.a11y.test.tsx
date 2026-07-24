import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, waitFor } from '../../../test/utils'
import { PersonaFormModal } from '../ui/PersonaFormModal'

vi.mock('../api', () => ({
  createPersona: vi.fn(),
  updatePersona: vi.fn(),
}))

vi.mock('../../prompts/api', () => ({
  listTemplates: vi.fn().mockResolvedValue([]),
}))

const defaultProps = {
  open: true,
  onClose: vi.fn(),
  onSaved: vi.fn(),
  persona: null,
}

describe('PersonaFormModal — form a11y', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('marks Name and System Prompt as required', () => {
    render(<PersonaFormModal {...defaultProps} />)

    const nameInput = document.getElementById('persona-name')
    expect(nameInput?.getAttribute('aria-required')).toBe('true')

    const systemPromptInput = document.getElementById('persona-system-prompt')
    expect(systemPromptInput?.getAttribute('aria-required')).toBe('true')
  })

  it('autofocuses the Name input when the modal opens', async () => {
    render(<PersonaFormModal {...defaultProps} />)

    const nameInput = document.getElementById('persona-name') as HTMLInputElement
    await waitFor(() => {
      expect(document.activeElement).toBe(nameInput)
    })
  })

  it('System Prompt initially describes itself by hint, switches to error on submit-empty', async () => {
    render(<PersonaFormModal {...defaultProps} />)

    const systemPromptInput = document.getElementById('persona-system-prompt') as HTMLTextAreaElement
    expect(systemPromptInput.getAttribute('aria-invalid')).toBe('false')
    // hint should be referenced when no error
    expect(systemPromptInput.getAttribute('aria-describedby')).toBe('persona-systemPrompt-hint')

    // Type then clear to trigger required error
    fireEvent.change(systemPromptInput, { target: { value: 'temp value' } })
    fireEvent.change(systemPromptInput, { target: { value: '' } })

    await waitFor(() => {
      expect(systemPromptInput.getAttribute('aria-invalid')).toBe('true')
      expect(systemPromptInput.getAttribute('aria-describedby')).toBe('persona-systemPrompt-error')
    })

    const errorEl = document.getElementById('persona-systemPrompt-error')
    expect(errorEl).not.toBeNull()
    expect(errorEl?.getAttribute('role')).toBe('alert')
  })
})

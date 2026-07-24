import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '../../../test/utils'
import { PersonaInfoTab } from '../ui/PersonaInfoTab'
import type { PersonaResponse } from '../types'

const basePersona: PersonaResponse = {
  id: 'persona-1',
  name: 'Support Bot',
  systemPrompt: 'Fallback prompt',
  isDefault: false,
  description: 'Support persona',
  responseGuideline: 'Answer in bullet points.',
  welcomeMessage: 'Welcome!',
  promptTemplateId: 'template-1',
  icon: '\u{1F916}',
  isActive: true,
  createdAt: 1,
  updatedAt: 2,
}

describe('PersonaInfoTab', () => {
  it('renders readable role content without decorative emoji identity', () => {
    render(<PersonaInfoTab persona={basePersona} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('Fallback prompt')).toBeInTheDocument()
    expect(screen.queryByText('\u{1F916}')).not.toBeInTheDocument()
  })

  it('renders system prompt', () => {
    render(<PersonaInfoTab persona={basePersona} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('Fallback prompt')).toBeInTheDocument()
  })

  it('renders optional fields when present', () => {
    render(<PersonaInfoTab persona={basePersona} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('Support persona')).toBeInTheDocument()
    expect(screen.getByText('Answer in bullet points.')).toBeInTheDocument()
    expect(screen.getByText('Welcome!')).toBeInTheDocument()
  })

  it('hides optional fields when null', () => {
    const minimal: PersonaResponse = {
      ...basePersona,
      description: null,
      responseGuideline: null,
      welcomeMessage: null,
    }
    render(<PersonaInfoTab persona={minimal} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.queryByText('Support persona')).not.toBeInTheDocument()
    expect(screen.queryByText('Answer in bullet points.')).not.toBeInTheDocument()
  })

  it('shows default state as a plain fact', () => {
    const defaultPersona = { ...basePersona, isDefault: true }
    render(<PersonaInfoTab persona={defaultPersona} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('Yes')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /delete/i })).toBeDisabled()
  })

  it('shows inactive state as a plain fact', () => {
    const inactive = { ...basePersona, isActive: false }
    render(<PersonaInfoTab persona={inactive} onEdit={vi.fn()} onDelete={vi.fn()} />)
    expect(screen.getByText('INACTIVE')).toBeInTheDocument()
  })

  it('calls onEdit when edit button is clicked', () => {
    const onEdit = vi.fn()
    render(<PersonaInfoTab persona={basePersona} onEdit={onEdit} onDelete={vi.fn()} />)
    screen.getByRole('button', { name: /edit/i }).click()
    expect(onEdit).toHaveBeenCalled()
  })

  it('calls onDelete from the selected role detail', () => {
    const onDelete = vi.fn()
    render(<PersonaInfoTab persona={basePersona} onEdit={vi.fn()} onDelete={onDelete} />)
    screen.getByRole('button', { name: /delete/i }).click()
    expect(onDelete).toHaveBeenCalled()
  })
})

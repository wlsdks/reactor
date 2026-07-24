import { render, screen } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { TemplateList } from '../ui/TemplateList'

const templates = [
  { id: '1', name: 'General Q&A', description: 'General', createdAt: 0, updatedAt: 0 },
  { id: '2', name: 'Code Review', description: 'Code', createdAt: 0, updatedAt: 0 },
]

describe('TemplateList', () => {
  it('renders template names', () => {
    render(<TemplateList templates={templates} selectedId={null} onSelect={vi.fn()} onCreateNew={vi.fn()} />)
    expect(screen.getByText('General Q&A')).toBeInTheDocument()
    expect(screen.getByText('Code Review')).toBeInTheDocument()
  })

  it('highlights selected template', () => {
    render(<TemplateList templates={templates} selectedId="1" onSelect={vi.fn()} onCreateNew={vi.fn()} />)
    expect(screen.getByText('General Q&A').closest('.template-list-item')).toHaveClass('selected')
  })

  it('calls onSelect when clicked', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<TemplateList templates={templates} selectedId={null} onSelect={onSelect} onCreateNew={vi.fn()} />)
    await user.click(screen.getByText('Code Review'))
    expect(onSelect).toHaveBeenCalledWith('2')
  })

  it('shows new template button', () => {
    render(<TemplateList templates={templates} selectedId={null} onSelect={vi.fn()} onCreateNew={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'prompts.createTemplate' })).toBeInTheDocument()
  })

  it('shows empty state when no templates', () => {
    render(<TemplateList templates={[]} selectedId={null} onSelect={vi.fn()} onCreateNew={vi.fn()} />)
    expect(screen.getByRole('button')).toBeInTheDocument()
  })
})

import { render, screen, fireEvent } from '../../../test/utils'
import { describe, it, expect, vi } from 'vitest'
import { SettingsTab } from '../ui/SettingsTab'
import type { TemplateDetailResponse } from '../types'
import { formatDateTime } from '../../../shared/lib/formatters'

vi.mock('../../../shared/lib/clipboard', () => ({
  copyToClipboard: vi.fn().mockResolvedValue(true),
}))

function makeTemplate(overrides: Partial<TemplateDetailResponse> = {}): TemplateDetailResponse {
  return {
    id: 'tmpl-abc-123',
    name: 'Customer Support',
    description: 'A support template',
    activeVersion: null,
    versions: [],
    createdAt: 1700000000000,
    updatedAt: 1700100000000,
    ...overrides,
  }
}

const defaultProps = {
  onUpdate: vi.fn(),
  onDelete: vi.fn(),
  saving: false,
  experimentCount: 0,
}

describe('SettingsTab', () => {
  it('renders template name and description', () => {
    render(<SettingsTab template={makeTemplate()} {...defaultProps} />)

    expect(screen.getByText('Customer Support')).toBeInTheDocument()
    expect(screen.getByText('A support template')).toBeInTheDocument()
  })

  it('shows template ID with copy button', () => {
    render(<SettingsTab template={makeTemplate()} {...defaultProps} />)

    expect(screen.getByText('tmpl-abc-123')).toBeInTheDocument()
    // CopyButton renders with aria-label derived from common.copy.aria.
    const copyButton = screen.getByRole('button', { name: /common\.copy\.aria/i })
    expect(copyButton).toBeInTheDocument()
  })

  it('copies template ID when copy button is clicked', async () => {
    const { copyToClipboard } = await import('../../../shared/lib/clipboard')
    render(<SettingsTab template={makeTemplate()} {...defaultProps} />)

    const copyButton = screen.getByRole('button', { name: /common\.copy\.aria/i })
    fireEvent.click(copyButton)
    expect(copyToClipboard).toHaveBeenCalledWith('tmpl-abc-123', expect.objectContaining({
      label: 'promptStudio.templateId',
    }))
  })

  it('shows timestamps', () => {
    const template = makeTemplate({
      createdAt: 1700000000000,
      updatedAt: 1700100000000,
    })
    render(<SettingsTab template={template} {...defaultProps} />)

    const createdText = formatDateTime(1700000000000)
    const updatedText = formatDateTime(1700100000000)

    expect(screen.getByText((content) => content.includes(createdText))).toBeInTheDocument()
    expect(screen.getByText((content) => content.includes(updatedText))).toBeInTheDocument()
  })

  it('opens delete confirmation dialog when delete button is clicked', () => {
    render(<SettingsTab template={makeTemplate()} {...defaultProps} />)

    // common.delete is translated as "Delete" in test i18n
    fireEvent.click(screen.getByText('Delete'))
    // ConfirmDialog renders with the title
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('shows experiment count warning in delete dialog when experiments exist', () => {
    render(
      <SettingsTab
        template={makeTemplate()}
        {...defaultProps}
        experimentCount={5}
      />,
    )

    fireEvent.click(screen.getByText('Delete'))

    // The delete message should contain the warning key (returned as-is from i18n)
    const dialog = screen.getByRole('dialog')
    expect(dialog.textContent).toContain('promptStudio.deleteTemplateWarning')
  })

  it('calls onDelete when delete is confirmed', () => {
    const onDelete = vi.fn()
    render(
      <SettingsTab
        template={makeTemplate()}
        {...defaultProps}
        onDelete={onDelete}
      />,
    )

    fireEvent.click(screen.getByText('Delete'))
    fireEvent.click(screen.getByRole('button', { name: /confirm/i }))
    expect(onDelete).toHaveBeenCalled()
  })

  it('inline edit name saves on Enter', () => {
    const onUpdate = vi.fn()
    render(
      <SettingsTab
        template={makeTemplate()}
        {...defaultProps}
        onUpdate={onUpdate}
      />,
    )

    fireEvent.click(screen.getByTestId('editable-name'))

    const input = screen.getByDisplayValue('Customer Support')
    fireEvent.change(input, { target: { value: 'Updated Name' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(onUpdate).toHaveBeenCalledWith({
      name: 'Updated Name',
      description: 'A support template',
    })
  })

  it('inline edit name cancels on Escape', () => {
    const onUpdate = vi.fn()
    render(
      <SettingsTab
        template={makeTemplate()}
        {...defaultProps}
        onUpdate={onUpdate}
      />,
    )

    fireEvent.click(screen.getByTestId('editable-name'))
    const input = screen.getByDisplayValue('Customer Support')
    fireEvent.change(input, { target: { value: 'Changed' } })
    fireEvent.keyDown(input, { key: 'Escape' })

    expect(onUpdate).not.toHaveBeenCalled()
    expect(screen.getByText('Customer Support')).toBeInTheDocument()
  })

  it('inline edit description saves on Enter', () => {
    const onUpdate = vi.fn()
    render(
      <SettingsTab
        template={makeTemplate()}
        {...defaultProps}
        onUpdate={onUpdate}
      />,
    )

    fireEvent.click(screen.getByTestId('editable-description'))
    const input = screen.getByDisplayValue('A support template')
    fireEvent.change(input, { target: { value: 'New description' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(onUpdate).toHaveBeenCalledWith({
      name: 'Customer Support',
      description: 'New description',
    })
  })
})

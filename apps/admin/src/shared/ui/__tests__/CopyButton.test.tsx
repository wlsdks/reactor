import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../../../test/utils'
import { CopyButton } from '../CopyButton'
import { useToastStore } from '../../store/toast.store'

function clearToasts() {
  useToastStore.setState({ toasts: [] })
}

describe('CopyButton', () => {
  beforeEach(() => {
    clearToasts()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    clearToasts()
  })

  it('renders the icon-only variant by default with an aria-label', () => {
    render(<CopyButton value="abc-123" label="ID" />)
    const btn = screen.getByRole('button')
    expect(btn).toHaveClass('copy-button', 'copy-button--icon', 'copy-button--sm')
    // Default variant: no value text rendered.
    expect(screen.queryByTestId('copy-button-value')).toBeNull()
    // Test i18n stub returns keys as-is, so the aria-label resolves to the
    // key path. The presence of an aria-label and title is what matters here.
    expect(btn.getAttribute('aria-label')).toBe('common.copy.aria')
    expect(btn.getAttribute('title')).toBe('common.copy.aria')
  })

  it('renders the icon-text variant with the truncated value', () => {
    render(<CopyButton value="abc-123-very-long" label="ID" variant="icon-text" />)
    const valueNode = screen.getByTestId('copy-button-value')
    expect(valueNode.textContent).toBe('abc-123-very-long')
    expect(screen.getByRole('button')).toHaveClass('copy-button--icon-text')
  })

  it('disables the button when value is empty', () => {
    render(<CopyButton value="" label="ID" />)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('writes to the clipboard and swaps to the check icon on click', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText: writeTextMock } })

    render(<CopyButton value="abc-123" label="ID" />)
    const btn = screen.getByRole('button')

    fireEvent.click(btn)

    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith('abc-123')
    })
    await waitFor(() => {
      expect(btn).toHaveClass('copy-button--copied')
    })
    expect(btn.getAttribute('data-copied')).toBe('true')
  })

  it('does not toggle the check icon when the copy fails', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error('blocked')) },
    })
    document.execCommand = vi.fn().mockReturnValue(false)

    render(<CopyButton value="abc-123" label="ID" />)
    const btn = screen.getByRole('button')

    fireEvent.click(btn)

    await waitFor(() => {
      const toasts = useToastStore.getState().toasts
      expect(toasts.some((toast) => toast.type === 'error')).toBe(true)
    })
    expect(btn).not.toHaveClass('copy-button--copied')
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../../../test/utils'
import { SavedViewsControl } from '../SavedViewsControl'
import { useSavedViewsStore, SAVED_VIEWS_STORAGE_KEY } from '../../store/savedViews.store'

function reset() {
  localStorage.removeItem(SAVED_VIEWS_STORAGE_KEY)
  useSavedViewsStore.setState({ views: [] })
}

describe('SavedViewsControl', () => {
  beforeEach(() => {
    reset()
  })

  it('renders the dropdown label and an empty trigger when no views exist', () => {
    render(<SavedViewsControl scope="audit" currentParams={{}} onApply={() => {}} />)
    expect(screen.getByText('Saved views')).toBeInTheDocument()
    // Trigger collapses to "No saved views" when the scope has nothing yet.
    expect(screen.getByRole('button', { name: /No saved views/ })).toBeInTheDocument()
  })

  it('opens the panel and shows the empty state on first click', async () => {
    const user = userEvent.setup()
    render(<SavedViewsControl scope="audit" currentParams={{}} onApply={() => {}} />)
    await user.click(screen.getByRole('button', { name: /No saved views/ }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getByText('No saved views yet')).toBeInTheDocument()
  })

  it('shows scope-filtered views in the dropdown and ignores other scopes', async () => {
    useSavedViewsStore.getState().add('audit', 'High risk', { audit_p: '2' })
    useSavedViewsStore.getState().add('feedback', 'Inbox only', { feedback_p: '1' })

    const user = userEvent.setup()
    render(<SavedViewsControl scope="audit" currentParams={{}} onApply={() => {}} />)
    await user.click(screen.getByRole('button', { name: /1 saved/ }))

    expect(screen.getByText('High risk')).toBeInTheDocument()
    expect(screen.queryByText('Inbox only')).not.toBeInTheDocument()
  })

  it('saves a new view via the inline form (Enter submits)', async () => {
    const user = userEvent.setup()
    render(<SavedViewsControl scope="audit" currentParams={{ audit_p: '3' }} onApply={() => {}} />)

    await user.click(screen.getByRole('button', { name: /No saved views/ }))
    await user.click(screen.getByRole('button', { name: /Save current filter/ }))

    const input = screen.getByRole('textbox', { name: /Enter view name/ })
    await user.type(input, 'Page 3 view{Enter}')

    const stored = useSavedViewsStore.getState().list('audit')
    expect(stored).toHaveLength(1)
    expect(stored[0].name).toBe('Page 3 view')
    expect(stored[0].params).toEqual({ audit_p: '3' })
  })

  it('Save button is disabled until a non-empty name is typed', async () => {
    const user = userEvent.setup()
    render(<SavedViewsControl scope="audit" currentParams={{}} onApply={() => {}} />)

    await user.click(screen.getByRole('button', { name: /No saved views/ }))
    await user.click(screen.getByRole('button', { name: /Save current filter/ }))

    const saveBtn = screen.getByRole('button', { name: /^Save$/ })
    expect(saveBtn).toBeDisabled()

    await user.type(screen.getByRole('textbox', { name: /Enter view name/ }), 'Foo')
    expect(saveBtn).not.toBeDisabled()
  })

  it('Escape inside the save form cancels back to the trigger', async () => {
    const user = userEvent.setup()
    render(<SavedViewsControl scope="audit" currentParams={{}} onApply={() => {}} />)

    await user.click(screen.getByRole('button', { name: /No saved views/ }))
    await user.click(screen.getByRole('button', { name: /Save current filter/ }))
    await user.type(screen.getByRole('textbox', { name: /Enter view name/ }), 'x')
    await user.keyboard('{Escape}')

    // Form should close; the "Save current filter…" trigger should reappear.
    expect(screen.queryByRole('textbox', { name: /Enter view name/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save current filter/ })).toBeInTheDocument()
  })

  it('Apply triggers onApply with the stored params and closes the panel', async () => {
    useSavedViewsStore.getState().add('audit', 'High risk', { audit_p: '2', audit_s: 'category' })
    const onApply = vi.fn()
    const user = userEvent.setup()
    render(<SavedViewsControl scope="audit" currentParams={{}} onApply={onApply} />)

    await user.click(screen.getByRole('button', { name: /1 saved/ }))
    await user.click(screen.getByRole('button', { name: 'Apply' }))

    expect(onApply).toHaveBeenCalledTimes(1)
    expect(onApply).toHaveBeenCalledWith({ audit_p: '2', audit_s: 'category' })
    // Panel auto-closes after applying.
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('Remove requires a confirmation click before deleting', async () => {
    useSavedViewsStore.getState().add('audit', 'High risk', { audit_p: '2' })
    const user = userEvent.setup()
    render(<SavedViewsControl scope="audit" currentParams={{}} onApply={() => {}} />)

    await user.click(screen.getByRole('button', { name: /1 saved/ }))

    // First click: arms the confirm-state (button label changes).
    await user.click(screen.getByRole('button', { name: 'Remove' }))
    expect(useSavedViewsStore.getState().list('audit')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Click again' })).toBeInTheDocument()

    // Second click: actually removes.
    await user.click(screen.getByRole('button', { name: 'Click again' }))
    expect(useSavedViewsStore.getState().list('audit')).toHaveLength(0)
  })

  it('Escape on the open panel closes it', async () => {
    const user = userEvent.setup()
    render(<SavedViewsControl scope="audit" currentParams={{}} onApply={() => {}} />)
    await user.click(screen.getByRole('button', { name: /No saved views/ }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})

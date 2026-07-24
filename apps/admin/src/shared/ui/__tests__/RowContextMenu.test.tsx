import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '../../../test/utils'
import { RowContextMenu, type RowAction } from '../RowContextMenu'

interface Row {
  id: string
  name: string
}

const sampleRow: Row = { id: 'row-1', name: 'Alice' }

function makeActions(overrides: Partial<RowAction<Row>>[] = []): RowAction<Row>[] {
  const base: RowAction<Row>[] = [
    { id: 'copy', label: 'Copy ID', perform: vi.fn() },
    { id: 'open', label: 'Open detail', perform: vi.fn() },
    { id: 'delete', label: 'Delete', destructive: true, perform: vi.fn() },
  ]
  if (overrides.length === 0) return base
  return base.map((action, i) => ({ ...action, ...overrides[i] }))
}

describe('RowContextMenu', () => {
  beforeEach(() => {
    cleanup()
    Object.defineProperty(window, 'innerWidth', { value: 1280, configurable: true })
    Object.defineProperty(window, 'innerHeight', { value: 800, configurable: true })
  })

  it('renders nothing when position is null', () => {
    const { container } = render(
      <RowContextMenu row={sampleRow} actions={makeActions()} position={null} onClose={vi.fn()} />,
    )
    // No portal content reaches the document body either.
    expect(container.querySelector('.row-context-menu')).toBeNull()
    expect(document.body.querySelector('.row-context-menu')).toBeNull()
  })

  it('renders all enabled actions in a menu role', () => {
    render(
      <RowContextMenu row={sampleRow} actions={makeActions()} position={{ x: 100, y: 100 }} onClose={vi.fn()} />,
    )
    const menu = screen.getByRole('menu')
    expect(menu).toBeInTheDocument()
    const items = screen.getAllByRole('menuitem')
    expect(items).toHaveLength(3)
    expect(items[0].textContent).toContain('Copy ID')
    expect(items[1].textContent).toContain('Open detail')
    expect(items[2].textContent).toContain('Delete')
  })

  it('omits hidden actions entirely', () => {
    const actions = makeActions([
      {},
      { hidden: () => true },
      {},
    ])
    render(
      <RowContextMenu row={sampleRow} actions={actions} position={{ x: 50, y: 50 }} onClose={vi.fn()} />,
    )
    const items = screen.getAllByRole('menuitem')
    expect(items).toHaveLength(2)
    expect(screen.queryByText('Open detail')).toBeNull()
  })

  it('marks destructive actions with the destructive class', () => {
    render(
      <RowContextMenu row={sampleRow} actions={makeActions()} position={{ x: 0, y: 0 }} onClose={vi.fn()} />,
    )
    const deleteItem = screen.getByText('Delete').closest('button')
    expect(deleteItem?.classList.contains('row-context-menu__item--destructive')).toBe(true)
  })

  it('disabled actions have the disabled attribute and ignore clicks', () => {
    const performMock = vi.fn()
    const actions = makeActions([
      { disabled: () => true, perform: performMock },
      {},
      {},
    ])
    const onClose = vi.fn()
    render(
      <RowContextMenu row={sampleRow} actions={actions} position={{ x: 10, y: 10 }} onClose={onClose} />,
    )
    const item = screen.getByText('Copy ID').closest('button') as HTMLButtonElement
    expect(item.disabled).toBe(true)
    expect(item.getAttribute('aria-disabled')).toBe('true')
    expect(item.classList.contains('row-context-menu__item--disabled')).toBe(true)
    fireEvent.click(item)
    expect(performMock).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('clicking an enabled action invokes perform with the row and closes', () => {
    const onClose = vi.fn()
    const performMock = vi.fn()
    const actions = makeActions([
      { perform: performMock },
      {},
      {},
    ])
    render(
      <RowContextMenu row={sampleRow} actions={actions} position={{ x: 5, y: 5 }} onClose={onClose} />,
    )
    fireEvent.click(screen.getByText('Copy ID'))
    expect(performMock).toHaveBeenCalledWith(sampleRow)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('ArrowDown / ArrowUp cycles the active item', () => {
    render(
      <RowContextMenu row={sampleRow} actions={makeActions()} position={{ x: 0, y: 0 }} onClose={vi.fn()} />,
    )
    const menu = screen.getByRole('menu')
    const items = screen.getAllByRole('menuitem')

    // First item active by default.
    expect(items[0].classList.contains('row-context-menu__item--active')).toBe(true)

    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(items[1].classList.contains('row-context-menu__item--active')).toBe(true)

    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(items[2].classList.contains('row-context-menu__item--active')).toBe(true)

    // Wraps to top.
    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    expect(items[0].classList.contains('row-context-menu__item--active')).toBe(true)

    // ArrowUp wraps backward.
    fireEvent.keyDown(menu, { key: 'ArrowUp' })
    expect(items[2].classList.contains('row-context-menu__item--active')).toBe(true)
  })

  it('Enter invokes the active action', () => {
    const performMock = vi.fn()
    const actions = makeActions([
      {},
      { perform: performMock },
      {},
    ])
    const onClose = vi.fn()
    render(
      <RowContextMenu row={sampleRow} actions={actions} position={{ x: 0, y: 0 }} onClose={onClose} />,
    )
    const menu = screen.getByRole('menu')
    fireEvent.keyDown(menu, { key: 'ArrowDown' })
    fireEvent.keyDown(menu, { key: 'Enter' })
    expect(performMock).toHaveBeenCalledWith(sampleRow)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Escape closes the menu via useEscapeClose', () => {
    const onClose = vi.fn()
    render(
      <RowContextMenu row={sampleRow} actions={makeActions()} position={{ x: 0, y: 0 }} onClose={onClose} />,
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('outside click closes the menu', () => {
    const onClose = vi.fn()
    render(
      <RowContextMenu row={sampleRow} actions={makeActions()} position={{ x: 0, y: 0 }} onClose={onClose} />,
    )
    // Mousedown on body (outside the menu) should close.
    fireEvent.mouseDown(document.body)
    expect(onClose).toHaveBeenCalled()
  })

  it('clamps position so the menu stays inside the viewport', () => {
    Object.defineProperty(window, 'innerWidth', { value: 1000, configurable: true })
    Object.defineProperty(window, 'innerHeight', { value: 600, configurable: true })
    render(
      <RowContextMenu
        row={sampleRow}
        actions={makeActions()}
        position={{ x: 990, y: 590 }}
        onClose={vi.fn()}
      />,
    )
    const menu = screen.getByRole('menu') as HTMLDivElement
    // After the layout effect runs, the menu should sit within the viewport
    // with the 8px margin enforced. Use the inline `left` / `top` we set.
    const left = parseFloat(menu.style.left)
    const top = parseFloat(menu.style.top)
    const rect = menu.getBoundingClientRect()
    expect(left + rect.width).toBeLessThanOrEqual(1000 - 8 + 0.5)
    expect(top + rect.height).toBeLessThanOrEqual(600 - 8 + 0.5)
  })
})

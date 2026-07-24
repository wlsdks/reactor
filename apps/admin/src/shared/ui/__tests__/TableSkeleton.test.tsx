import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { TableSkeleton } from '../TableSkeleton'

describe('TableSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = render(<TableSkeleton />)
    expect(container.firstChild).not.toBeNull()
  })

  it('has aria-busy attribute set to true', () => {
    const { container } = render(<TableSkeleton />)
    const root = container.querySelector('.skeleton-table')
    expect(root?.getAttribute('aria-busy')).toBe('true')
  })

  it('has accessible loading label', () => {
    render(<TableSkeleton />)
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
  })

  it('renders default 5 rows', () => {
    const { container } = render(<TableSkeleton />)
    const rows = container.querySelectorAll('.skeleton-table-row')
    expect(rows).toHaveLength(5)
  })

  it('renders default 3 header columns', () => {
    const { container } = render(<TableSkeleton />)
    const header = container.querySelector('.skeleton-table-header')
    const cells = header?.querySelectorAll('.skeleton-table-cell')
    expect(cells).toHaveLength(3)
  })

  it('renders custom row count', () => {
    const { container } = render(<TableSkeleton rows={10} />)
    const rows = container.querySelectorAll('.skeleton-table-row')
    expect(rows).toHaveLength(10)
  })

  it('renders custom column count', () => {
    const { container } = render(<TableSkeleton columns={5} />)
    const header = container.querySelector('.skeleton-table-header')
    const cells = header?.querySelectorAll('.skeleton-table-cell')
    expect(cells).toHaveLength(5)
  })

  it('each row has the correct number of cells matching columns', () => {
    const { container } = render(<TableSkeleton rows={3} columns={4} />)
    const rows = container.querySelectorAll('.skeleton-table-row')
    rows.forEach((row) => {
      const cells = row.querySelectorAll('.skeleton-table-cell')
      expect(cells).toHaveLength(4)
    })
  })
})

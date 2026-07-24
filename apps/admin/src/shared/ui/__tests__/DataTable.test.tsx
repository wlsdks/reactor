import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useState } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { render, screen, fireEvent, waitFor } from '../../../test/utils'
import { DataTable } from '../DataTable'
import type { Column } from '../DataTable'
import { pageRange } from '../pageRange'

interface TestRow {
  id: string
  name: string
  value: number
}

const columns: Column<TestRow>[] = [
  { key: 'name', header: 'Name', render: row => row.name },
  { key: 'value', header: 'Value', render: row => String(row.value) },
]

const data: TestRow[] = [
  { id: '1', name: 'Alice', value: 100 },
  { id: '2', name: 'Bob', value: 200 },
  { id: '3', name: 'Charlie', value: 300 },
]

describe('DataTable', () => {
  it('renders column headers', () => {
    render(<DataTable columns={columns} data={data} keyFn={r => r.id} />)
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Value')).toBeInTheDocument()
  })

  it('renders all data rows', () => {
    render(<DataTable columns={columns} data={data} keyFn={r => r.id} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('Charlie')).toBeInTheDocument()
  })

  it('renders empty table with no rows when data is empty', () => {
    render(<DataTable columns={columns} data={[]} keyFn={r => r.id} />)
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.queryByText('Alice')).not.toBeInTheDocument()
  })

  it('calls onRowClick with row data when row is clicked', () => {
    const onClick = vi.fn()
    render(<DataTable columns={columns} data={data} keyFn={r => r.id} onRowClick={onClick} />)
    fireEvent.click(screen.getByText('Alice'))
    expect(onClick).toHaveBeenCalledWith(data[0])
  })

  it('adds clickable class to rows when onRowClick is provided', () => {
    const { container } = render(
      <DataTable columns={columns} data={data} keyFn={r => r.id} onRowClick={vi.fn()} />,
    )
    const rows = container.querySelectorAll('tbody tr')
    rows.forEach(row => expect(row.classList.contains('clickable')).toBe(true))
  })

  it('does not add clickable class without onRowClick', () => {
    const { container } = render(
      <DataTable columns={columns} data={data} keyFn={r => r.id} />,
    )
    const rows = container.querySelectorAll('tbody tr')
    rows.forEach(row => expect(row.classList.contains('clickable')).toBe(false))
  })

  it('highlights selected row with is-selected class', () => {
    const { container } = render(
      <DataTable columns={columns} data={data} keyFn={r => r.id} selectedKey="2" />,
    )
    const rows = container.querySelectorAll('tbody tr')
    expect(rows[0].classList.contains('is-selected')).toBe(false)
    expect(rows[1].classList.contains('is-selected')).toBe(true)
    expect(rows[2].classList.contains('is-selected')).toBe(false)
  })

  it('applies rowClassName to matching rows', () => {
    const { container } = render(
      <DataTable
        columns={columns}
        data={data}
        keyFn={r => r.id}
        rowClassName={row => (row.value > 200 ? 'high-value' : undefined)}
      />,
    )
    const rows = container.querySelectorAll('tbody tr')
    expect(rows[0].classList.contains('high-value')).toBe(false)
    expect(rows[1].classList.contains('high-value')).toBe(false)
    expect(rows[2].classList.contains('high-value')).toBe(true)
  })

  it('applies column width when specified', () => {
    const colsWithWidth: Column<TestRow>[] = [
      { key: 'name', header: 'Name', render: row => row.name, width: '200px' },
      { key: 'value', header: 'Value', render: row => String(row.value) },
    ]
    const { container } = render(
      <DataTable columns={colsWithWidth} data={data} keyFn={r => r.id} />,
    )
    const headers = container.querySelectorAll('th')
    expect((headers[0] as HTMLElement).style.width).toBe('200px')
    expect((headers[1] as HTMLElement).style.width).toBe('')
  })

  // --- Sorting ---

  describe('sorting', () => {
    const sortableColumns: Column<TestRow>[] = [
      { key: 'name', header: 'Name', render: row => row.name, sortable: true },
      { key: 'value', header: 'Value', render: row => String(row.value), sortable: true },
    ]

    it('renders sortable headers with sortable-header class', () => {
      const onSort = vi.fn()
      const { container } = render(
        <DataTable columns={sortableColumns} data={data} keyFn={r => r.id} onSort={onSort} />,
      )
      const headers = container.querySelectorAll('.sortable-header')
      expect(headers).toHaveLength(2)
    })

    it('does not render sortable-header class without onSort', () => {
      const { container } = render(
        <DataTable columns={sortableColumns} data={data} keyFn={r => r.id} />,
      )
      const headers = container.querySelectorAll('.sortable-header')
      expect(headers).toHaveLength(0)
    })

    it('calls onSort with ascending on first click', () => {
      const onSort = vi.fn()
      render(
        <DataTable columns={sortableColumns} data={data} keyFn={r => r.id} onSort={onSort} />,
      )
      fireEvent.click(screen.getByText('Name'))
      expect(onSort).toHaveBeenCalledWith('name', 'asc')
    })

    it('cycles sort direction: asc -> desc -> null', () => {
      const onSort = vi.fn()
      // Currently sorted ascending on 'name'
      render(
        <DataTable
          columns={sortableColumns}
          data={data}
          keyFn={r => r.id}
          onSort={onSort}
          sortKey="name"
          sortDirection="asc"
        />,
      )
      fireEvent.click(screen.getByText(/^Name/))
      expect(onSort).toHaveBeenCalledWith('name', 'desc')
    })

    it('cycles from desc to null (no sort)', () => {
      const onSort = vi.fn()
      render(
        <DataTable
          columns={sortableColumns}
          data={data}
          keyFn={r => r.id}
          onSort={onSort}
          sortKey="name"
          sortDirection="desc"
        />,
      )
      fireEvent.click(screen.getByText(/^Name/))
      expect(onSort).toHaveBeenCalledWith('name', null)
    })

    it('clicking a different column starts with asc', () => {
      const onSort = vi.fn()
      render(
        <DataTable
          columns={sortableColumns}
          data={data}
          keyFn={r => r.id}
          onSort={onSort}
          sortKey="name"
          sortDirection="asc"
        />,
      )
      fireEvent.click(screen.getByText('Value'))
      expect(onSort).toHaveBeenCalledWith('value', 'asc')
    })

    it('displays ascending sort indicator', () => {
      render(
        <DataTable
          columns={sortableColumns}
          data={data}
          keyFn={r => r.id}
          onSort={vi.fn()}
          sortKey="name"
          sortDirection="asc"
        />,
      )
      const nameHeader = screen.getByText('Name').closest('th')
      const icon = nameHeader?.querySelector('.data-table-sort-icon')
      expect(icon).not.toBeNull()
      expect(icon?.classList.contains('data-table-sort-icon--active')).toBe(true)
      expect(icon?.tagName.toLowerCase()).toBe('svg')
      expect(icon?.getAttribute('width')).toBe('8')
    })

    it('displays descending sort indicator', () => {
      render(
        <DataTable
          columns={sortableColumns}
          data={data}
          keyFn={r => r.id}
          onSort={vi.fn()}
          sortKey="name"
          sortDirection="desc"
        />,
      )
      const nameHeader = screen.getByText('Name').closest('th')
      const icon = nameHeader?.querySelector('.data-table-sort-icon')
      expect(icon).not.toBeNull()
      expect(icon?.classList.contains('data-table-sort-icon--active')).toBe(true)
      expect(icon?.tagName.toLowerCase()).toBe('svg')
    })

    it('sets aria-sort="ascending" on actively sorted column', () => {
      render(
        <DataTable
          columns={sortableColumns}
          data={data}
          keyFn={r => r.id}
          onSort={vi.fn()}
          sortKey="name"
          sortDirection="asc"
        />,
      )
      const nameHeader = screen.getByText(/Name/)
      expect(nameHeader.getAttribute('aria-sort')).toBe('ascending')
    })

    it('sets aria-sort="descending" on actively sorted column', () => {
      render(
        <DataTable
          columns={sortableColumns}
          data={data}
          keyFn={r => r.id}
          onSort={vi.fn()}
          sortKey="name"
          sortDirection="desc"
        />,
      )
      const nameHeader = screen.getByText(/Name/)
      expect(nameHeader.getAttribute('aria-sort')).toBe('descending')
    })

    it('sets aria-sort="none" on unsorted sortable columns', () => {
      render(
        <DataTable
          columns={sortableColumns}
          data={data}
          keyFn={r => r.id}
          onSort={vi.fn()}
          sortKey="name"
          sortDirection="asc"
        />,
      )
      const valueHeader = screen.getByText('Value')
      expect(valueHeader.getAttribute('aria-sort')).toBe('none')
    })

    it('renders inactive chevron pair on sortable but unsorted columns', () => {
      render(
        <DataTable
          columns={sortableColumns}
          data={data}
          keyFn={r => r.id}
          onSort={vi.fn()}
          sortKey="name"
          sortDirection="asc"
        />,
      )
      const valueHeader = screen.getByText('Value').closest('th') as HTMLElement
      const icon = valueHeader.querySelector('.data-table-sort-icon')
      expect(icon).not.toBeNull()
      expect(icon?.classList.contains('data-table-sort-icon--inactive')).toBe(true)
      // Inactive icon is composed of two stacked chevron paths.
      expect(icon?.querySelectorAll('path').length).toBe(2)
    })

    it('active sort column applies aria-sort and visual class', () => {
      const { container } = render(
        <DataTable
          columns={sortableColumns}
          data={data}
          keyFn={r => r.id}
          onSort={vi.fn()}
          sortKey="value"
          sortDirection="desc"
        />,
      )
      // Active header carries aria-sort and the active modifier class.
      const valueHeader = screen.getByText('Value').closest('th') as HTMLElement
      expect(valueHeader.getAttribute('aria-sort')).toBe('descending')
      expect(valueHeader.classList.contains('sortable-header--active')).toBe(true)

      // Inactive sortable column gets aria-sort="none" and no active class.
      const nameHeader = screen.getByText('Name').closest('th') as HTMLElement
      expect(nameHeader.getAttribute('aria-sort')).toBe('none')
      expect(nameHeader.classList.contains('sortable-header--active')).toBe(false)

      // All body cells in the active column receive col-sort-active so the
      // CSS tint can highlight the sorted axis.
      const activeCells = container.querySelectorAll('tbody td.col-sort-active')
      expect(activeCells.length).toBe(data.length)
    })

    it('sortable headers are keyboard accessible via Enter', () => {
      const onSort = vi.fn()
      render(
        <DataTable columns={sortableColumns} data={data} keyFn={r => r.id} onSort={onSort} />,
      )
      const header = screen.getByText('Name')
      fireEvent.keyDown(header, { key: 'Enter' })
      expect(onSort).toHaveBeenCalledWith('name', 'asc')
    })

    it('sortable headers are keyboard accessible via Space', () => {
      const onSort = vi.fn()
      render(
        <DataTable columns={sortableColumns} data={data} keyFn={r => r.id} onSort={onSort} />,
      )
      const header = screen.getByText('Name')
      fireEvent.keyDown(header, { key: ' ' })
      expect(onSort).toHaveBeenCalledWith('name', 'asc')
    })

    it('sortable headers have role="button" and tabIndex=0', () => {
      render(
        <DataTable columns={sortableColumns} data={data} keyFn={r => r.id} onSort={vi.fn()} />,
      )
      const header = screen.getByText('Name')
      expect(header.getAttribute('role')).toBe('button')
      expect(header.getAttribute('tabindex')).toBe('0')
    })
  })

  // --- Pagination ---

  describe('pagination', () => {
    it('does not render pagination when not paginated', () => {
      const { container } = render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} />,
      )
      expect(container.querySelector('.table-pagination')).not.toBeInTheDocument()
    })

    it('does not render pagination when totalPages is 1', () => {
      const { container } = render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={1}
          pageSize={10}
          totalCount={3}
          onPageChange={vi.fn()}
        />,
      )
      expect(container.querySelector('.table-pagination')).not.toBeInTheDocument()
    })

    it('renders pagination when there are multiple pages', () => {
      const { container } = render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={1}
          pageSize={2}
          totalCount={5}
          onPageChange={vi.fn()}
        />,
      )
      expect(container.querySelector('.table-pagination')).toBeInTheDocument()
    })

    it('renders the pagination row as a navigation landmark', () => {
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={2}
          pageSize={2}
          totalCount={10}
          onPageChange={vi.fn()}
        />,
      )
      // role="navigation" + i18n key as accessible name (test i18n echoes keys).
      expect(
        screen.getByRole('navigation', { name: 'common.pagination.navLabel' }),
      ).toBeInTheDocument()
    })

    it('disables prev button on first page', () => {
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={1}
          pageSize={2}
          totalCount={5}
          onPageChange={vi.fn()}
        />,
      )
      const prev = screen.getByRole('button', { name: 'common.pagination.previousPage' })
      expect(prev).toBeDisabled()
    })

    it('disables next button on last page', () => {
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={3}
          pageSize={2}
          totalCount={5}
          onPageChange={vi.fn()}
        />,
      )
      const next = screen.getByRole('button', { name: 'common.pagination.nextPage' })
      expect(next).toBeDisabled()
    })

    it('calls onPageChange with previous page when prev is clicked', () => {
      const onPageChange = vi.fn()
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={2}
          pageSize={2}
          totalCount={5}
          onPageChange={onPageChange}
        />,
      )
      fireEvent.click(screen.getByRole('button', { name: 'common.pagination.previousPage' }))
      expect(onPageChange).toHaveBeenCalledWith(1)
    })

    it('calls onPageChange with next page when next is clicked', () => {
      const onPageChange = vi.fn()
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={1}
          pageSize={2}
          totalCount={5}
          onPageChange={onPageChange}
        />,
      )
      fireEvent.click(screen.getByRole('button', { name: 'common.pagination.nextPage' }))
      expect(onPageChange).toHaveBeenCalledWith(2)
    })

    // --- Numbered page buttons ---

    it('renders one button per page when totalPages ≤ window (7)', () => {
      const { container } = render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={3}
          pageSize={1}
          totalCount={5}
          onPageChange={vi.fn()}
        />,
      )
      const pageButtons = container.querySelectorAll('.table-pagination__page-btn')
      expect(pageButtons.length).toBe(5)
      const labels = Array.from(pageButtons, el => el.textContent?.trim())
      expect(labels).toEqual(['1', '2', '3', '4', '5'])
    })

    it('renders a 7-token row centered on current with first/last anchors', () => {
      const { container } = render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={50}
          pageSize={1}
          totalCount={99}
          onPageChange={vi.fn()}
        />,
      )
      // 5 numeric buttons (1, 49, 50, 51, 99) + 2 ellipses = 7 tokens total.
      const pageButtons = container.querySelectorAll('.table-pagination__page-btn')
      const labels = Array.from(pageButtons, el => el.textContent?.trim())
      expect(labels).toEqual(['1', '49', '50', '51', '99'])
      const ellipses = container.querySelectorAll('.table-pagination__ellipsis')
      expect(ellipses.length).toBe(2)
      expect(pageButtons.length + ellipses.length).toBe(7)
    })

    it('renders ellipsis between non-adjacent shown pages', () => {
      const { container } = render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={1}
          pageSize={1}
          totalCount={99}
          onPageChange={vi.fn()}
        />,
      )
      // current at edge: only one ellipsis (between window and the last anchor).
      const ellipses = container.querySelectorAll('.table-pagination__ellipsis')
      expect(ellipses.length).toBe(1)
    })

    it('marks the active page with aria-current="page"', () => {
      const { container } = render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={3}
          pageSize={1}
          totalCount={5}
          onPageChange={vi.fn()}
        />,
      )
      const active = container.querySelector(
        '.table-pagination__page-btn[aria-current="page"]',
      )
      expect(active?.textContent?.trim()).toBe('3')
    })

    it('clicking a numbered page button calls onPageChange with that page', () => {
      const onPageChange = vi.fn()
      const { container } = render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={1}
          pageSize={1}
          totalCount={5}
          onPageChange={onPageChange}
        />,
      )
      const buttons = Array.from(
        container.querySelectorAll<HTMLButtonElement>('.table-pagination__page-btn'),
      )
      const fourth = buttons.find(el => el.textContent?.trim() === '4')
      expect(fourth).toBeDefined()
      fireEvent.click(fourth!)
      expect(onPageChange).toHaveBeenCalledWith(4)
    })

    // --- Direct input "jump to page" ---

    it('jump input clamps to maxPage on Enter when value exceeds bounds', () => {
      const onPageChange = vi.fn()
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={1}
          pageSize={1}
          totalCount={20}
          onPageChange={onPageChange}
        />,
      )
      const input = screen.getByLabelText('common.pagination.jumpInputLabel') as HTMLInputElement
      fireEvent.change(input, { target: { value: '999' } })
      fireEvent.keyDown(input, { key: 'Enter' })
      expect(onPageChange).toHaveBeenCalledWith(20)
    })

    it('jump input clamps to 1 on Enter when value is below bounds', () => {
      const onPageChange = vi.fn()
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={5}
          pageSize={1}
          totalCount={20}
          onPageChange={onPageChange}
        />,
      )
      const input = screen.getByLabelText('common.pagination.jumpInputLabel') as HTMLInputElement
      fireEvent.change(input, { target: { value: '-5' } })
      fireEvent.keyDown(input, { key: 'Enter' })
      expect(onPageChange).toHaveBeenCalledWith(1)
    })

    it('jump action button commits typed page', () => {
      const onPageChange = vi.fn()
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={1}
          pageSize={1}
          totalCount={20}
          onPageChange={onPageChange}
        />,
      )
      const input = screen.getByLabelText('common.pagination.jumpInputLabel') as HTMLInputElement
      fireEvent.change(input, { target: { value: '7' } })
      fireEvent.click(screen.getByRole('button', { name: 'common.pagination.goAction' }))
      expect(onPageChange).toHaveBeenCalledWith(7)
    })

    it('jump action does not fire when typed page equals current', () => {
      const onPageChange = vi.fn()
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={5}
          pageSize={1}
          totalCount={20}
          onPageChange={onPageChange}
        />,
      )
      const input = screen.getByLabelText('common.pagination.jumpInputLabel') as HTMLInputElement
      // Input already shows "5" because it mirrors `page`. Submit it as-is.
      fireEvent.change(input, { target: { value: '5' } })
      fireEvent.click(screen.getByRole('button', { name: 'common.pagination.goAction' }))
      expect(onPageChange).not.toHaveBeenCalled()
    })

    // --- Mobile breakpoint: hide numbered buttons ---

    describe('mobile breakpoint (≤640px)', () => {
      let originalMatchMedia: typeof window.matchMedia

      beforeEach(() => {
        originalMatchMedia = window.matchMedia
        // Force the mobile query (≤640px) to match.
        window.matchMedia = ((query: string) => ({
          matches: query.includes('640px'),
          media: query,
          onchange: null,
          addListener: () => {},
          removeListener: () => {},
          addEventListener: () => {},
          removeEventListener: () => {},
          dispatchEvent: () => false,
        })) as typeof window.matchMedia
      })

      afterEach(() => {
        window.matchMedia = originalMatchMedia
      })

      it('hides the numeric page button row on mobile', () => {
        const { container } = render(
          <DataTable
            columns={columns}
            data={data}
            keyFn={r => r.id}
            page={3}
            pageSize={1}
            totalCount={20}
            onPageChange={vi.fn()}
          />,
        )
        expect(container.querySelector('.table-pagination__pages')).not.toBeInTheDocument()
        // Compact info label (N / M) replaces the button row.
        const info = container.querySelector('.table-pagination-info')
        expect(info?.getAttribute('aria-live')).toBe('polite')
      })

      it('keeps prev / next / jump-input usable on mobile', () => {
        render(
          <DataTable
            columns={columns}
            data={data}
            keyFn={r => r.id}
            page={3}
            pageSize={1}
            totalCount={20}
            onPageChange={vi.fn()}
          />,
        )
        expect(
          screen.getByRole('button', { name: 'common.pagination.previousPage' }),
        ).toBeInTheDocument()
        expect(
          screen.getByRole('button', { name: 'common.pagination.nextPage' }),
        ).toBeInTheDocument()
        expect(screen.getByLabelText('common.pagination.jumpInputLabel')).toBeInTheDocument()
      })
    })
  })

  // --- pageRange algorithm (pure helper) ---

  describe('pageRange()', () => {
    it('returns every page when total ≤ window', () => {
      expect(pageRange(1, 1)).toEqual([1])
      expect(pageRange(3, 5)).toEqual([1, 2, 3, 4, 5])
      expect(pageRange(7, 7)).toEqual([1, 2, 3, 4, 5, 6, 7])
    })

    it('inserts a single trailing ellipsis when current is near the start', () => {
      expect(pageRange(1, 99)).toEqual([1, 2, 3, 4, 5, 'ellipsis', 99])
      expect(pageRange(2, 99)).toEqual([1, 2, 3, 4, 5, 'ellipsis', 99])
    })

    it('inserts a single leading ellipsis when current is near the end', () => {
      expect(pageRange(99, 99)).toEqual([1, 'ellipsis', 95, 96, 97, 98, 99])
    })

    it('inserts two ellipses when current is in the middle', () => {
      expect(pageRange(50, 99)).toEqual([1, 'ellipsis', 49, 50, 51, 'ellipsis', 99])
    })

    it('returns an empty array for total ≤ 0', () => {
      expect(pageRange(1, 0)).toEqual([])
    })
  })

  // --- Cell truncation / title tooltip ---

  describe('cell truncation and title tooltip', () => {
    it('adds title attribute on td for long string cell values', () => {
      const longValue =
        '/very/long/file/path/that/definitely/overflows/in/a/narrow/column.log'
      const rows = [{ id: '1', name: longValue, value: 42 }]
      const cols: Column<TestRow>[] = [
        { key: 'name', header: 'Name', render: row => row.name },
      ]
      const { container } = render(
        <DataTable columns={cols} data={rows} keyFn={r => r.id} />,
      )
      const cell = container.querySelector('tbody td') as HTMLTableCellElement
      expect(cell.getAttribute('title')).toBe(longValue)
      expect(cell.classList.contains('data-table-cell-truncate')).toBe(true)
    })

    it('does not set title when column opts out with truncate: false', () => {
      const rows = [{ id: '1', name: 'Some long string value', value: 1 }]
      const cols: Column<TestRow>[] = [
        { key: 'name', header: 'Name', render: row => row.name, truncate: false },
      ]
      const { container } = render(
        <DataTable columns={cols} data={rows} keyFn={r => r.id} />,
      )
      const cell = container.querySelector('tbody td') as HTMLTableCellElement
      expect(cell.getAttribute('title')).toBeNull()
      expect(cell.classList.contains('data-table-cell-truncate')).toBe(false)
    })

    it('does not set title when render returns a ReactNode (non-string)', () => {
      const rows = [{ id: '1', name: 'Alice', value: 1 }]
      const cols: Column<TestRow>[] = [
        {
          key: 'name',
          header: 'Name',
          render: row => <span data-testid="chip">{row.name}</span>,
        },
      ]
      const { container } = render(
        <DataTable columns={cols} data={rows} keyFn={r => r.id} />,
      )
      const cell = container.querySelector('tbody td') as HTMLTableCellElement
      expect(cell.getAttribute('title')).toBeNull()
      expect(cell.classList.contains('data-table-cell-truncate')).toBe(false)
    })
  })

  // --- Column resize ---

  describe('column resize', () => {
    it('renders a resize handle when a column is resizable', () => {
      const cols: Column<TestRow>[] = [
        { key: 'name', header: 'Name', render: row => row.name, resizable: true },
        { key: 'value', header: 'Value', render: row => String(row.value) },
      ]
      const { container } = render(
        <DataTable columns={cols} data={data} keyFn={r => r.id} />,
      )
      const handles = container.querySelectorAll('.data-table-resize-handle')
      expect(handles).toHaveLength(1)
      expect(handles[0].getAttribute('role')).toBe('separator')
      expect(handles[0].getAttribute('aria-orientation')).toBe('vertical')
    })

    it('does not render a handle when resizable is not set', () => {
      const { container } = render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} />,
      )
      expect(container.querySelectorAll('.data-table-resize-handle')).toHaveLength(0)
    })

    it('adjusts width via ArrowRight and persists to localStorage when tableId is provided', () => {
      const tableId = 'test-resize'
      const storage = `reactor-admin-datatable-${tableId}-widths`
      window.localStorage.removeItem(storage)
      const cols: Column<TestRow>[] = [
        {
          key: 'name',
          header: 'Name',
          render: row => row.name,
          resizable: true,
          width: '120px',
        },
      ]
      const { container } = render(
        <DataTable columns={cols} data={data} keyFn={r => r.id} tableId={tableId} />,
      )
      const handle = container.querySelector('.data-table-resize-handle') as HTMLElement
      expect(handle).toBeTruthy()
      fireEvent.keyDown(handle, { key: 'ArrowRight' })

      const raw = window.localStorage.getItem(storage)
      expect(raw).not.toBeNull()
      const parsed = JSON.parse(raw ?? '{}') as Record<string, number>
      expect(typeof parsed.name).toBe('number')
      expect(parsed.name).toBeGreaterThan(0)
      window.localStorage.removeItem(storage)
    })

    it('shrinks width via ArrowLeft (keyboard)', () => {
      const tableId = 'test-resize-shrink'
      const storage = `reactor-admin-datatable-${tableId}-widths`
      window.localStorage.setItem(storage, JSON.stringify({ name: 200 }))
      const cols: Column<TestRow>[] = [
        { key: 'name', header: 'Name', render: row => row.name, resizable: true },
      ]
      const { container } = render(
        <DataTable columns={cols} data={data} keyFn={r => r.id} tableId={tableId} />,
      )
      const handle = container.querySelector('.data-table-resize-handle') as HTMLElement
      fireEvent.keyDown(handle, { key: 'ArrowLeft' })
      const raw = window.localStorage.getItem(storage)
      const parsed = JSON.parse(raw ?? '{}') as Record<string, number>
      expect(parsed.name).toBe(190)
      window.localStorage.removeItem(storage)
    })

    it('does not write to localStorage when tableId is omitted', () => {
      const spy = vi.spyOn(Storage.prototype, 'setItem')
      const cols: Column<TestRow>[] = [
        { key: 'name', header: 'Name', render: row => row.name, resizable: true },
      ]
      const { container } = render(
        <DataTable columns={cols} data={data} keyFn={r => r.id} />,
      )
      const handle = container.querySelector('.data-table-resize-handle') as HTMLElement
      fireEvent.keyDown(handle, { key: 'ArrowRight' })
      const calls = spy.mock.calls.filter(([key]) =>
        typeof key === 'string' && key.startsWith('reactor-admin-datatable-'),
      )
      expect(calls).toHaveLength(0)
      spy.mockRestore()
    })

    it('restores persisted widths on mount when tableId is provided', () => {
      const tableId = 'test-resize-restore'
      const storage = `reactor-admin-datatable-${tableId}-widths`
      window.localStorage.setItem(storage, JSON.stringify({ name: 321 }))
      const cols: Column<TestRow>[] = [
        { key: 'name', header: 'Name', render: row => row.name, resizable: true },
      ]
      const { container } = render(
        <DataTable columns={cols} data={data} keyFn={r => r.id} tableId={tableId} />,
      )
      const th = container.querySelector('th') as HTMLTableCellElement
      expect(th.style.width).toBe('321px')
      window.localStorage.removeItem(storage)
    })

    it('clamps resized width to a minimum and never shrinks below it', () => {
      const tableId = 'test-resize-clamp'
      const storage = `reactor-admin-datatable-${tableId}-widths`
      window.localStorage.setItem(storage, JSON.stringify({ name: 50 }))
      const cols: Column<TestRow>[] = [
        { key: 'name', header: 'Name', render: row => row.name, resizable: true },
      ]
      const { container } = render(
        <DataTable columns={cols} data={data} keyFn={r => r.id} tableId={tableId} />,
      )
      const handle = container.querySelector('.data-table-resize-handle') as HTMLElement
      // Press ArrowLeft multiple times to attempt to go below the minimum.
      for (let i = 0; i < 10; i += 1) {
        fireEvent.keyDown(handle, { key: 'ArrowLeft' })
      }
      const raw = window.localStorage.getItem(storage)
      const parsed = JSON.parse(raw ?? '{}') as Record<string, number>
      expect(parsed.name).toBeGreaterThanOrEqual(40)
      window.localStorage.removeItem(storage)
    })
  })

  // --- Keyboard navigation for rows ---

  describe('row keyboard navigation', () => {
    it('rows with onRowClick have role="button" and tabIndex=0', () => {
      const { container } = render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} onRowClick={vi.fn()} />,
      )
      const rows = container.querySelectorAll('tbody tr')
      rows.forEach(row => {
        expect(row.getAttribute('role')).toBe('button')
        expect(row.getAttribute('tabindex')).toBe('0')
      })
    })

    it('rows without onRowClick do not have role or tabIndex', () => {
      const { container } = render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} />,
      )
      const rows = container.querySelectorAll('tbody tr')
      rows.forEach(row => {
        expect(row.getAttribute('role')).toBeNull()
        expect(row.getAttribute('tabindex')).toBeNull()
      })
    })

    it('activates row via Enter key', () => {
      const onClick = vi.fn()
      render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} onRowClick={onClick} />,
      )
      const firstRow = screen.getByText('Alice').closest('tr') as HTMLElement
      fireEvent.keyDown(firstRow, { key: 'Enter' })
      expect(onClick).toHaveBeenCalledWith(data[0])
    })

    it('activates row via Space key', () => {
      const onClick = vi.fn()
      render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} onRowClick={onClick} />,
      )
      const firstRow = screen.getByText('Alice').closest('tr') as HTMLElement
      fireEvent.keyDown(firstRow, { key: ' ' })
      expect(onClick).toHaveBeenCalledWith(data[0])
    })
  })

  // --- Responsive column drop (responsivePriority) ---

  describe('responsivePriority (narrow viewport behaviour)', () => {
    /** Override window.matchMedia to simulate a narrow viewport before render. */
    function mockNarrowViewport(matches: boolean) {
      const listeners = new Set<(e: { matches: boolean }) => void>()
      const mql = {
        matches,
        media: '(max-width: 900px)',
        addEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.add(cb),
        removeEventListener: (_: string, cb: (e: { matches: boolean }) => void) => listeners.delete(cb),
        // Legacy fallback methods intentionally omitted; modern path is exercised.
        addListener: () => {},
        removeListener: () => {},
        onchange: null,
        dispatchEvent: () => true,
      }
      Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        writable: true,
        value: vi.fn().mockReturnValue(mql),
      })
      Object.defineProperty(window, 'innerWidth', {
        configurable: true,
        writable: true,
        value: matches ? 800 : 1200,
      })
    }

    const priorityColumns: Column<TestRow>[] = [
      { key: 'name', header: 'Name', render: row => row.name },
      { key: 'value', header: 'Value', render: row => String(row.value), responsivePriority: 3 },
    ]

    it('renders all columns on wide viewports (no expander column)', () => {
      mockNarrowViewport(false)
      const { container } = render(
        <DataTable columns={priorityColumns} data={data} keyFn={r => r.id} />,
      )
      expect(container.querySelector('.data-table-expander-col')).toBeNull()
      expect(container.querySelector('.data-table-expander')).toBeNull()
      // Both headers rendered in main table
      expect(screen.getByText('Name')).toBeInTheDocument()
      expect(screen.getByText('Value')).toBeInTheDocument()
    })

    it('hides low-priority columns and renders expander column when narrow', () => {
      mockNarrowViewport(true)
      const { container } = render(
        <DataTable columns={priorityColumns} data={data} keyFn={r => r.id} />,
      )
      expect(container.querySelector('.data-table-expander-col')).toBeTruthy()
      // Low-priority 'Value' header should not appear in the visible thead.
      const headers = Array.from(container.querySelectorAll('thead th')).map(h => h.textContent?.trim())
      expect(headers).toContain('Name')
      expect(headers.filter(h => h === 'Value')).toHaveLength(0)
    })

    it('does not render expander column when no column opts in', () => {
      mockNarrowViewport(true)
      const { container } = render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} />,
      )
      expect(container.querySelector('.data-table-expander-col')).toBeNull()
    })

    it('expander reveals hidden cell values when clicked', () => {
      mockNarrowViewport(true)
      const { container } = render(
        <DataTable columns={priorityColumns} data={data} keyFn={r => r.id} />,
      )
      const expanders = container.querySelectorAll('.data-table-expander')
      expect(expanders.length).toBe(data.length)

      // No expanded row visible before clicking.
      expect(container.querySelector('.data-table-expanded-row')).toBeNull()

      fireEvent.click(expanders[0])
      const expanded = container.querySelector('.data-table-expanded-row')
      expect(expanded).toBeTruthy()
      // Hidden column name + its rendered value appear inside the expander.
      expect(expanded?.textContent).toContain('Value')
      expect(expanded?.textContent).toContain('100')
    })

    it('expander button has aria-expanded reflecting state', () => {
      mockNarrowViewport(true)
      const { container } = render(
        <DataTable columns={priorityColumns} data={data} keyFn={r => r.id} />,
      )
      const firstExpander = container.querySelector('.data-table-expander') as HTMLButtonElement
      expect(firstExpander.getAttribute('aria-expanded')).toBe('false')
      fireEvent.click(firstExpander)
      expect(firstExpander.getAttribute('aria-expanded')).toBe('true')
    })

    it('expander click does not trigger row onRowClick (stopPropagation)', () => {
      mockNarrowViewport(true)
      const onClick = vi.fn()
      const { container } = render(
        <DataTable
          columns={priorityColumns}
          data={data}
          keyFn={r => r.id}
          onRowClick={onClick}
        />,
      )
      const firstExpander = container.querySelector('.data-table-expander') as HTMLButtonElement
      fireEvent.click(firstExpander)
      expect(onClick).not.toHaveBeenCalled()
    })
  })

  // --- Export menu (exportable prop) ---

  describe('exportable menu', () => {
    it('renders the toolbar trigger when exportable is provided', () => {
      const { container } = render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          exportable={{ filename: 'rows' }}
        />,
      )
      const trigger = container.querySelector('.data-table-export-menu__trigger')
      expect(trigger).not.toBeNull()
      expect(trigger).not.toBeDisabled()
    })

    it('disables the trigger when there are no rows to export', () => {
      const { container } = render(
        <DataTable
          columns={columns}
          data={[]}
          keyFn={r => r.id}
          exportable={{ filename: 'rows' }}
        />,
      )
      const trigger = container.querySelector('.data-table-export-menu__trigger') as HTMLButtonElement
      expect(trigger).toBeDisabled()
    })

    it('opens the menu and triggers download on CSV pick', async () => {
      const downloadModule = await import('../../lib/downloadFile')
      const spy = vi.spyOn(downloadModule, 'downloadFile').mockImplementation(() => undefined)
      try {
        const { container } = render(
          <DataTable
            columns={columns}
            data={data}
            keyFn={r => r.id}
            exportable={{ filename: 'rows' }}
          />,
        )
        const trigger = container.querySelector('.data-table-export-menu__trigger') as HTMLButtonElement
        fireEvent.click(trigger)
        const csvItem = screen.getByRole('menuitem', { name: /csv/i })
        fireEvent.click(csvItem)
        expect(spy).toHaveBeenCalledTimes(1)
        const [, filename, mime] = spy.mock.calls[0] as [unknown, string, string]
        expect(filename).toMatch(/^rows-\d{4}-\d{2}-\d{2}\.csv$/)
        expect(mime).toContain('text/csv')
      } finally {
        spy.mockRestore()
      }
    })

    it('skips columns flagged with excludeFromExport when deriving columns', async () => {
      const downloadModule = await import('../../lib/downloadFile')
      const spy = vi.spyOn(downloadModule, 'downloadFile').mockImplementation(() => undefined)
      try {
        const colsWithSelect: Column<TestRow>[] = [
          { key: 'select', header: 'Select', render: () => '☐', excludeFromExport: true },
          ...columns,
        ]
        const { container } = render(
          <DataTable
            columns={colsWithSelect}
            data={data}
            keyFn={r => r.id}
            exportable={{ filename: 'rows' }}
          />,
        )
        fireEvent.click(container.querySelector('.data-table-export-menu__trigger') as HTMLButtonElement)
        fireEvent.click(screen.getByRole('menuitem', { name: /json/i }))
        const [payload] = spy.mock.calls[0] as [string]
        const parsed = JSON.parse(payload) as Array<Record<string, unknown>>
        expect(Object.keys(parsed[0])).not.toContain('select')
        expect(Object.keys(parsed[0])).toContain('name')
      } finally {
        spy.mockRestore()
      }
    })
  })
  describe('rowActions (context menu integration)', () => {
    const baseActions = (perform = vi.fn()) => [
      { id: 'copy', label: 'Copy ID', perform },
      { id: 'open', label: 'Open detail', perform: vi.fn() },
    ]

    it('renders no trigger column when rowActions is omitted', () => {
      const { container } = render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} />,
      )
      expect(container.querySelector('.data-table-row-trigger-cell')).toBeNull()
      expect(container.querySelector('.data-table-row-trigger')).toBeNull()
    })

    it('renders a trigger button per row when rowActions is provided', () => {
      const { container } = render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} rowActions={baseActions()} />,
      )
      const triggers = container.querySelectorAll('.data-table-row-trigger')
      expect(triggers).toHaveLength(data.length)
    })

    it('right-click on a row opens the context menu', () => {
      render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} rowActions={baseActions()} />,
      )
      const firstRow = screen.getByText('Alice').closest('tr') as HTMLElement
      fireEvent.contextMenu(firstRow, { clientX: 100, clientY: 200 })
      const menu = document.body.querySelector('.row-context-menu')
      expect(menu).toBeTruthy()
      expect(menu?.textContent).toContain('Copy ID')
    })

    it('Shift+Enter on a focused row opens the menu', () => {
      render(
        <DataTable columns={columns} data={data} keyFn={r => r.id} rowActions={baseActions()} />,
      )
      const firstRow = screen.getByText('Alice').closest('tr') as HTMLElement
      fireEvent.keyDown(firstRow, { key: 'Enter', shiftKey: true })
      const menu = document.body.querySelector('.row-context-menu')
      expect(menu).toBeTruthy()
    })

    it('plain Enter on a focused row still triggers onRowClick (Shift gates the menu)', () => {
      const onClick = vi.fn()
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          onRowClick={onClick}
          rowActions={baseActions()}
        />,
      )
      const firstRow = screen.getByText('Alice').closest('tr') as HTMLElement
      fireEvent.keyDown(firstRow, { key: 'Enter' })
      expect(onClick).toHaveBeenCalledWith(data[0])
      expect(document.body.querySelector('.row-context-menu')).toBeNull()
    })

    it('clicking the row trigger button opens the menu without triggering onRowClick', () => {
      const onClick = vi.fn()
      const { container } = render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          onRowClick={onClick}
          rowActions={baseActions()}
        />,
      )
      const trigger = container.querySelector('.data-table-row-trigger') as HTMLButtonElement
      fireEvent.click(trigger)
      expect(document.body.querySelector('.row-context-menu')).toBeTruthy()
      expect(onClick).not.toHaveBeenCalled()
    })

    it('selecting an action invokes perform with the row data', () => {
      const performMock = vi.fn()
      render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          rowActions={baseActions(performMock)}
        />,
      )
      const firstRow = screen.getByText('Alice').closest('tr') as HTMLElement
      fireEvent.contextMenu(firstRow, { clientX: 50, clientY: 50 })
      const item = document.body.querySelector('[data-action-id="copy"]') as HTMLButtonElement
      fireEvent.click(item)
      expect(performMock).toHaveBeenCalledWith(data[0])
    })
  })

  // --- Page-size selector (pageSizeOptions opt-in) ---

  describe('page-size selector', () => {
    /**
     * Helper that renders DataTable inside a state-bearing host so the table
     * can drive `page` / `pageSize` updates back through `onPageChange` /
     * `onPageSizeChange`. Mirrors how real callers (AuditLogManager,
     * FeedbackManager) wire the props.
     */
    function renderWithStatefulHost(props: {
      pageSizeOptions?: number[]
      defaultPageSize?: number
      tableId?: string
      urlStateKey?: string
      initialEntry?: string
      initialPage?: number
    }) {
      const initialPage = props.initialPage ?? 1
      const initialSize = props.defaultPageSize ?? 25
      const onPageChangeSpy = vi.fn()
      const onPageSizeChangeSpy = vi.fn()
      // Track the most recent value the spies were called with so tests can
      // assert "what does the host think the current page/size is now?".
      // Defaults to the initial seed so reads before any callback are valid.
      const getLatest = (spy: ReturnType<typeof vi.fn>, fallback: number): number => {
        const calls = spy.mock.calls
        if (calls.length === 0) return fallback
        return calls[calls.length - 1][0] as number
      }

      function Host() {
        const [page, setPage] = useState(initialPage)
        const [size, setSize] = useState(initialSize)
        return (
          <DataTable
            columns={columns}
            data={data}
            keyFn={r => r.id}
            page={page}
            pageSize={size}
            totalCount={120}
            onPageChange={(p) => {
              onPageChangeSpy(p)
              setPage(p)
            }}
            pageSizeOptions={props.pageSizeOptions}
            defaultPageSize={props.defaultPageSize}
            onPageSizeChange={(s) => {
              onPageSizeChangeSpy(s)
              setSize(s)
            }}
            tableId={props.tableId}
            urlStateKey={props.urlStateKey}
          />
        )
      }

      if (props.urlStateKey) {
        const router = createMemoryRouter(
          [{ path: '/', element: <Host /> }],
          { initialEntries: [props.initialEntry ?? '/'] },
        )
        const view = render(<RouterProvider router={router} />)
        return {
          ...view,
          getSearch: () => router.state.location.search,
          onPageChangeSpy,
          onPageSizeChangeSpy,
          getCurrentSize: () => getLatest(onPageSizeChangeSpy, initialSize),
          getCurrentPage: () => getLatest(onPageChangeSpy, initialPage),
        }
      }

      const view = render(<Host />)
      return {
        ...view,
        getSearch: () => '',
        onPageChangeSpy,
        onPageSizeChangeSpy,
        getCurrentSize: () => getLatest(onPageSizeChangeSpy, initialSize),
        getCurrentPage: () => getLatest(onPageChangeSpy, initialPage),
      }
    }

    afterEach(() => {
      // Defensive cleanup so persisted preferences do not leak across tests.
      const ids = ['ps-storage', 'ps-no-storage', 'ps-url']
      for (const id of ids) {
        window.localStorage.removeItem(`reactor-admin-datatable-${id}-pageSize`)
      }
    })

    it('does not render the selector when pageSizeOptions is omitted', () => {
      const { container } = render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          page={1}
          pageSize={2}
          totalCount={5}
          onPageChange={vi.fn()}
        />,
      )
      expect(container.querySelector('.table-pagination__page-size')).toBeNull()
    })

    it('renders the selector when pageSizeOptions is provided', () => {
      const { container } = renderWithStatefulHost({
        pageSizeOptions: [10, 25, 50, 100],
        defaultPageSize: 25,
      })
      const wrapper = container.querySelector('.table-pagination__page-size')
      expect(wrapper).not.toBeNull()
      const select = wrapper?.querySelector('select') as HTMLSelectElement
      expect(select).not.toBeNull()
      const labels = Array.from(select.options).map((opt) => opt.value)
      expect(labels).toEqual(['10', '25', '50', '100'])
      expect(select.value).toBe('25')
    })

    it('selecting a new size emits onPageSizeChange and resets page to 1', () => {
      const { container, onPageChangeSpy, onPageSizeChangeSpy, getCurrentPage, getCurrentSize } =
        renderWithStatefulHost({
          pageSizeOptions: [10, 25, 50, 100],
          defaultPageSize: 25,
          initialPage: 3,
        })
      const select = container.querySelector(
        '.table-pagination__page-size-select',
      ) as HTMLSelectElement
      fireEvent.change(select, { target: { value: '50' } })
      expect(onPageSizeChangeSpy).toHaveBeenCalledWith(50)
      expect(onPageChangeSpy).toHaveBeenCalledWith(1)
      expect(getCurrentSize()).toBe(50)
      expect(getCurrentPage()).toBe(1)
    })

    it('persists the selected size to localStorage when tableId is provided', () => {
      const tableId = 'ps-storage'
      const storage = `reactor-admin-datatable-${tableId}-pageSize`
      window.localStorage.removeItem(storage)
      const { container } = renderWithStatefulHost({
        pageSizeOptions: [10, 25, 50, 100],
        defaultPageSize: 25,
        tableId,
      })
      const select = container.querySelector(
        '.table-pagination__page-size-select',
      ) as HTMLSelectElement
      fireEvent.change(select, { target: { value: '100' } })
      expect(window.localStorage.getItem(storage)).toBe('100')
    })

    it('does not write to localStorage when tableId is omitted', () => {
      const spy = vi.spyOn(Storage.prototype, 'setItem')
      const { container } = renderWithStatefulHost({
        pageSizeOptions: [10, 25, 50, 100],
        defaultPageSize: 25,
      })
      const select = container.querySelector(
        '.table-pagination__page-size-select',
      ) as HTMLSelectElement
      fireEvent.change(select, { target: { value: '50' } })
      const calls = spy.mock.calls.filter(([key]) =>
        typeof key === 'string' && key.endsWith('-pageSize'),
      )
      expect(calls).toHaveLength(0)
      spy.mockRestore()
    })

    it('seeds the initial size from localStorage on mount', () => {
      const tableId = 'ps-storage'
      const storage = `reactor-admin-datatable-${tableId}-pageSize`
      window.localStorage.setItem(storage, '50')
      const { onPageSizeChangeSpy, getCurrentSize } = renderWithStatefulHost({
        pageSizeOptions: [10, 25, 50, 100],
        defaultPageSize: 25,
        tableId,
      })
      expect(onPageSizeChangeSpy).toHaveBeenCalledWith(50)
      expect(getCurrentSize()).toBe(50)
    })

    it('writes the URL param when urlStateKey is provided', async () => {
      const { container, getSearch } = renderWithStatefulHost({
        pageSizeOptions: [10, 25, 50, 100],
        defaultPageSize: 25,
        urlStateKey: 'ps',
      })
      const select = container.querySelector(
        '.table-pagination__page-size-select',
      ) as HTMLSelectElement
      fireEvent.change(select, { target: { value: '100' } })
      // Allow the URL bridge effect to flush.
      await Promise.resolve()
      expect(getSearch()).toContain('ps_ps=100')
    })

    it('seeds initial size from URL param when present', () => {
      const { onPageSizeChangeSpy, getCurrentSize } = renderWithStatefulHost({
        pageSizeOptions: [10, 25, 50, 100],
        defaultPageSize: 25,
        urlStateKey: 'ps',
        initialEntry: '/?ps_ps=50',
      })
      expect(onPageSizeChangeSpy).toHaveBeenCalledWith(50)
      expect(getCurrentSize()).toBe(50)
    })
  })

  // ── Bulk row selection ──

  describe('bulk selection', () => {
    type BulkAction = NonNullable<
      Parameters<typeof DataTable<TestRow>>[0]['bulkActions']
    >[number]

    function renderTable(
      overrides: Partial<Parameters<typeof DataTable<TestRow>>[0]> = {},
    ) {
      return render(
        <DataTable
          columns={columns}
          data={data}
          keyFn={r => r.id}
          selectable
          {...overrides}
        />,
      )
    }

    it('renders a leading checkbox column when selectable=true', () => {
      const { container } = renderTable()
      const headerCheckbox = container.querySelector(
        '.data-table-select-col input[type="checkbox"]',
      )
      expect(headerCheckbox).not.toBeNull()
      const rowCheckboxes = container.querySelectorAll(
        '.data-table-select-cell input[type="checkbox"]',
      )
      expect(rowCheckboxes).toHaveLength(data.length)
    })

    it('does not render the bulk bar until at least one row is selected', () => {
      const { container } = renderTable({
        bulkActions: [{ id: 'noop', label: 'Noop', perform: () => {} }],
      })
      expect(container.querySelector('.data-table-bulk-bar')).toBeNull()
      const firstCheckbox = container.querySelector(
        '.data-table-select-cell input[type="checkbox"]',
      ) as HTMLInputElement
      fireEvent.click(firstCheckbox)
      expect(container.querySelector('.data-table-bulk-bar')).not.toBeNull()
      expect(screen.getByText(/1 selected/)).toBeInTheDocument()
    })

    it('toggles individual row selection on checkbox click', () => {
      const { container } = renderTable()
      const cb = container.querySelectorAll(
        '.data-table-select-cell input[type="checkbox"]',
      )[1] as HTMLInputElement
      fireEvent.click(cb)
      expect(cb.checked).toBe(true)
      fireEvent.click(cb)
      expect(cb.checked).toBe(false)
    })

    it('select-all checkbox toggles every selectable row', () => {
      const { container } = renderTable()
      const headerCb = container.querySelector(
        '.data-table-select-col input[type="checkbox"]',
      ) as HTMLInputElement
      fireEvent.click(headerCb)
      const rowCheckboxes = container.querySelectorAll(
        '.data-table-select-cell input[type="checkbox"]',
      ) as NodeListOf<HTMLInputElement>
      rowCheckboxes.forEach(cb => expect(cb.checked).toBe(true))
      // Selected count surfaces in the bulk bar.
      expect(screen.getByText(/3 selected/)).toBeInTheDocument()
      // Toggle off.
      fireEvent.click(headerCb)
      const cleared = container.querySelectorAll(
        '.data-table-select-cell input[type="checkbox"]',
      ) as NodeListOf<HTMLInputElement>
      cleared.forEach(cb => expect(cb.checked).toBe(false))
    })

    it('applies indeterminate state when some but not all rows are selected', () => {
      const { container } = renderTable()
      const firstRow = container.querySelector(
        '.data-table-select-cell input[type="checkbox"]',
      ) as HTMLInputElement
      fireEvent.click(firstRow)
      const headerCb = container.querySelector(
        '.data-table-select-col input[type="checkbox"]',
      ) as HTMLInputElement
      expect(headerCb.indeterminate).toBe(true)
      expect(headerCb.checked).toBe(false)
    })

    it('Shift+Click extends selection across the contiguous range', () => {
      const { container } = renderTable()
      const cbs = container.querySelectorAll(
        '.data-table-select-cell input[type="checkbox"]',
      ) as NodeListOf<HTMLInputElement>
      fireEvent.click(cbs[0])
      // Shift+Click on the third row should select 0..2 inclusive.
      fireEvent.click(cbs[2], { shiftKey: true })
      expect(cbs[0].checked).toBe(true)
      expect(cbs[1].checked).toBe(true)
      expect(cbs[2].checked).toBe(true)
    })

    it('rowSelectable=false renders the row checkbox disabled and skips select-all', () => {
      const { container } = renderTable({
        rowSelectable: row => row.id !== '2',
      })
      const cbs = container.querySelectorAll(
        '.data-table-select-cell input[type="checkbox"]',
      ) as NodeListOf<HTMLInputElement>
      expect(cbs[1].disabled).toBe(true)
      // Select-all only flips the selectable rows.
      const headerCb = container.querySelector(
        '.data-table-select-col input[type="checkbox"]',
      ) as HTMLInputElement
      fireEvent.click(headerCb)
      expect(cbs[0].checked).toBe(true)
      expect(cbs[1].checked).toBe(false)
      expect(cbs[2].checked).toBe(true)
    })

    it('invokes the bulk action with the selected rows and clears selection', async () => {
      const perform = vi.fn().mockResolvedValue(undefined)
      const action: BulkAction = { id: 'noop', label: 'Noop', perform }
      const { container } = renderTable({ bulkActions: [action] })
      const cbs = container.querySelectorAll(
        '.data-table-select-cell input[type="checkbox"]',
      ) as NodeListOf<HTMLInputElement>
      fireEvent.click(cbs[0])
      fireEvent.click(cbs[2])
      const button = screen.getByRole('button', { name: /Noop/i })
      fireEvent.click(button)
      // perform receives the selected rows in original data order.
      await waitFor(() => expect(perform).toHaveBeenCalledTimes(1))
      const rowsArg = perform.mock.calls[0][0] as TestRow[]
      expect(rowsArg.map(r => r.id)).toEqual(['1', '3'])
      // Bulk bar disappears once selection is cleared.
      await waitFor(() => {
        expect(container.querySelector('.data-table-bulk-bar')).toBeNull()
      })
    })

    it('shows a confirm dialog when action.confirmMessage returns a string', () => {
      const perform = vi.fn()
      const action: BulkAction = {
        id: 'danger',
        label: 'Delete',
        variant: 'danger',
        perform,
        confirmMessage: rows => `Delete ${rows.length} rows?`,
      }
      const { container } = renderTable({ bulkActions: [action] })
      const cb = container.querySelector(
        '.data-table-select-cell input[type="checkbox"]',
      ) as HTMLInputElement
      fireEvent.click(cb)
      const trigger = screen.getByRole('button', { name: /Delete/i })
      fireEvent.click(trigger)
      // Dialog is portaled to document.body — search globally.
      expect(screen.getByText('Delete 1 rows?')).toBeInTheDocument()
      // perform is NOT called yet — waiting for confirmation.
      expect(perform).not.toHaveBeenCalled()
    })

    it('clear selection button empties the bulk bar', () => {
      const { container } = renderTable()
      const headerCb = container.querySelector(
        '.data-table-select-col input[type="checkbox"]',
      ) as HTMLInputElement
      fireEvent.click(headerCb)
      const clearBtn = screen.getByRole('button', { name: /Clear selection/i })
      fireEvent.click(clearBtn)
      expect(container.querySelector('.data-table-bulk-bar')).toBeNull()
    })

    it('Space toggles the row checkbox via keyboard', () => {
      const { container } = renderTable()
      const cb = container.querySelector(
        '.data-table-select-cell input[type="checkbox"]',
      ) as HTMLInputElement
      fireEvent.keyDown(cb, { key: ' ' })
      expect(cb.checked).toBe(true)
      fireEvent.keyDown(cb, { key: ' ' })
      expect(cb.checked).toBe(false)
    })
  })
})

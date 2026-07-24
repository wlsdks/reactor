import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import {
  Skeleton,
  SkeletonText,
  SkeletonCard,
  SkeletonTable,
  SkeletonChart,
} from '../Skeleton'

describe('Skeleton', () => {
  it('renders with accessible loading label', () => {
    render(<Skeleton />)
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
  })

  it('applies width, height, and radius as inline styles', () => {
    const { container } = render(
      <Skeleton width={120} height={18} radius={8} />,
    )
    const node = container.querySelector('.skeleton-base') as HTMLElement
    expect(node).not.toBeNull()
    expect(node.style.width).toBe('120px')
    expect(node.style.height).toBe('18px')
    expect(node.style.borderRadius).toBe('8px')
  })

  it('accepts string dimensions (e.g. percentages)', () => {
    const { container } = render(<Skeleton width="60%" height="2rem" />)
    const node = container.querySelector('.skeleton-base') as HTMLElement
    expect(node.style.width).toBe('60%')
    expect(node.style.height).toBe('2rem')
  })

  it('sets aria-busy="true" for assistive tech', () => {
    const { container } = render(<Skeleton />)
    const node = container.querySelector('.skeleton-base')
    expect(node?.getAttribute('aria-busy')).toBe('true')
  })

  it('supports inline variant via inline prop', () => {
    const { container } = render(<Skeleton inline />)
    const node = container.querySelector('.skeleton-base')
    expect(node?.classList.contains('skeleton-base--inline')).toBe(true)
  })

  it('merges caller className', () => {
    const { container } = render(<Skeleton className="my-custom" />)
    const node = container.querySelector('.skeleton-base')
    expect(node?.classList.contains('my-custom')).toBe(true)
  })
})

describe('SkeletonText', () => {
  it('renders a single line by default', () => {
    const { container } = render(<SkeletonText />)
    const lines = container.querySelectorAll('.skeleton-base')
    expect(lines).toHaveLength(1)
  })

  it('renders the requested number of lines', () => {
    const { container } = render(<SkeletonText lines={4} />)
    const lines = container.querySelectorAll('.skeleton-base')
    expect(lines).toHaveLength(4)
  })

  it('applies lastLineWidth only to the final line', () => {
    const { container } = render(
      <SkeletonText lines={3} width="100%" lastLineWidth="40%" />,
    )
    const lines = container.querySelectorAll<HTMLElement>('.skeleton-base')
    expect(lines[0].style.width).toBe('100%')
    expect(lines[1].style.width).toBe('100%')
    expect(lines[2].style.width).toBe('40%')
  })
})

describe('SkeletonCard', () => {
  it('renders with default height of 80px', () => {
    const { container } = render(<SkeletonCard />)
    const card = container.querySelector('.skeleton-card') as HTMLElement
    expect(card).not.toBeNull()
    expect(card.style.height).toBe('80px')
  })

  it('accepts a custom height', () => {
    const { container } = render(<SkeletonCard height={200} />)
    const card = container.querySelector('.skeleton-card') as HTMLElement
    expect(card.style.height).toBe('200px')
  })

  it('renders a single card by default (count=1)', () => {
    const { container } = render(<SkeletonCard />)
    expect(container.querySelectorAll('.skeleton-card')).toHaveLength(1)
  })

  it('renders the requested number of cards via count prop', () => {
    const { container } = render(<SkeletonCard count={4} height={72} />)
    const cards = container.querySelectorAll<HTMLElement>('.skeleton-card')
    expect(cards).toHaveLength(4)
    cards.forEach((card) => {
      expect(card.style.height).toBe('72px')
    })
  })

  it('treats count<=1 as a single card (no fragment overhead)', () => {
    const { container } = render(<SkeletonCard count={0} />)
    expect(container.querySelectorAll('.skeleton-card')).toHaveLength(1)
  })
})

describe('SkeletonTable', () => {
  it('renders with default 6 rows and 4 columns', () => {
    const { container } = render(<SkeletonTable />)
    const rows = container.querySelectorAll('.skeleton-table-v2__row')
    expect(rows).toHaveLength(6)
    // Header row cells
    const headerCells = container.querySelectorAll(
      '.skeleton-table-v2__header .skeleton-table-v2__cell',
    )
    expect(headerCells).toHaveLength(4)
  })

  it('renders the requested row and column counts', () => {
    const { container } = render(<SkeletonTable rows={3} columns={2} />)
    const rows = container.querySelectorAll('.skeleton-table-v2__row')
    expect(rows).toHaveLength(3)
    const headerCells = container.querySelectorAll(
      '.skeleton-table-v2__header .skeleton-table-v2__cell',
    )
    expect(headerCells).toHaveLength(2)
    // Each row has the expected number of cells
    rows.forEach((row) => {
      expect(row.querySelectorAll('.skeleton-table-v2__cell')).toHaveLength(2)
    })
  })

  it('has aria-busy on the root', () => {
    const { container } = render(<SkeletonTable />)
    const root = container.querySelector('.skeleton-table-v2')
    expect(root?.getAttribute('aria-busy')).toBe('true')
  })
})

describe('SkeletonChart', () => {
  it('renders with default height of 280px', () => {
    const { container } = render(<SkeletonChart />)
    const chart = container.querySelector('.skeleton-chart') as HTMLElement
    expect(chart).not.toBeNull()
    expect(chart.style.height).toBe('280px')
  })

  it('accepts a custom height', () => {
    const { container } = render(<SkeletonChart height={160} />)
    const chart = container.querySelector('.skeleton-chart') as HTMLElement
    expect(chart.style.height).toBe('160px')
  })

  it('renders 12 skeleton bars', () => {
    const { container } = render(<SkeletonChart />)
    const bars = container.querySelectorAll('.skeleton-chart__bar')
    expect(bars).toHaveLength(12)
  })

  it('has aria-busy on the root', () => {
    const { container } = render(<SkeletonChart />)
    const root = container.querySelector('.skeleton-chart')
    expect(root?.getAttribute('aria-busy')).toBe('true')
  })
})

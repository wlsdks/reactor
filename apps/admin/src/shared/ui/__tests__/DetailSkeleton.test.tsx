import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { DetailSkeleton } from '../DetailSkeleton'

describe('DetailSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = render(<DetailSkeleton />)
    expect(container.firstChild).not.toBeNull()
  })

  it('has aria-busy attribute set to true', () => {
    const { container } = render(<DetailSkeleton />)
    const root = container.querySelector('.skeleton-detail')
    expect(root).not.toBeNull()
    expect(root?.getAttribute('aria-busy')).toBe('true')
  })

  it('has accessible loading label', () => {
    render(<DetailSkeleton />)
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
  })

  it('renders a title skeleton line', () => {
    const { container } = render(<DetailSkeleton />)
    expect(container.querySelector('.skeleton-detail-title')).not.toBeNull()
  })

  it('renders 3 detail sections', () => {
    const { container } = render(<DetailSkeleton />)
    const sections = container.querySelectorAll('.skeleton-detail-section')
    expect(sections).toHaveLength(3)
  })

  it('each section has label and value skeleton lines', () => {
    const { container } = render(<DetailSkeleton />)
    const labels = container.querySelectorAll('.skeleton-detail-label')
    const values = container.querySelectorAll('.skeleton-detail-value')
    expect(labels).toHaveLength(3)
    expect(values).toHaveLength(3)
  })
})

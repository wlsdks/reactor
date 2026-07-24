import { describe, it, expect } from 'vitest'
import { render } from '../../../test/utils'
import { SparkLine } from '../SparkLine'

describe('SparkLine', () => {
  it('renders without crashing', () => {
    const { container } = render(<SparkLine data={[1, 2, 3, 4, 5]} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders with custom dimensions', () => {
    const { container } = render(
      <SparkLine data={[10, 20, 15]} width={100} height={32} />,
    )
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg?.getAttribute('width')).toBe('100')
    expect(svg?.getAttribute('height')).toBe('32')
  })

  it('renders with default dimensions', () => {
    const { container } = render(<SparkLine data={[1, 2, 3]} />)
    const svg = container.querySelector('svg')
    expect(svg?.getAttribute('width')).toBe('60')
    expect(svg?.getAttribute('height')).toBe('24')
  })

  it('renders with empty data', () => {
    const { container } = render(<SparkLine data={[]} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders with single data point', () => {
    const { container } = render(<SparkLine data={[42]} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('accepts trend prop without crashing', () => {
    const { container: upContainer } = render(
      <SparkLine data={[1, 2, 3]} trend="up" />,
    )
    expect(upContainer.querySelector('svg')).toBeInTheDocument()

    const { container: downContainer } = render(
      <SparkLine data={[3, 2, 1]} trend="down" />,
    )
    expect(downContainer.querySelector('svg')).toBeInTheDocument()

    const { container: flatContainer } = render(
      <SparkLine data={[2, 2, 2]} trend="flat" />,
    )
    expect(flatContainer.querySelector('svg')).toBeInTheDocument()
  })

  it('accepts custom color prop', () => {
    const { container } = render(
      <SparkLine data={[1, 2, 3]} color="#FF0000" />,
    )
    expect(container.querySelector('svg')).toBeInTheDocument()
  })
})

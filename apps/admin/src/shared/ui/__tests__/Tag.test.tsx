import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { Tag } from '../Tag'

describe('Tag', () => {
  it('renders children content', () => {
    render(<Tag>Hello</Tag>)
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })

  it('applies base .tag class only when variant is neutral (default)', () => {
    const { container } = render(<Tag>Neutral</Tag>)
    const span = container.querySelector('span')
    expect(span?.className).toBe('tag')
  })

  it('applies tag--success modifier for success variant', () => {
    const { container } = render(<Tag variant="success">OK</Tag>)
    const span = container.querySelector('span')
    expect(span?.className).toContain('tag')
    expect(span?.className).toContain('tag--success')
  })

  it('applies tag--pill modifier for pill variant', () => {
    const { container } = render(<Tag variant="pill">tag-name</Tag>)
    const span = container.querySelector('span')
    expect(span?.className).toContain('tag--pill')
  })

  it('applies tag--mono when mono prop is true', () => {
    const { container } = render(<Tag mono>code-id</Tag>)
    const span = container.querySelector('span')
    expect(span?.className).toContain('tag--mono')
  })

  it('combines variant and mono modifiers', () => {
    const { container } = render(
      <Tag variant="error" mono>
        ERR-42
      </Tag>,
    )
    const span = container.querySelector('span')
    expect(span?.className).toContain('tag--error')
    expect(span?.className).toContain('tag--mono')
  })

  it('forwards style prop for dynamic per-instance styling', () => {
    const { container } = render(
      <Tag variant="pill" style={{ borderLeft: '3px solid red' }}>
        Custom
      </Tag>,
    )
    const span = container.querySelector('span') as HTMLSpanElement
    expect(span.style.borderLeft).toContain('3px solid')
  })

  it('exposes data-testid for stable test selection', () => {
    render(
      <Tag data-testid="my-tag" variant="info">
        Info
      </Tag>,
    )
    expect(screen.getByTestId('my-tag')).toBeInTheDocument()
  })
})

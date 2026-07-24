import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { TrendBadge } from '../TrendBadge'

describe('TrendBadge', () => {
  it('renders an em-dash and the flat class when value is zero', () => {
    render(<TrendBadge value={0} />)
    const badge = screen.getByTestId('trend-badge')
    expect(badge.className).toContain('trend-flat')
    expect(badge.textContent).toBe('—')
  })

  it('renders +N with the good class for positive values', () => {
    render(<TrendBadge value={3} />)
    const badge = screen.getByTestId('trend-badge')
    expect(badge.className).toContain('trend-good')
    expect(badge.textContent).toBe('+3')
  })

  it('renders -N with the bad class for negative values', () => {
    render(<TrendBadge value={-2} />)
    const badge = screen.getByTestId('trend-badge')
    expect(badge.className).toContain('trend-bad')
    expect(badge.textContent).toBe('-2')
  })

  it('inverts colour intent so a rising value reads as bad', () => {
    render(<TrendBadge value={5} inverse />)
    // Rising issue count is bad → trend-bad despite positive value.
    const badge = screen.getByTestId('trend-badge')
    expect(badge.className).toContain('trend-bad')
    expect(badge.textContent).toBe('+5')
  })

  it('inverts colour intent so a falling value reads as good', () => {
    render(<TrendBadge value={-1} inverse />)
    const badge = screen.getByTestId('trend-badge')
    expect(badge.className).toContain('trend-good')
  })

  it('omits the title attribute when no baselineLabel is supplied', () => {
    render(<TrendBadge value={2} />)
    const badge = screen.getByTestId('trend-badge')
    expect(badge.getAttribute('title')).toBeNull()
    expect(badge.getAttribute('aria-label')).toBeNull()
  })

  it('renders title and aria-label using the tooltipPattern when baselineLabel is supplied', () => {
    render(<TrendBadge value={4} baselineLabel="어제 대비" />)
    const badge = screen.getByTestId('trend-badge')
    // The test i18n harness returns the key string itself, so the title is
    // built from the key (still proves the wiring).
    const title = badge.getAttribute('title')
    expect(title).toBeTruthy()
    expect(title).toContain('+4')
    expect(title).toContain('어제 대비')
    expect(badge.getAttribute('aria-label')).toBe(title)
  })

  it('does not render the caption wrapper by default', () => {
    render(<TrendBadge value={1} baselineLabel="어제 대비" />)
    expect(screen.queryByTestId('trend-badge-caption')).not.toBeInTheDocument()
  })

  it('renders the caption when showCaption is true and baselineLabel is supplied', () => {
    render(
      <TrendBadge value={1} baselineLabel="어제 대비" showCaption />,
    )
    const caption = screen.getByTestId('trend-badge-caption')
    expect(caption.textContent).toBe('어제 대비')
  })

  it('does not render the caption when showCaption is true but baselineLabel is missing', () => {
    render(<TrendBadge value={1} showCaption />)
    expect(screen.queryByTestId('trend-badge-caption')).not.toBeInTheDocument()
  })
})

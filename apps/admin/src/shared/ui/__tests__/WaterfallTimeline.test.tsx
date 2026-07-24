import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { WaterfallTimeline } from '../WaterfallTimeline'
import type { WaterfallSpan } from '../WaterfallTimeline'

const spans: WaterfallSpan[] = [
  { id: '1', parentId: null, name: 'Request', type: 'request', startMs: 0, durationMs: 500, status: 'ok' },
  { id: '2', parentId: '1', name: 'Input Guard', type: 'input_guard', startMs: 10, durationMs: 50, status: 'ok' },
  { id: '3', parentId: '1', name: 'LLM Call', type: 'llm_call', startMs: 60, durationMs: 400, status: 'ok' },
  { id: '4', parentId: '1', name: 'Blocked Guard', type: 'output_guard', startMs: 460, durationMs: 30, status: 'blocked' },
]

describe('WaterfallTimeline', () => {
  it('renders all span names', () => {
    render(<WaterfallTimeline spans={spans} totalDurationMs={500} />)
    expect(screen.getByText('Request')).toBeInTheDocument()
    expect(screen.getByText('Input Guard')).toBeInTheDocument()
    expect(screen.getByText('LLM Call')).toBeInTheDocument()
    expect(screen.getByText('Blocked Guard')).toBeInTheDocument()
  })

  it('renders duration labels', () => {
    render(<WaterfallTimeline spans={spans} totalDurationMs={500} />)
    expect(screen.getByText('500ms')).toBeInTheDocument()
    expect(screen.getByText('50ms')).toBeInTheDocument()
    expect(screen.getByText('400ms')).toBeInTheDocument()
    expect(screen.getByText('30ms')).toBeInTheDocument()
  })

  it('renders as a list', () => {
    render(<WaterfallTimeline spans={spans} totalDurationMs={500} />)
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(4)
  })

  it('applies selected class to selected span', () => {
    const { container } = render(
      <WaterfallTimeline spans={spans} totalDurationMs={500} selectedSpanId="2" />,
    )
    const rows = container.querySelectorAll('.waterfall-row')
    expect(rows[1].classList.contains('waterfall-row--selected')).toBe(true)
    expect(rows[0].classList.contains('waterfall-row--selected')).toBe(false)
  })

  it('applies error class to error/blocked spans', () => {
    const { container } = render(
      <WaterfallTimeline spans={spans} totalDurationMs={500} />,
    )
    const rows = container.querySelectorAll('.waterfall-row')
    expect(rows[3].classList.contains('waterfall-row--error')).toBe(true)
    expect(rows[0].classList.contains('waterfall-row--error')).toBe(false)
  })

  it('calls onSpanClick when a span is clicked', () => {
    const onClick = vi.fn()
    render(
      <WaterfallTimeline spans={spans} totalDurationMs={500} onSpanClick={onClick} />,
    )
    fireEvent.click(screen.getByText('LLM Call'))
    expect(onClick).toHaveBeenCalledWith(spans[2])
  })

  it('calls onSpanClick on Enter key', () => {
    const onClick = vi.fn()
    render(
      <WaterfallTimeline spans={spans} totalDurationMs={500} onSpanClick={onClick} />,
    )
    const row = screen.getByText('Request').closest('.waterfall-row') as HTMLElement
    fireEvent.keyDown(row, { key: 'Enter' })
    expect(onClick).toHaveBeenCalledWith(spans[0])
  })

  it('calls onSpanClick on Space key', () => {
    const onClick = vi.fn()
    render(
      <WaterfallTimeline spans={spans} totalDurationMs={500} onSpanClick={onClick} />,
    )
    const row = screen.getByText('Request').closest('.waterfall-row') as HTMLElement
    fireEvent.keyDown(row, { key: ' ' })
    expect(onClick).toHaveBeenCalledWith(spans[0])
  })

  it('rows are focusable when onSpanClick is provided', () => {
    const { container } = render(
      <WaterfallTimeline spans={spans} totalDurationMs={500} onSpanClick={vi.fn()} />,
    )
    const rows = container.querySelectorAll('.waterfall-row')
    rows.forEach(row => {
      expect(row.getAttribute('tabindex')).toBe('0')
    })
  })

  it('rows are not focusable when onSpanClick is not provided', () => {
    const { container } = render(
      <WaterfallTimeline spans={spans} totalDurationMs={500} />,
    )
    const rows = container.querySelectorAll('.waterfall-row')
    rows.forEach(row => {
      expect(row.getAttribute('tabindex')).toBeNull()
    })
  })

  it('nests child spans with indent', () => {
    const { container } = render(
      <WaterfallTimeline spans={spans} totalDurationMs={500} />,
    )
    const nameElements = container.querySelectorAll('.waterfall-name')
    // Root span (Request) should have 0 indent (depth 0)
    expect((nameElements[0] as HTMLElement).style.paddingLeft).toBe('0px')
    // Child spans should have 16px indent (depth 1)
    expect((nameElements[1] as HTMLElement).style.paddingLeft).toBe('16px')
  })

  it('renders empty list when no spans provided', () => {
    render(<WaterfallTimeline spans={[]} totalDurationMs={100} />)
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.queryAllByRole('listitem')).toHaveLength(0)
  })

  it('formats durations in seconds for large values', () => {
    const largeSpans: WaterfallSpan[] = [
      { id: '1', parentId: null, name: 'Slow', type: 'request', startMs: 0, durationMs: 2500, status: 'ok' },
    ]
    render(<WaterfallTimeline spans={largeSpans} totalDurationMs={3000} />)
    expect(screen.getByText('2.50s')).toBeInTheDocument()
  })
})

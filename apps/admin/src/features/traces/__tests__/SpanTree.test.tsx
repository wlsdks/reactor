import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent } from '@testing-library/react'
import { i18n, render, screen } from '../../../test/utils'
import { SpanTree } from '../ui/SpanTree'
import type { TraceSpan } from '../types'

function buildSpan(overrides: Partial<TraceSpan> = {}): TraceSpan {
  return {
    spanId: 'span_1',
    parentSpanId: null,
    operationName: 'op',
    serviceName: 'svc',
    durationMs: 100,
    success: true,
    errorClass: null,
    attributes: {},
    time: 0,
    ...overrides,
  }
}

const BASE_TIME = 1_700_000_000_000

function threeLevels(): TraceSpan[] {
  // root
  //  ├─ guard (ok)
  //  └─ llm
  //       └─ tool (error)
  return [
    buildSpan({
      spanId: 'root',
      parentSpanId: null,
      operationName: 'request',
      durationMs: 1000,
      time: BASE_TIME,
    }),
    buildSpan({
      spanId: 'guard',
      parentSpanId: 'root',
      operationName: 'input_guard',
      durationMs: 50,
      time: BASE_TIME + 10,
    }),
    buildSpan({
      spanId: 'llm',
      parentSpanId: 'root',
      operationName: 'llm:claude',
      durationMs: 600,
      time: BASE_TIME + 100,
      attributes: { model: 'claude-sonnet-4' },
    }),
    buildSpan({
      spanId: 'tool',
      parentSpanId: 'llm',
      operationName: 'tool:search',
      durationMs: 300,
      time: BASE_TIME + 200,
      success: false,
      errorClass: 'ToolExecutionError',
      attributes: {
        toolName: 'search',
        error: 'Upstream timeout after 30s',
        stack: 'Error: timeout\n  at Tool.execute (tool.ts:42)',
      },
    }),
  ]
}

function renderTree(spans: TraceSpan[], onSelect = vi.fn()) {
  const totalDurationMs = 1000
  const traceStartTime = BASE_TIME
  return {
    onSelect,
    ...render(
      <SpanTree
        spans={spans}
        totalDurationMs={totalDurationMs}
        traceStartTime={traceStartTime}
        onSelectSpan={onSelect}
      />,
    ),
  }
}

describe('SpanTree', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'tracesPage.drawer.noSpanData': 'No span data available for this trace',
      'tracesPage.drawer.noSpanDataHint': 'Pending server endpoint.',
      'tracesPage.drawer.spanTreeAria': 'Span hierarchy',
      'tracesPage.drawer.expand': 'Expand',
      'tracesPage.drawer.collapse': 'Collapse',
      'tracesPage.drawer.statusOk': 'Success',
      'tracesPage.drawer.statusError': 'Error',
      'tracesPage.drawer.errorReason': 'Error reason',
      'tracesPage.spanDetail.technicalDetails': 'Technical details',
      'tracesPage.spanKinds.request': 'Request processing',
      'tracesPage.spanKinds.tool_call': 'External tool run',
      'tracesPage.spanKinds.llm_call': 'AI response generation',
      'tracesPage.spanKinds.input_guard': 'Input safety check',
      'tracesPage.spanKinds.output_guard': 'Response safety check',
      'tracesPage.spanDetail.modelLabels.claude_sonnet': 'Claude Sonnet',
      'tracesPage.spanDetail.errorLabels.unknown': 'An execution error occurred',
    }, true, true)
  })

  it('renders empty state when spans array is empty', () => {
    renderTree([])
    expect(screen.getByTestId('span-tree-empty')).toBeInTheDocument()
    expect(
      screen.getByText('No span data available for this trace'),
    ).toBeInTheDocument()
  })

  it('renders three nested levels with indent proportional to depth', () => {
    renderTree(threeLevels())

    const root = screen.getByTestId('span-tree-row-root')
    const guard = screen.getByTestId('span-tree-row-guard')
    const llm = screen.getByTestId('span-tree-row-llm')
    const tool = screen.getByTestId('span-tree-row-tool')

    expect(root).toBeInTheDocument()
    expect(guard).toBeInTheDocument()
    expect(llm).toBeInTheDocument()
    expect(tool).toBeInTheDocument()

    // aria-level reflects depth (1-indexed per ARIA spec).
    expect(root).toHaveAttribute('aria-level', '1')
    expect(guard).toHaveAttribute('aria-level', '2')
    expect(llm).toHaveAttribute('aria-level', '2')
    expect(tool).toHaveAttribute('aria-level', '3')
  })

  it('shows a localized known model without exposing unknown tool codes', () => {
    renderTree(threeLevels())
    expect(screen.getByText('Claude Sonnet')).toBeInTheDocument()
    expect(screen.queryByText('claude-sonnet-4')).not.toBeInTheDocument()
    expect(screen.queryByText('search')).not.toBeInTheDocument()
  })

  it('renders a localized error summary and keeps the stack collapsed', () => {
    renderTree(threeLevels())

    expect(screen.getByText('Error reason')).toBeInTheDocument()
    expect(screen.getByText('An execution error occurred')).toBeInTheDocument()
    expect(screen.getByText('Technical details')).toBeInTheDocument()
    expect(document.querySelector('.span-tree-technical-detail')).not.toHaveAttribute('open')
    expect(document.querySelector('.span-tree-error-stack')).toHaveTextContent('at Tool.execute')

    const errorRow = screen.getByTestId('span-tree-row-tool')
    expect(errorRow.className).toMatch(/span-tree-node--error/)
  })

  it('collapses and re-expands children when the toggle is clicked', () => {
    renderTree(threeLevels())

    // Initially the descendant `tool` (under `llm`) is visible.
    expect(screen.getByTestId('span-tree-row-tool')).toBeInTheDocument()

    const llmToggle = screen.getByTestId('span-tree-toggle-llm')
    fireEvent.click(llmToggle)

    // After collapsing `llm`, `tool` should no longer render.
    expect(screen.queryByTestId('span-tree-row-tool')).not.toBeInTheDocument()
    // `llm` itself still renders.
    expect(screen.getByTestId('span-tree-row-llm')).toBeInTheDocument()

    // Re-expand.
    fireEvent.click(llmToggle)
    expect(screen.getByTestId('span-tree-row-tool')).toBeInTheDocument()
  })

  it('collapses with ArrowLeft and expands with ArrowRight via keyboard', () => {
    const { onSelect } = renderTree(threeLevels())

    const tree = screen.getByTestId('span-tree')
    tree.focus()

    // Move down to `llm` (index 2: root, guard, llm).
    fireEvent.keyDown(tree, { key: 'ArrowDown' })
    fireEvent.keyDown(tree, { key: 'ArrowDown' })
    expect(onSelect).toHaveBeenLastCalledWith(
      expect.objectContaining({ spanId: 'llm' }),
    )

    // Collapse `llm` via ArrowLeft — descendant `tool` should hide.
    fireEvent.keyDown(tree, { key: 'ArrowLeft' })
    expect(screen.queryByTestId('span-tree-row-tool')).not.toBeInTheDocument()

    // Expand via ArrowRight.
    fireEvent.keyDown(tree, { key: 'ArrowRight' })
    expect(screen.getByTestId('span-tree-row-tool')).toBeInTheDocument()
  })

  it('fires onSelectSpan when a row is clicked', () => {
    const { onSelect } = renderTree(threeLevels())
    fireEvent.click(screen.getByTestId('span-tree-row-guard'))
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ spanId: 'guard' }),
    )
  })

  it('treats orphaned parent ids as roots instead of dropping the span', () => {
    const spans = [
      buildSpan({ spanId: 'a', parentSpanId: 'missing-parent', time: BASE_TIME, durationMs: 100 }),
      buildSpan({ spanId: 'b', parentSpanId: null, time: BASE_TIME + 50, durationMs: 50 }),
    ]
    renderTree(spans)
    // Both spans render as roots.
    expect(screen.getByTestId('span-tree-row-a')).toHaveAttribute('aria-level', '1')
    expect(screen.getByTestId('span-tree-row-b')).toHaveAttribute('aria-level', '1')
  })
})

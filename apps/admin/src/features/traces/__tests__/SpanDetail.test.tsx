import { beforeEach, describe, expect, it } from 'vitest'
import { i18n, render, screen } from '../../../test/utils'
import { SpanDetail } from '../ui/SpanDetail'
import type { TraceSpan } from '../types'

function buildSpan(overrides: Partial<TraceSpan> = {}): TraceSpan {
  return {
    spanId: 'span_1',
    parentSpanId: null,
    operationName: 'test-span',
    serviceName: 'test-service',
    durationMs: 200,
    success: true,
    errorClass: null,
    attributes: {},
    time: Date.now(),
    ...overrides,
  }
}

describe('SpanDetail', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'tracesPage.spanDetail.title': '{{name}}',
      'tracesPage.spanDetail.toolName': 'Tool Name',
      'tracesPage.spanDetail.mcpServer': 'MCP Server',
      'tracesPage.spanDetail.args': 'Arguments',
      'tracesPage.spanDetail.result': 'Result',
      'tracesPage.spanDetail.error': 'Error',
      'tracesPage.spanDetail.model': 'Model',
      'tracesPage.spanDetail.tokens': 'Tokens (in / out)',
      'tracesPage.spanDetail.cost': 'Cost',
      'tracesPage.spanDetail.stopReason': 'Stop Reason',
      'tracesPage.spanDetail.action': 'Action',
      'tracesPage.spanDetail.matchedRule': 'Matched Rule',
      'tracesPage.spanDetail.confidence': 'Confidence',
      'tracesPage.spanDetail.technicalDetails': 'Technical details',
      'tracesPage.spanDetail.outcomeSuccess': 'Completed',
      'tracesPage.spanDetail.outcomeError': 'Needs review',
      'tracesPage.spanKinds.request': 'Request processing',
      'tracesPage.spanKinds.tool_call': 'External tool run',
      'tracesPage.spanKinds.llm_call': 'AI response generation',
      'tracesPage.spanKinds.input_guard': 'Input safety check',
      'tracesPage.spanKinds.output_guard': 'Response safety check',
      'tracesPage.spanDetail.toolLabels.jira_search': 'Jira search',
      'tracesPage.spanDetail.toolLabels.unknown': 'External tool',
      'tracesPage.spanDetail.serverLabels.atlassian': 'Atlassian external tool',
      'tracesPage.spanDetail.serverLabels.unknown': 'Connected external tool',
      'tracesPage.spanDetail.modelLabels.claude_sonnet': 'Claude Sonnet',
      'tracesPage.spanDetail.modelLabels.unknown': 'AI model',
      'tracesPage.spanDetail.stopReasonLabels.end_turn': 'Finished normally',
      'tracesPage.spanDetail.stopReasonLabels.unknown': 'Ended after review',
      'tracesPage.spanDetail.guardActionLabels.allow': 'Passed',
      'tracesPage.spanDetail.guardActionLabels.block': 'Blocked',
      'tracesPage.spanDetail.guardActionLabels.unknown': 'Needs review',
      'tracesPage.spanDetail.guardRuleLabels.pii_detection': 'Personal data detected',
      'tracesPage.spanDetail.guardRuleLabels.none': 'No rule detected',
      'tracesPage.spanDetail.guardRuleLabels.unknown': 'Safety rule',
      'tracesPage.spanDetail.errorLabels.connection_timeout': 'External tool connection timed out',
      'tracesPage.spanDetail.errorLabels.unknown': 'An execution error occurred',
    }, true, true)
  })

  it('renders tool_call detail with tool name, server, args, and result', () => {
    const span = buildSpan({
      operationName: 'tool:jira_search',
      attributes: {
        toolName: 'jira_search',
        mcpServer: 'atlassian-mcp',
        args: { query: 'open bugs' },
        result: { count: 5 },
        error: null,
      },
    })

    render(<SpanDetail span={span} />)

    expect(screen.getByRole('heading', { name: 'External tool run' })).toBeInTheDocument()
    expect(screen.getByText('Tool Name')).toBeInTheDocument()
    expect(screen.getByText('Jira search')).toBeInTheDocument()
    expect(screen.getByText('MCP Server')).toBeInTheDocument()
    expect(screen.getByText('Atlassian external tool')).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(document.querySelectorAll('.span-detail .badge')).toHaveLength(0)
    expect(document.querySelector('.span-technical-detail')).not.toHaveAttribute('open')
    expect(document.querySelector('.span-technical-detail pre')).toHaveTextContent('jira_search')
  })

  it('renders tool_call error when present', () => {
    const span = buildSpan({
      operationName: 'tool:failing',
      success: false,
      errorClass: 'ConnectionTimeout',
      attributes: {
        toolName: 'failing_tool',
        mcpServer: 'test-mcp',
        args: {},
        result: null,
        error: 'Connection timeout',
      },
    })

    render(<SpanDetail span={span} />)

    expect(screen.getByText('External tool connection timed out')).toBeInTheDocument()
    expect(document.querySelector('.span-technical-detail pre')).toHaveTextContent('ConnectionTimeout')
  })

  it('renders llm_call detail with model, tokens, cost, and stop reason', () => {
    const span = buildSpan({
      operationName: 'llm:claude-sonnet-4',
      attributes: {
        model: 'claude-sonnet-4-20250514',
        inputTokens: 200,
        outputTokens: 400,
        costUsd: 0.003,
        stopReason: 'end_turn',
      },
    })

    render(<SpanDetail span={span} />)

    expect(screen.getByRole('heading', { name: 'AI response generation' })).toBeInTheDocument()
    expect(screen.getByText('Claude Sonnet')).toBeInTheDocument()
    expect(screen.getByText('200 / 400')).toBeInTheDocument()
    expect(screen.getByText('$0.0030')).toBeInTheDocument()
    expect(screen.getByText('Finished normally')).toBeInTheDocument()
  })

  it('renders input_guard detail with action, matched rule, and confidence', () => {
    const span = buildSpan({
      operationName: 'content-filter',
      success: false,
      attributes: {
        action: 'block',
        matchedRule: 'pii-detection',
        confidence: 0.92,
      },
    })

    render(<SpanDetail span={span} />)

    expect(screen.getByRole('heading', { name: 'Input safety check' })).toBeInTheDocument()
    expect(screen.getByText('Action')).toBeInTheDocument()
    expect(screen.getByText('Blocked')).toBeInTheDocument()
    expect(screen.getByText('Matched Rule')).toBeInTheDocument()
    expect(screen.getByText('Personal data detected')).toBeInTheDocument()
    expect(screen.getByText('Confidence')).toBeInTheDocument()
    expect(screen.getByText('92.0%')).toBeInTheDocument()
  })

  it('renders output_guard detail the same way as input_guard', () => {
    const span = buildSpan({
      operationName: 'output-guard',
      attributes: {
        action: 'allow',
        matchedRule: 'none',
        confidence: 0.05,
      },
    })

    render(<SpanDetail span={span} />)

    expect(screen.getByRole('heading', { name: 'Response safety check' })).toBeInTheDocument()
    expect(screen.getByText('Passed')).toBeInTheDocument()
    expect(screen.getByText('5.0%')).toBeInTheDocument()
  })

  it('renders request type with raw JSON detail', () => {
    const span = buildSpan({
      operationName: 'request',
      attributes: { method: 'POST', path: '/api/chat' },
    })

    render(<SpanDetail span={span} />)

    expect(screen.getByRole('heading', { name: 'Request processing' })).toBeInTheDocument()
    expect(document.querySelector('.span-technical-detail pre')).toHaveTextContent('/api/chat')
  })
})

import { render, screen } from '../../../test/utils'
import { describe, it, expect } from 'vitest'
import { StreamEventItem } from '../ui/StreamEventItem'
import { PAYLOAD_COLLAPSE_THRESHOLD_BYTES } from '../cost'

describe('StreamEventItem', () => {
  it('renders message events with a Korean technical-record label', () => {
    render(<StreamEventItem event="message" data="Hello world" />)
    expect(screen.getByText('chatInspector.streamEventTypes.message')).toBeInTheDocument()
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('renders tool-start events with a Korean technical-record label', () => {
    render(<StreamEventItem event="tool_start" data="web_search" />)
    expect(screen.getByText('chatInspector.streamEventTypes.toolStart')).toBeInTheDocument()
    expect(screen.getByText('web_search')).toBeInTheDocument()
  })

  it('renders tool_end event with DONE indicator', () => {
    render(<StreamEventItem event="tool_end" data="web_search" />)
    expect(screen.getByText('chatInspector.streamEventTypes.toolEnd')).toBeInTheDocument()
  })

  it('renders error event with ERR indicator', () => {
    render(<StreamEventItem event="error" data="Timeout" />)
    expect(screen.getByText('chatInspector.streamEventTypes.error')).toBeInTheDocument()
    expect(screen.getByText('Timeout')).toBeInTheDocument()
  })

  it('renders done event with END indicator', () => {
    render(<StreamEventItem event="done" data="" />)
    expect(screen.getByText('chatInspector.streamEventTypes.done')).toBeInTheDocument()
  })

  it('renders unknown event with ??? indicator', () => {
    render(<StreamEventItem event="custom_event" data="payload" />)
    expect(screen.getByText('chatInspector.streamEventTypes.unknown')).toBeInTheDocument()
    expect(screen.getByText('payload')).toBeInTheDocument()
  })

  it('renders payloads under 2KB inline (no <details>)', () => {
    const small = 'x'.repeat(100)
    const { container } = render(<StreamEventItem event="message" data={small} />)
    expect(screen.getByText(small)).toBeInTheDocument()
    expect(container.querySelector('details')).toBeNull()
  })

  it('collapses payloads larger than 2KB by default', () => {
    const large = 'x'.repeat(PAYLOAD_COLLAPSE_THRESHOLD_BYTES + 10)
    const { container } = render(<StreamEventItem event="message" data={large} />)
    const details = container.querySelector('details')
    expect(details).not.toBeNull()
    // <details> starts closed by default
    expect(details?.hasAttribute('open')).toBe(false)
  })

  it('pretty-prints JSON payloads when expanded', () => {
    const jsonBlob = '{"tokenUsage":{"promptTokens":100,"completionTokens":200,"totalTokens":300}}'
    const large = jsonBlob + ' '.repeat(PAYLOAD_COLLAPSE_THRESHOLD_BYTES)
    const { container } = render(<StreamEventItem event="done" data={large} />)
    const pre = container.querySelector('pre.stream-event__payload')
    expect(pre).not.toBeNull()
    // Pretty-printed JSON contains the key name on its own line
    expect(pre?.textContent).toContain('"tokenUsage"')
  })
})

import { describe, it, expect, vi } from 'vitest'
import { act } from '@testing-library/react'
import { render, screen } from '../../../test/utils'
import { MessageList } from '../ui/Detail/MessageList'
import type { ChatMessage } from '../types'
import type { MessageCost } from '../../token-cost/types'

function makeMessages(count: number): ChatMessage[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    role: (i % 2 === 0 ? 'user' : 'assistant') as ChatMessage['role'],
    content: `Message ${i + 1}`,
    timestamp: 1_700_000_000_000 + i * 1000,
    model: i % 2 === 1 ? 'gpt-4o' : undefined,
    durationMs: i % 2 === 1 ? 1200 : undefined,
  }))
}

describe('MessageList (virtualization)', () => {
  it('renders only a subset of a large message list to the DOM', () => {
    const messages = makeMessages(500)
    const costsByMessageIndex = new Map<number, MessageCost>()

    render(
      <MessageList
        messages={messages}
        costsByMessageIndex={costsByMessageIndex}
        showCost={false}
        hasOlderMessages={false}
        onLoadOlder={vi.fn()}
      />,
    )

    const rendered = screen.queryAllByTestId('virtualized-row')
    // With a 600px viewport and ~96px default row height we expect far fewer
    // than 500 rows to be mounted. The exact count varies by jsdom layout but
    // should be well under 100.
    expect(rendered.length).toBeGreaterThan(0)
    expect(rendered.length).toBeLessThan(100)
    expect(rendered.length).toBeLessThan(messages.length)
  })

  it('exposes role="log" and aria-live="polite" for screen readers', () => {
    const messages = makeMessages(10)
    render(
      <MessageList
        messages={messages}
        costsByMessageIndex={new Map()}
        showCost={false}
        hasOlderMessages={false}
        onLoadOlder={vi.fn()}
      />,
    )

    const log = screen.getByTestId('message-list-virtualized')
    expect(log).toHaveAttribute('role', 'log')
    expect(log).toHaveAttribute('aria-live', 'polite')
  })

  it('invokes onLoadOlder when scroll reaches near the top of the list', () => {
    const messages = makeMessages(200)
    const onLoadOlder = vi.fn()

    render(
      <MessageList
        messages={messages}
        costsByMessageIndex={new Map()}
        showCost={false}
        hasOlderMessages
        onLoadOlder={onLoadOlder}
      />,
    )

    // Initial mount anchors to the newest message (scroll near the bottom),
    // so the load-older callback must not fire just from mounting.
    expect(onLoadOlder).not.toHaveBeenCalled()

    // Simulate the user scrolling the virtualised list to the very top.
    const listEl = document.querySelector('.message-list') as HTMLDivElement
    expect(listEl).not.toBeNull()

    // First scroll away from the bottom so the "hasScrolled" guard trips.
    act(() => {
      listEl.scrollTop = 4000
      listEl.dispatchEvent(new Event('scroll'))
    })

    // Then scroll all the way up to trigger the near-top lazy-load threshold.
    act(() => {
      listEl.scrollTop = 0
      listEl.dispatchEvent(new Event('scroll'))
    })

    expect(onLoadOlder).toHaveBeenCalled()
  })

  it('does not invoke onLoadOlder when hasOlderMessages is false', () => {
    const messages = makeMessages(200)
    const onLoadOlder = vi.fn()

    render(
      <MessageList
        messages={messages}
        costsByMessageIndex={new Map()}
        showCost={false}
        hasOlderMessages={false}
        onLoadOlder={onLoadOlder}
      />,
    )

    const listEl = document.querySelector('.message-list') as HTMLDivElement
    act(() => {
      listEl.scrollTop = 4000
      listEl.dispatchEvent(new Event('scroll'))
    })
    act(() => {
      listEl.scrollTop = 0
      listEl.dispatchEvent(new Event('scroll'))
    })

    expect(onLoadOlder).not.toHaveBeenCalled()
  })

  it('preserves chat bubble content so message actions remain accessible', () => {
    const messages = makeMessages(5)
    render(
      <MessageList
        messages={messages}
        costsByMessageIndex={new Map()}
        showCost={false}
        hasOlderMessages={false}
        onLoadOlder={vi.fn()}
      />,
    )

    // Both user and assistant rows render bubble content + footer metadata.
    expect(screen.getByText('Message 1')).toBeInTheDocument()
    expect(screen.getByText('Message 2')).toBeInTheDocument()
    expect(screen.getAllByText('user').length).toBeGreaterThan(0)
    expect(screen.getAllByText('assistant').length).toBeGreaterThan(0)
  })

  it('uses the compact token-owned height for short conversations', () => {
    render(
      <MessageList
        messages={makeMessages(3)}
        costsByMessageIndex={new Map()}
        showCost={false}
        hasOlderMessages={false}
        onLoadOlder={vi.fn()}
      />,
    )

    expect(document.querySelector('.message-list')).toHaveAttribute(
      'style',
      expect.stringContaining('var(--conversation-list-compact-height)'),
    )
  })
})

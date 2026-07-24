import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { ChatBubble } from '../ui/Detail/ChatBubble'
import type { ChatMessage } from '../types'

const userMsg: ChatMessage = {
  id: 1, role: 'user', content: 'Hello, how are you?', timestamp: Date.now()
}

const assistantMsg: ChatMessage = {
  id: 2, role: 'assistant', content: 'I am doing well!', timestamp: Date.now(),
  model: 'gpt-4o', durationMs: 1200, grounded: true
}

const blockedMsg: ChatMessage = {
  id: 3, role: 'assistant', content: '', timestamp: Date.now(),
  blockReason: 'policy_violation', grounded: false
}

describe('ChatBubble', () => {
  it('renders user message content', () => {
    render(<ChatBubble message={userMsg} />)
    expect(screen.getByText('Hello, how are you?')).toBeInTheDocument()
  })

  it('renders user role label', () => {
    render(<ChatBubble message={userMsg} />)
    expect(screen.getByText('user')).toBeInTheDocument()
  })

  it('applies user alignment class', () => {
    const { container } = render(<ChatBubble message={userMsg} />)
    expect(container.querySelector('.session-chat-bubble--user')).toBeInTheDocument()
  })

  it('renders assistant message with model info', () => {
    render(<ChatBubble message={assistantMsg} />)
    expect(screen.getByText('I am doing well!')).toBeInTheDocument()
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
  })

  it('renders assistant response time', () => {
    render(<ChatBubble message={assistantMsg} />)
    expect(screen.getByText(/1\.2s/)).toBeInTheDocument()
  })

  it('renders grounded badge for grounded assistant', () => {
    render(<ChatBubble message={assistantMsg} />)
    expect(screen.getByText(/grounded/i)).toBeInTheDocument()
  })

  it('renders blocked message with warning', () => {
    render(<ChatBubble message={blockedMsg} />)
    // "BLOCKED" label in content + "blocked" in meta = multiple matches
    const blockedElements = screen.getAllByText(/blocked/i)
    expect(blockedElements.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/policy_violation/i)).toBeInTheDocument()
  })

  it('applies blocked class', () => {
    const { container } = render(<ChatBubble message={blockedMsg} />)
    expect(container.querySelector('.session-chat-bubble--blocked')).toBeInTheDocument()
  })

  it('renders timestamp', () => {
    render(<ChatBubble message={userMsg} />)
    // Should render time in HH:MM format
    const timeElements = screen.getAllByText(/\d{1,2}:\d{2}/)
    expect(timeElements.length).toBeGreaterThan(0)
  })
})

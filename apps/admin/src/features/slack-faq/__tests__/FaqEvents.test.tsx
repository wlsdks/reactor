import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { render } from '../../../test/utils'
import { FaqEvents } from '../ui/FaqEvents'
import * as faqApi from '../api'
import type { FaqEvent } from '../types'

const events: FaqEvent[] = [
  {
    id: 'e1',
    ts: 1700000000000,
    userId: 'U001',
    query: 'how to reset password',
    matchedFaqId: 'F001',
    confidence: 0.92,
    outcome: 'MATCH',
  },
  {
    id: 'e2',
    ts: 1700000100000,
    userId: 'U002',
    query: 'unrelated topic',
    outcome: 'MISS',
  },
]

function renderWith(node: React.ReactElement) {
  return render(<MemoryRouter>{node}</MemoryRouter>)
}

describe('FaqEvents', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders events table with rows', async () => {
    vi.spyOn(faqApi, 'getFaqChannelEvents').mockResolvedValue(events)
    renderWith(<FaqEvents channelId="C001" />)
    expect(await screen.findByText('how to reset password')).toBeInTheDocument()
    expect(screen.getByText('unrelated topic')).toBeInTheDocument()
    expect(screen.getByText('U001')).toBeInTheDocument()
  })

  it('renders empty state when no events', async () => {
    vi.spyOn(faqApi, 'getFaqChannelEvents').mockResolvedValue([])
    renderWith(<FaqEvents channelId="C001" />)
    expect(await screen.findByText(/slackFaq\.events\.empty/)).toBeInTheDocument()
  })

  it('renders error state on load failure', async () => {
    vi.spyOn(faqApi, 'getFaqChannelEvents').mockRejectedValue(new Error('boom'))
    renderWith(<FaqEvents channelId="C001" />)
    expect(await screen.findByText(/slackFaq\.events\.loadError/)).toBeInTheDocument()
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { render } from '../../../test/utils'
import { FaqFeedback } from '../ui/FaqFeedback'
import * as faqApi from '../api'
import type { FaqFeedback as FaqFeedbackRow } from '../types'

const feedback: FaqFeedbackRow[] = [
  { id: 'f1', eventId: 'e1', rating: 'UP', comment: 'helpful', ts: 1700000000000 },
  { id: 'f2', eventId: 'e2', rating: 'DOWN', ts: 1700000100000 },
]

function renderWith(node: React.ReactElement) {
  return render(<MemoryRouter>{node}</MemoryRouter>)
}

describe('FaqFeedback', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders feedback rows with text label (not icon-only)', async () => {
    vi.spyOn(faqApi, 'getFaqChannelFeedback').mockResolvedValue(feedback)
    renderWith(<FaqFeedback channelId="C001" />)
    expect(await screen.findByText(/slackFaq\.feedback\.ratingUp/)).toBeInTheDocument()
    expect(screen.getByText(/slackFaq\.feedback\.ratingDown/)).toBeInTheDocument()
    expect(screen.getByText('helpful')).toBeInTheDocument()
  })

  it('renders empty state when no feedback', async () => {
    vi.spyOn(faqApi, 'getFaqChannelFeedback').mockResolvedValue([])
    renderWith(<FaqFeedback channelId="C001" />)
    expect(await screen.findByText(/slackFaq\.feedback\.empty/)).toBeInTheDocument()
  })
})

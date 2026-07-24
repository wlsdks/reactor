import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { render } from '../../../test/utils'
import { FaqOverview } from '../ui/FaqOverview'
import * as faqApi from '../api'
import type { FaqChannel, FaqChannelStats } from '../types'

const channel: FaqChannel = {
  channelId: 'C001',
  channelName: 'general',
  enabled: true,
  autoReplyMode: 'AUTO',
  confidenceThreshold: 0.7,
  daysBack: 30,
  reIngestIntervalHours: 24,
  createdAt: 0,
  updatedAt: 0,
}

const stats: FaqChannelStats = {
  channelId: 'C001',
  totalQueries: 42,
  matchedQueries: 30,
  avgConfidence: 0.82,
  hitRate: 0.71,
  windowDays: 7,
}

describe('FaqOverview', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders channel config and stats', async () => {
    vi.spyOn(faqApi, 'getFaqChannel').mockResolvedValue(channel)
    vi.spyOn(faqApi, 'getFaqChannelStats').mockResolvedValue(stats)
    render(<FaqOverview channelId="C001" onRequestEdit={vi.fn()} />)
    expect(await screen.findByText('C001')).toBeInTheDocument()
    expect(screen.getByText('general')).toBeInTheDocument()
    expect(screen.getByText('slackFaq.form.modeLabels.AUTO')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('42')).toBeInTheDocument()
    })
    expect(screen.getByText('71%')).toBeInTheDocument()
  })

  it('fires onRequestEdit when edit button clicked', async () => {
    vi.spyOn(faqApi, 'getFaqChannel').mockResolvedValue(channel)
    vi.spyOn(faqApi, 'getFaqChannelStats').mockResolvedValue(stats)
    const onRequestEdit = vi.fn()
    render(<FaqOverview channelId="C001" onRequestEdit={onRequestEdit} />)
    const editBtn = await screen.findByTestId('faq-overview-edit-btn')
    await userEvent.click(editBtn)
    expect(onRequestEdit).toHaveBeenCalledTimes(1)
  })

  it('renders error state on load failure', async () => {
    vi.spyOn(faqApi, 'getFaqChannel').mockRejectedValue(new Error('boom'))
    vi.spyOn(faqApi, 'getFaqChannelStats').mockResolvedValue(stats)
    render(<FaqOverview channelId="C001" onRequestEdit={vi.fn()} />)
    expect(await screen.findByText(/slackFaq\.overview\.loadError/)).toBeInTheDocument()
  })
})

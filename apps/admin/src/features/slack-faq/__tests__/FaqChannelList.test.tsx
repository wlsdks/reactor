import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { render } from '../../../test/utils'
import { FaqChannelList } from '../ui/FaqChannelList'
import * as faqApi from '../api'
import type { FaqChannel, FaqChannelStats } from '../types'

const channelA: FaqChannel = {
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
const channelB: FaqChannel = {
  channelId: 'C002',
  channelName: 'random',
  enabled: false,
  autoReplyMode: 'OFF',
  confidenceThreshold: 0.7,
  daysBack: 30,
  reIngestIntervalHours: 24,
  createdAt: 0,
  updatedAt: 0,
}

const statsA: FaqChannelStats = {
  channelId: 'C001',
  totalQueries: 12,
  matchedQueries: 9,
  avgConfidence: 0.85,
  hitRate: 0.75,
  windowDays: 1,
}

describe('FaqChannelList', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders empty state when no channels', async () => {
    vi.spyOn(faqApi, 'listFaqChannels').mockResolvedValue([])
    const onSelect = vi.fn()
    render(
      <FaqChannelList selectedId={null} onSelect={onSelect} />,
    )
    await waitFor(() => expect(faqApi.listFaqChannels).toHaveBeenCalled())
    expect(await screen.findByText(/slackFaq\.list\.emptyTitle/)).toBeInTheDocument()
  })

  it('renders both channels with names', async () => {
    vi.spyOn(faqApi, 'listFaqChannels').mockResolvedValue([channelA, channelB])
    vi.spyOn(faqApi, 'getFaqChannelStats').mockResolvedValue(statsA)
    render(
      <FaqChannelList selectedId={null} onSelect={vi.fn()} />,
    )
    expect(await screen.findByText('general')).toBeInTheDocument()
    expect(await screen.findByText('random')).toBeInTheDocument()
  })

  it('calls onSelect with channelId when a row is clicked', async () => {
    vi.spyOn(faqApi, 'listFaqChannels').mockResolvedValue([channelA])
    vi.spyOn(faqApi, 'getFaqChannelStats').mockResolvedValue(statsA)
    const onSelect = vi.fn()
    render(
      <FaqChannelList selectedId={null} onSelect={onSelect} />,
    )
    const row = await screen.findByTestId('faq-channel-row-C001')
    await userEvent.click(row)
    expect(onSelect).toHaveBeenCalledWith('C001')
  })

  it('marks selected row with aria-pressed=true', async () => {
    vi.spyOn(faqApi, 'listFaqChannels').mockResolvedValue([channelA, channelB])
    vi.spyOn(faqApi, 'getFaqChannelStats').mockResolvedValue(statsA)
    render(
      <FaqChannelList selectedId="C002" onSelect={vi.fn()} />,
    )
    const selectedRow = await screen.findByTestId('faq-channel-row-C002')
    expect(selectedRow.getAttribute('aria-pressed')).toBe('true')
    const otherRow = await screen.findByTestId('faq-channel-row-C001')
    expect(otherRow.getAttribute('aria-pressed')).toBe('false')
  })

})

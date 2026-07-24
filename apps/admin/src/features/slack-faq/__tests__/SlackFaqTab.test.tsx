import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { LiveAnnouncerProvider } from '../../../shared/ui/LiveAnnouncer'
import { render } from '../../../test/utils'
import { SlackFaqTab } from '../ui/SlackFaqTab'
import * as faqApi from '../api'
import type { FaqChannel } from '../types'

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

function renderTab(initialPath = '/integrations') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <LiveAnnouncerProvider>
        <SlackFaqTab />
      </LiveAnnouncerProvider>
    </MemoryRouter>,
  )
}

describe('SlackFaqTab', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(faqApi, 'getFaqSchedulerHealth').mockResolvedValue({
      enabled: true,
      status: 'OK',
    })
    vi.spyOn(faqApi, 'getFaqChannel').mockResolvedValue(channel)
    vi.spyOn(faqApi, 'getFaqChannelStats').mockResolvedValue({
      channelId: 'C001',
      totalQueries: 1,
      matchedQueries: 1,
      avgConfidence: 0.8,
      hitRate: 1,
      windowDays: 1,
    })
    vi.spyOn(faqApi, 'getFaqChannelEvents').mockResolvedValue([])
    vi.spyOn(faqApi, 'getFaqChannelFeedback').mockResolvedValue([])
  })

  it('renders org overview when no channel selected', async () => {
    vi.spyOn(faqApi, 'listFaqChannels').mockResolvedValue([])
    vi.spyOn(faqApi, 'getFaqOrgStats').mockResolvedValue({
      totalChannels: 3,
      totalQueries7d: 120,
      avgHitRate7d: 0.66,
    })
    renderTab()
    expect(await screen.findByTestId('slack-faq-org-overview')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByText('66%')).toBeInTheDocument()
  })

  it('uses one FAQ workspace header without duplicate release workflow links', async () => {
    vi.spyOn(faqApi, 'listFaqChannels').mockResolvedValue([])
    vi.spyOn(faqApi, 'getFaqOrgStats').mockResolvedValue({
      totalChannels: 0,
      totalQueries7d: 0,
      avgHitRate7d: 0,
    })
    renderTab()
    await screen.findByTestId('slack-faq-org-overview')
    expect(screen.getByText('slackFaq.tab.title')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /integrationsPage\.releaseSmoke\.workflowSlack/ })).not.toBeInTheDocument()
  })

  it('switches to detail pane when channel selected', async () => {
    vi.spyOn(faqApi, 'listFaqChannels').mockResolvedValue([channel])
    vi.spyOn(faqApi, 'getFaqOrgStats').mockResolvedValue({
      totalChannels: 1,
      totalQueries7d: 0,
      avgHitRate7d: 0,
    })
    renderTab()
    const user = userEvent.setup()
    const row = await screen.findByTestId('faq-channel-row-C001')
    await user.click(row)
    await waitFor(() => {
      expect(screen.getByTestId('faq-detail-pane')).toBeInTheDocument()
    })
  })

  it('opens create modal when Add Channel clicked', async () => {
    vi.spyOn(faqApi, 'listFaqChannels').mockResolvedValue([])
    vi.spyOn(faqApi, 'getFaqOrgStats').mockResolvedValue({
      totalChannels: 0,
      totalQueries7d: 0,
      avgHitRate7d: 0,
    })
    renderTab()
    const user = userEvent.setup()
    const addBtn = await screen.findByTestId('faq-add-channel-btn')
    await user.click(addBtn)
    expect(await screen.findByText(/slackFaq\.tab\.createModalTitle/)).toBeInTheDocument()
  })

  it('reads selected channel from ?faqChannel param', async () => {
    vi.spyOn(faqApi, 'listFaqChannels').mockResolvedValue([channel])
    renderTab('/integrations?faqChannel=C001')
    await waitFor(() => {
      expect(screen.getByTestId('faq-detail-pane')).toBeInTheDocument()
    })
  })
})

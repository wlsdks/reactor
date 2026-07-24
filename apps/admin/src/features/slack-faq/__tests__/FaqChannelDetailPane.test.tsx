import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { LiveAnnouncerProvider } from '../../../shared/ui/LiveAnnouncer'
import { render } from '../../../test/utils'
import { FaqChannelDetailPane } from '../ui/FaqChannelDetailPane'
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

function renderWith(node: React.ReactElement) {
  return render(
    <MemoryRouter>
      <LiveAnnouncerProvider>{node}</LiveAnnouncerProvider>
    </MemoryRouter>,
  )
}

describe('FaqChannelDetailPane', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
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

  it('renders four task-oriented workspace views instead of stacked collapsible sections', () => {
    renderWith(
      <FaqChannelDetailPane
        channelId="C001"
        view="overview"
        onViewChange={vi.fn()}
        onChannelDeleted={vi.fn()}
        onRequestEdit={vi.fn()}
      />,
    )
    expect(screen.getByText(/slackFaq\.detail\.views\.overview/)).toBeInTheDocument()
    expect(screen.getByText(/slackFaq\.detail\.views\.test/)).toBeInTheDocument()
    expect(screen.getByText(/slackFaq\.detail\.views\.activity/)).toBeInTheDocument()
    expect(screen.getByText(/slackFaq\.detail\.views\.manage/)).toBeInTheDocument()
    expect(screen.queryByText(/slackFaq\.section\.dryRun/)).not.toBeInTheDocument()
  })

  it('mounts the SectionErrorBoundary wrapper', () => {
    renderWith(
      <FaqChannelDetailPane
        channelId="C001"
        view="overview"
        onViewChange={vi.fn()}
        onChannelDeleted={vi.fn()}
        onRequestEdit={vi.fn()}
      />,
    )
    expect(screen.getByTestId('faq-detail-pane')).toBeInTheDocument()
  })
})

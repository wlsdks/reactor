import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { LiveAnnouncerProvider } from '../../../shared/ui/LiveAnnouncer'
import { render } from '../../../test/utils'
import { FaqReindex } from '../ui/FaqReindex'
import * as faqApi from '../api'
import type { FaqChannel } from '../types'

const channel: FaqChannel = {
  channelId: 'C001',
  enabled: true,
  autoReplyMode: 'AUTO',
  confidenceThreshold: 0.7,
  daysBack: 30,
  reIngestIntervalHours: 24,
  createdAt: 0,
  updatedAt: 0,
  lastIngestedAt: 1700000000000,
}

function renderWith(ui: React.ReactElement) {
  return render(<LiveAnnouncerProvider>{ui}</LiveAnnouncerProvider>)
}

describe('FaqReindex', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('shows last ingested hint when present', async () => {
    vi.spyOn(faqApi, 'getFaqChannel').mockResolvedValue(channel)
    renderWith(<FaqReindex channelId="C001" />)
    await waitFor(() =>
      expect(screen.getByText(/slackFaq\.reindex\.lastIngested/)).toBeInTheDocument(),
    )
  })

  it('shows never-ingested hint when missing', async () => {
    vi.spyOn(faqApi, 'getFaqChannel').mockResolvedValue({ ...channel, lastIngestedAt: undefined })
    renderWith(<FaqReindex channelId="C001" />)
    expect(await screen.findByText(/slackFaq\.reindex\.neverIngested/)).toBeInTheDocument()
  })

  it('triggers ingest mutation on click', async () => {
    vi.spyOn(faqApi, 'getFaqChannel').mockResolvedValue(channel)
    const ingestSpy = vi.spyOn(faqApi, 'ingestFaqChannel').mockResolvedValue(undefined)
    renderWith(<FaqReindex channelId="C001" />)
    const user = userEvent.setup()
    await user.click(await screen.findByTestId('faq-reindex-btn'))
    await waitFor(() => expect(ingestSpy).toHaveBeenCalledWith('C001'))
  })
})

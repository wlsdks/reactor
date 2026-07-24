import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { LiveAnnouncerProvider } from '../../../shared/ui/LiveAnnouncer'
import { render } from '../../../test/utils'
import { FaqDryRun } from '../ui/FaqDryRun'
import * as faqApi from '../api'

function renderWith(ui: React.ReactElement) {
  return render(<LiveAnnouncerProvider>{ui}</LiveAnnouncerProvider>)
}

describe('FaqDryRun', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('explains that the preview is safe and audited', () => {
    renderWith(<FaqDryRun channelId="C001" />)
    expect(screen.getByText(/slackFaq\.dryRun\.description/)).toBeInTheDocument()
  })

  it('rejects empty query', async () => {
    renderWith(<FaqDryRun channelId="C001" />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /slackFaq\.dryRun\.submit/ }))
    // Schema messages now go through i18n.t(); when running in the unit test
    // environment without the global i18n initialized, zod falls back to its
    // default error. We assert the error element is rendered with non-empty text.
    await waitFor(() => {
      const errorEl = screen.getByText((_, el) =>
        el?.id === 'faq-dryrun-query-error' && (el?.textContent ?? '').trim().length > 0,
      )
      expect(errorEl).toBeInTheDocument()
    })
  })

  it('shows decision badge on success', async () => {
    vi.spyOn(faqApi, 'dryRunFaqChannel').mockResolvedValue({
      decision: 'WOULD_REPLY',
      reason: 'High confidence match',
      match: { faqId: 'F1', title: 'Reset password', confidence: 0.92 },
    })
    renderWith(<FaqDryRun channelId="C001" />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/slackFaq\.dryRun\.query/), 'reset')
    await user.click(screen.getByRole('button', { name: /slackFaq\.dryRun\.submit/ }))
    expect(await screen.findByTestId('faq-dry-run-result-heading')).toBeInTheDocument()
    expect(screen.getByText('slackFaq.dryRun.decisions.WOULD_REPLY')).toBeInTheDocument()
    expect(screen.getByText('High confidence match')).toBeInTheDocument()
    expect(screen.getByTestId('faq-dry-run-match')).toBeInTheDocument()
  })

  it('handles WOULD_SKIP without match', async () => {
    vi.spyOn(faqApi, 'dryRunFaqChannel').mockResolvedValue({
      decision: 'WOULD_SKIP',
      reason: 'Below threshold',
    })
    renderWith(<FaqDryRun channelId="C001" />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/slackFaq\.dryRun\.query/), 'unrelated')
    await user.click(screen.getByRole('button', { name: /slackFaq\.dryRun\.submit/ }))
    expect(await screen.findByText('slackFaq.dryRun.decisions.WOULD_SKIP')).toBeInTheDocument()
    expect(screen.queryByTestId('faq-dry-run-match')).not.toBeInTheDocument()
  })
})

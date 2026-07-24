import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { LiveAnnouncerProvider } from '../../../shared/ui/LiveAnnouncer'
import { render } from '../../../test/utils'
import { FaqProbe } from '../ui/FaqProbe'
import * as faqApi from '../api'

function renderWith(ui: React.ReactElement) {
  return render(<LiveAnnouncerProvider>{ui}</LiveAnnouncerProvider>)
}

describe('FaqProbe', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('rejects empty query', async () => {
    renderWith(<FaqProbe channelId="C001" />)
    const user = userEvent.setup()
    const submit = screen.getByRole('button', { name: /slackFaq\.probe\.submit/ })
    await user.click(submit)
    // Schema messages now go through i18n.t(); when running in the unit test
    // environment without the global i18n initialized, zod falls back to its
    // default error. We assert the error element is rendered with non-empty text.
    await waitFor(() => {
      const errorEl = screen.getByText((_, el) =>
        el?.id === 'faq-probe-query-error' && (el?.textContent ?? '').trim().length > 0,
      )
      expect(errorEl).toBeInTheDocument()
    })
  })

  it('shows ranked matches and announces success', async () => {
    vi.spyOn(faqApi, 'probeFaqChannel').mockResolvedValue({
      query: 'reset password',
      matches: [
        { faqId: 'F1', title: 'Reset Password', confidence: 0.92 },
        { faqId: 'F2', title: 'Forgot password', body: 'Use the reset flow', confidence: 0.71 },
      ],
    })
    renderWith(<FaqProbe channelId="C001" />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/slackFaq\.probe\.query/), 'reset password')
    await user.click(screen.getByRole('button', { name: /slackFaq\.probe\.submit/ }))
    expect(await screen.findByTestId('faq-probe-result-heading')).toBeInTheDocument()
    expect(screen.getByText(/Reset Password/)).toBeInTheDocument()
    expect(screen.getByText(/Forgot password/)).toBeInTheDocument()
    // aria-live polite region should reflect announcement (count: 2)
    await waitFor(() => {
      expect(screen.getByTestId('live-announcer-polite').textContent).toContain(
        'slackFaq.probe.announce',
      )
    })
  })

  it('renders no-matches state when matches is empty', async () => {
    vi.spyOn(faqApi, 'probeFaqChannel').mockResolvedValue({
      query: 'unrelated',
      matches: [],
    })
    renderWith(<FaqProbe channelId="C001" />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/slackFaq\.probe\.query/), 'unrelated')
    await user.click(screen.getByRole('button', { name: /slackFaq\.probe\.submit/ }))
    expect(await screen.findByText(/slackFaq\.probe\.noMatches/)).toBeInTheDocument()
  })
})

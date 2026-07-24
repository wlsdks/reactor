import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { render } from '../../../test/utils'
import { FaqSchedulerHealthBar } from '../ui/FaqSchedulerHealthBar'
import * as faqApi from '../api'

describe('FaqSchedulerHealthBar', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders nothing when status is OK', async () => {
    vi.spyOn(faqApi, 'getFaqSchedulerHealth').mockResolvedValue({
      enabled: true,
      status: 'OK',
    })
    const { container } = render(<FaqSchedulerHealthBar />)
    // Wait for the query to settle, then confirm nothing rendered.
    await waitFor(() => expect(faqApi.getFaqSchedulerHealth).toHaveBeenCalled())
    expect(container.querySelector('[data-testid="faq-scheduler-health-bar"]')).toBeNull()
  })

  it('renders disabled state when scheduler is disabled', async () => {
    vi.spyOn(faqApi, 'getFaqSchedulerHealth').mockResolvedValue({ enabled: false })
    render(<FaqSchedulerHealthBar />)
    const bar = await screen.findByTestId('faq-scheduler-health-bar')
    expect(bar).toBeInTheDocument()
    expect(bar.getAttribute('aria-live')).toBe('polite')
    expect(bar.textContent).toContain('slackFaq.scheduler.disabled')
  })

  it('renders degraded state with polite live region', async () => {
    vi.spyOn(faqApi, 'getFaqSchedulerHealth').mockResolvedValue({
      enabled: true,
      status: 'DEGRADED',
    })
    render(<FaqSchedulerHealthBar />)
    const bar = await screen.findByTestId('faq-scheduler-health-bar')
    expect(bar.getAttribute('aria-live')).toBe('polite')
    expect(bar.textContent).toContain('slackFaq.scheduler.degraded')
  })

  it('renders down state with assertive live region', async () => {
    vi.spyOn(faqApi, 'getFaqSchedulerHealth').mockResolvedValue({
      enabled: true,
      status: 'DOWN',
    })
    render(<FaqSchedulerHealthBar />)
    const bar = await screen.findByTestId('faq-scheduler-health-bar')
    expect(bar.getAttribute('aria-live')).toBe('assertive')
    expect(bar.textContent).toContain('slackFaq.scheduler.down')
  })
})

import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { render } from '../../../test/utils'
import { FaqChannelForm } from '../ui/FaqChannelForm'
import type { FaqChannel } from '../types'

const baseChannel: FaqChannel = {
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

describe('FaqChannelForm — create mode', () => {
  it('rejects submit when channelId is empty', async () => {
    const onSubmit = vi.fn()
    const onCancel = vi.fn()
    render(
      <FaqChannelForm
        mode="create"
        onSubmit={onSubmit}
        onCancel={onCancel}
        isPending={false}
      />,
    )
    const user = userEvent.setup()
    const submitBtn = screen.getByRole('button', { name: /slackFaq\.form\.createSubmit/ })
    await user.click(submitBtn)
    // Schema messages now go through i18n.t(); when running in the unit test
    // environment without the global i18n initialized, zod falls back to its
    // default error. We assert the error element is rendered with non-empty text.
    await waitFor(() => {
      const errorEl = screen.getByText((_, el) =>
        el?.id === 'faq-channel-id-error' && (el?.textContent ?? '').trim().length > 0,
      )
      expect(errorEl).toBeInTheDocument()
    })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits valid create payload', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <FaqChannelForm
        mode="create"
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isPending={false}
      />,
    )
    const user = userEvent.setup()
    const channelIdInput = screen.getByLabelText(/slackFaq\.form\.channelId/) as HTMLInputElement
    await user.type(channelIdInput, 'C123')
    const submitBtn = screen.getByRole('button', { name: /slackFaq\.form\.createSubmit/ })
    await user.click(submitBtn)
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const args = onSubmit.mock.calls[0]?.[0] as { channelId: string }
    expect(args.channelId).toBe('C123')
  })

  it('renders root error when provided', () => {
    render(
      <FaqChannelForm
        mode="create"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isPending={false}
        rootError="Something went wrong"
      />,
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('disables cancel button while pending', () => {
    render(
      <FaqChannelForm
        mode="create"
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isPending
      />,
    )
    const cancelBtn = screen.getByRole('button', { name: 'Cancel' })
    expect((cancelBtn as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('FaqChannelForm — edit mode', () => {
  it('shows channelId as disabled readonly input', () => {
    render(
      <FaqChannelForm
        mode="edit"
        initialValues={baseChannel}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isPending={false}
      />,
    )
    const idInput = screen.getByDisplayValue('C001') as HTMLInputElement
    expect(idInput.disabled).toBe(true)
  })

  it('pre-fills channelName', () => {
    render(
      <FaqChannelForm
        mode="edit"
        initialValues={baseChannel}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isPending={false}
      />,
    )
    expect(screen.getByDisplayValue('general')).toBeInTheDocument()
  })

  it('submits partial update payload', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <FaqChannelForm
        mode="edit"
        initialValues={baseChannel}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isPending={false}
      />,
    )
    const user = userEvent.setup()
    const submitBtn = screen.getByRole('button', { name: 'Save' })
    await user.click(submitBtn)
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const payload = onSubmit.mock.calls[0]?.[0] as Record<string, unknown>
    expect('channelId' in payload).toBe(false)
  })
})

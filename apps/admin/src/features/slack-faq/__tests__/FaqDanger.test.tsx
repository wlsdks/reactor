import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { render } from '../../../test/utils'
import { FaqDanger } from '../ui/FaqDanger'
import * as faqApi from '../api'

describe('FaqDanger', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('opens confirm dialog when delete clicked', async () => {
    render(<FaqDanger channelId="C001" onChannelDeleted={vi.fn()} />)
    const user = userEvent.setup()
    await user.click(screen.getByTestId('faq-danger-delete-btn'))
    expect(await screen.findByText(/slackFaq\.danger\.confirmTitle/)).toBeInTheDocument()
  })

  it('keeps confirm button disabled until typed value matches channelId', async () => {
    render(<FaqDanger channelId="C001" onChannelDeleted={vi.fn()} />)
    const user = userEvent.setup()
    await user.click(screen.getByTestId('faq-danger-delete-btn'))
    const confirm = await screen.findByRole('button', { name: 'Confirm' })
    expect((confirm as HTMLButtonElement).disabled).toBe(true)
  })

  it('calls deleteFaqChannel after type-to-confirm matches', async () => {
    const deleteSpy = vi.spyOn(faqApi, 'deleteFaqChannel').mockResolvedValue(undefined)
    const onChannelDeleted = vi.fn()
    render(<FaqDanger channelId="C001" onChannelDeleted={onChannelDeleted} />)
    const user = userEvent.setup()
    await user.click(screen.getByTestId('faq-danger-delete-btn'))
    const input = await screen.findByRole('textbox')
    await user.type(input, 'C001')
    const confirm = screen.getByRole('button', { name: 'Confirm' })
    await user.click(confirm)
    await waitFor(() => expect(deleteSpy).toHaveBeenCalledWith('C001'))
    await waitFor(() => expect(onChannelDeleted).toHaveBeenCalled())
  })
})

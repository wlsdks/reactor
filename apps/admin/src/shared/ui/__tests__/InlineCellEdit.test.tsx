import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { InlineCellEdit } from '../InlineCellEdit'

// Stateful host that mirrors the typical DataTable + mutation flow: the
// committed value flows back into `value` via onCommit, so after commit the
// idle cell displays the new value rather than the stale prop.
function HostedEdit({
  initialValue,
  onCommit,
}: {
  initialValue: string
  onCommit?: (next: string) => void | Promise<void>
}) {
  const [value, setValue] = useState(initialValue)
  return (
    <InlineCellEdit<string>
      value={value}
      onCommit={async (next) => {
        if (onCommit) await onCommit(next)
        setValue(next)
      }}
    />
  )
}

describe('InlineCellEdit', () => {
  it('renders the formatted value in idle mode', () => {
    render(
      <InlineCellEdit<string>
        value="hello"
        format={(v) => `→ ${v}`}
        onCommit={vi.fn()}
      />,
    )
    expect(screen.getByRole('button')).toHaveTextContent('→ hello')
  })

  it('clicking the idle cell mounts the editor with focus + selection', async () => {
    const user = userEvent.setup()
    render(<InlineCellEdit<string> value="hello" onCommit={vi.fn()} />)

    await user.click(screen.getByRole('button'))

    const input = await screen.findByRole('textbox')
    expect(input).toHaveValue('hello')
    expect(input).toHaveFocus()
  })

  it('Enter inside the editor commits the new value via onCommit', async () => {
    const user = userEvent.setup()
    const onCommit = vi.fn()
    render(<HostedEdit initialValue="hi" onCommit={onCommit} />)

    await user.click(screen.getByRole('button'))
    const input = await screen.findByRole('textbox')
    await user.clear(input)
    await user.type(input, 'updated{Enter}')

    await waitFor(() => expect(onCommit).toHaveBeenCalledWith('updated'))
    // Commit returns to idle; the role flips back from textbox to button.
    await waitFor(() => expect(screen.getByRole('button')).toHaveTextContent('updated'))
  })

  it('Escape cancels the edit and restores the original value', async () => {
    const user = userEvent.setup()
    const onCommit = vi.fn()
    render(<InlineCellEdit<string> value="original" onCommit={onCommit} />)

    await user.click(screen.getByRole('button'))
    const input = await screen.findByRole('textbox')
    await user.clear(input)
    await user.type(input, 'changed{Escape}')

    expect(onCommit).not.toHaveBeenCalled()
    await waitFor(() => expect(screen.getByRole('button')).toHaveTextContent('original'))
  })

  it('async commit shows submitting state then exits edit mode', async () => {
    const user = userEvent.setup()
    let resolve: (() => void) | undefined
    const asyncCommit = vi.fn(
      () =>
        new Promise<void>((r) => {
          resolve = r
        }),
    )
    render(<HostedEdit initialValue="a" onCommit={asyncCommit} />)

    await user.click(screen.getByRole('button'))
    const input = await screen.findByRole('textbox')
    await user.clear(input)
    await user.type(input, 'b{Enter}')

    // While the promise is pending the input is disabled and the indicator
    // shows the validating dot.
    await waitFor(() => expect(input).toBeDisabled())

    await act(async () => {
      resolve!()
    })

    await waitFor(() => expect(screen.getByRole('button')).toHaveTextContent('b'))
  })

  it('blocks commit when validate fails and surfaces the error inline', async () => {
    const user = userEvent.setup()
    const onCommit = vi.fn()
    const validate = (next: string) => (next.trim().length === 0 ? 'required' : null)
    render(
      <InlineCellEdit<string> value="hi" validate={validate} onCommit={onCommit} />,
    )

    await user.click(screen.getByRole('button'))
    const input = await screen.findByRole('textbox')
    await user.clear(input)
    await user.type(input, '{Enter}')

    expect(onCommit).not.toHaveBeenCalled()
    expect(await screen.findByRole('alert')).toHaveTextContent('required')
    // Editor stays mounted so the user can correct the value.
    expect(screen.getByRole('textbox')).toBeInTheDocument()
  })

  it('outside-click commits the draft when commitOnBlur is left default', async () => {
    const user = userEvent.setup()
    const onCommit = vi.fn(() => Promise.resolve())
    render(
      <div>
        <InlineCellEdit<string> value="hi" onCommit={onCommit} />
        <button type="button" data-testid="outside">outside</button>
      </div>,
    )

    await user.click(screen.getAllByRole('button')[0])
    const input = await screen.findByRole('textbox')
    await user.clear(input)
    await user.type(input, 'changed')

    fireEvent.mouseDown(screen.getByTestId('outside'))

    await waitFor(() => expect(onCommit).toHaveBeenCalledWith('changed'))
  })

  it('outside-click cancels the draft when commitOnBlur is false', async () => {
    const user = userEvent.setup()
    const onCommit = vi.fn()
    render(
      <div>
        <InlineCellEdit<string>
          value="original"
          commitOnBlur={false}
          onCommit={onCommit}
        />
        <button type="button" data-testid="outside">outside</button>
      </div>,
    )

    await user.click(screen.getAllByRole('button')[0])
    const input = await screen.findByRole('textbox')
    await user.clear(input)
    await user.type(input, 'discarded')

    fireEvent.mouseDown(screen.getByTestId('outside'))

    expect(onCommit).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Edit value/i })).toHaveTextContent('original'),
    )
  })

  it('select editor commits the option chosen by the user', async () => {
    const user = userEvent.setup()
    const onCommit = vi.fn(() => Promise.resolve())
    render(
      <InlineCellEdit<string>
        value="alpha"
        type="select"
        options={[
          { value: 'alpha', label: 'Alpha' },
          { value: 'beta', label: 'Beta' },
        ]}
        onCommit={onCommit}
      />,
    )

    await user.click(screen.getByRole('button'))
    const select = await screen.findByRole('combobox')
    await user.selectOptions(select, 'beta')
    fireEvent.keyDown(select, { key: 'Enter' })

    await waitFor(() => expect(onCommit).toHaveBeenCalledWith('beta'))
  })

  it('renders read-only when disabled', () => {
    render(
      <InlineCellEdit<string>
        value="locked"
        disabled
        onCommit={vi.fn()}
      />,
    )
    // Disabled idle cell drops the button role + tabIndex.
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText('locked')).toBeInTheDocument()
  })
})

import { describe, it, expect } from 'vitest'
import { render as rtlRender, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Breadcrumb } from '../Breadcrumb'

function renderInRouter(ui: React.ReactElement) {
  return rtlRender(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('Breadcrumb', () => {
  it('renders nothing when items is empty', () => {
    const { container } = renderInRouter(<Breadcrumb items={[]} />)
    expect(container.querySelector('nav')).not.toBeInTheDocument()
  })

  it('renders all items in order', () => {
    renderInRouter(
      <Breadcrumb
        items={[
          { label: 'Conversations', href: '/sessions' },
          { label: 'Users', href: '/sessions/users' },
          { label: 'user-123' },
        ]}
      />,
    )

    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('Conversations')
    expect(items[1]).toHaveTextContent('Users')
    expect(items[2]).toHaveTextContent('user-123')
  })

  it('marks the last item with aria-current="page"', () => {
    renderInRouter(
      <Breadcrumb
        items={[
          { label: 'Conversations', href: '/sessions' },
          { label: 'Detail' },
        ]}
      />,
    )

    expect(screen.getByText('Detail')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Conversations')).not.toHaveAttribute('aria-current')
  })

  it('renders ancestor items as react-router links', () => {
    renderInRouter(
      <Breadcrumb
        items={[
          { label: 'Scheduler', href: '/scheduler' },
          { label: 'Job-A' },
        ]}
      />,
    )

    const link = screen.getByRole('link', { name: 'Scheduler' })
    expect(link).toHaveAttribute('href', '/scheduler')
  })

  it('does not render a link when href is omitted on a non-last item', () => {
    renderInRouter(
      <Breadcrumb
        items={[
          { label: 'Root' },
          { label: 'Mid', href: '/mid' },
          { label: 'Leaf' },
        ]}
      />,
    )

    expect(screen.queryByRole('link', { name: 'Root' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Mid' })).toHaveAttribute('href', '/mid')
    expect(screen.getByText('Leaf')).toHaveAttribute('aria-current', 'page')
  })

  it('renders the default `/` separator between items, hidden from a11y tree', () => {
    const { container } = renderInRouter(
      <Breadcrumb
        items={[
          { label: 'A', href: '/a' },
          { label: 'B' },
        ]}
      />,
    )
    const separators = container.querySelectorAll('.breadcrumb__separator')
    expect(separators).toHaveLength(1)
    expect(separators[0]).toHaveAttribute('aria-hidden', 'true')
    expect(separators[0]).toHaveTextContent('/')
  })

  it('renders a custom separator when provided', () => {
    const { container } = renderInRouter(
      <Breadcrumb
        items={[
          { label: 'A', href: '/a' },
          { label: 'B' },
        ]}
        separator="›"
      />,
    )
    expect(container.querySelector('.breadcrumb__separator')).toHaveTextContent('›')
  })

  it('truncates labels longer than 32 chars and adds title tooltip', () => {
    const longLabel = 'a-very-long-resource-id-that-needs-truncation-12345'
    renderInRouter(<Breadcrumb items={[{ label: 'Root', href: '/' }, { label: longLabel }]} />)

    const current = screen.getByText(longLabel)
    expect(current).toHaveAttribute('title', longLabel)
    expect(current).toHaveClass('breadcrumb__label--truncate')
  })

  it('does not add a title tooltip for short labels', () => {
    renderInRouter(<Breadcrumb items={[{ label: 'Root', href: '/' }, { label: 'Short' }]} />)
    expect(screen.getByText('Short')).not.toHaveAttribute('title')
  })

  it('applies the mono class when item.mono is true', () => {
    renderInRouter(
      <Breadcrumb items={[{ label: 'Root', href: '/' }, { label: 'abc-123', mono: true }]} />,
    )
    expect(screen.getByText('abc-123')).toHaveClass('breadcrumb__label--mono')
  })

  it('uses the provided ariaLabel on the nav element', () => {
    renderInRouter(<Breadcrumb items={[{ label: 'Only' }]} ariaLabel="custom-label" />)
    expect(screen.getByLabelText('custom-label')).toBeInTheDocument()
  })

  it('appends an extra className when provided', () => {
    const { container } = renderInRouter(
      <Breadcrumb items={[{ label: 'Only' }]} className="my-extra" />,
    )
    expect(container.querySelector('nav')).toHaveClass('breadcrumb', 'my-extra')
  })
})

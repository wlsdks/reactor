import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PageHeader } from '../PageHeader'

describe('PageHeader', () => {
  it('renders title as <h1> with the page-title class', () => {
    render(<PageHeader title="Personas" />)
    const heading = screen.getByRole('heading', { level: 1, name: 'Personas' })
    expect(heading.tagName).toBe('H1')
    expect(heading).toHaveClass('page-title')
  })

  it('supports an embedded h2 without replacing the document title', () => {
    document.title = 'Safety rules · Reactor Admin'
    render(
      <PageHeader
        title="Input guard"
        headingLevel={2}
        updateDocumentTitle={false}
      />,
    )

    expect(screen.getByRole('heading', { level: 2, name: 'Input guard' })).toHaveClass('page-title')
    expect(document.title).toBe('Safety rules · Reactor Admin')
  })

  it('wraps the heading in a <header> with the page-header class', () => {
    const { container } = render(<PageHeader title="Personas" />)
    const headerEl = container.querySelector('header')
    expect(headerEl).not.toBeNull()
    expect(headerEl).toHaveClass('page-header')
    expect(headerEl?.querySelector('h1.page-title')).not.toBeNull()
  })

  it('renders the description when provided as a string', () => {
    render(<PageHeader title="Personas" description="Manage chatbot personas" />)
    expect(screen.getByText('Manage chatbot personas')).toBeInTheDocument()
  })

  it('renders the description when provided as ReactNode', () => {
    render(
      <PageHeader
        title="Audit"
        description={
          <>
            <p>line one</p>
            <p>line two</p>
          </>
        }
      />,
    )
    expect(screen.getByText('line one')).toBeInTheDocument()
    expect(screen.getByText('line two')).toBeInTheDocument()
  })

  it('omits the description container when description is not provided', () => {
    const { container } = render(<PageHeader title="Personas" />)
    expect(container.querySelector('.page-header-description')).toBeNull()
  })

  it('renders the breadcrumb in a dedicated slot above the title row', () => {
    const { container } = render(
      <PageHeader title="Detail" breadcrumb={<nav data-testid="bc">crumb</nav>} />,
    )
    const breadcrumbSlot = container.querySelector('.page-header-breadcrumb')
    expect(breadcrumbSlot).not.toBeNull()
    expect(breadcrumbSlot?.querySelector('[data-testid="bc"]')).not.toBeNull()
  })

  it('omits the breadcrumb container when breadcrumb is not provided', () => {
    const { container } = render(<PageHeader title="Personas" />)
    expect(container.querySelector('.page-header-breadcrumb')).toBeNull()
  })

  it('renders actions in a dedicated slot', () => {
    render(
      <PageHeader
        title="Personas"
        actions={<button type="button">Create</button>}
      />,
    )
    expect(screen.getByRole('button', { name: 'Create' })).toBeInTheDocument()
  })

  it('omits the actions container when actions are not provided', () => {
    const { container } = render(<PageHeader title="Personas" />)
    expect(container.querySelector('.page-header-actions')).toBeNull()
  })

  it('defaults aria-label on the header element to the title', () => {
    render(<PageHeader title="Personas" />)
    expect(screen.getByRole('banner', { name: 'Personas' })).toBeInTheDocument()
  })

  it('uses the provided ariaLabel override', () => {
    render(<PageHeader title="Personas" ariaLabel="Personas page header" />)
    expect(screen.getByRole('banner', { name: 'Personas page header' })).toBeInTheDocument()
  })

  it('updates document.title with the page title and brand suffix', () => {
    document.title = 'Reactor Admin'
    const { unmount } = render(<PageHeader title="Personas" />)
    expect(document.title).toBe('Personas · Reactor Admin')
    unmount()
    expect(document.title).toBe('Reactor Admin')
  })

  it('switches to the with-breadcrumb layout when breadcrumb is provided', () => {
    const { container } = render(
      <PageHeader
        title="Detail"
        breadcrumb={<nav>crumb</nav>}
        actions={<button type="button">Save</button>}
      />,
    )
    const headerEl = container.querySelector('header')
    expect(headerEl).toHaveClass('page-header--with-breadcrumb')
    // Breadcrumb is sibling above the row, main + actions are inside the row.
    expect(container.querySelector('.page-header-row')).not.toBeNull()
    expect(container.querySelector('.page-header-row .page-header-main')).not.toBeNull()
    expect(container.querySelector('.page-header-row .page-header-actions')).not.toBeNull()
  })
})

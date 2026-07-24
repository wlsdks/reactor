import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'

import { render, screen } from '../../test/utils'
import { NotFoundPage } from '../NotFoundPage'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  )
  return { ...actual, useNavigate: () => mockNavigate }
})

function renderPage() {
  return render(
    <MemoryRouter>
      <NotFoundPage />
    </MemoryRouter>,
  )
}

describe('NotFoundPage', () => {
  beforeEach(() => {
    mockNavigate.mockReset()
  })

  it('renders the 404 mark, friendly title, and description', () => {
    renderPage()

    expect(screen.getByText('404')).toBeInTheDocument()
    // i18n test instance returns the key when not pre-registered, which is
    // exactly the assertion surface we want for a copy-only page.
    expect(
      screen.getByRole('heading', { name: 'notFound.title' }),
    ).toBeInTheDocument()
    expect(screen.getByText('notFound.description')).toBeInTheDocument()
  })

  it('renders all three recovery suggestions', () => {
    renderPage()

    const list = screen.getByRole('list', { name: 'notFound.suggestionsLabel' })
    expect(list).toBeInTheDocument()

    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(
      screen.getByText('notFound.suggestions.dashboard.title'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('notFound.suggestions.sidebar.title'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('notFound.suggestions.search.title'),
    ).toBeInTheDocument()
  })

  it('navigates home when "go home" is clicked', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(
      screen.getByRole('button', { name: 'notFound.actions.goHome' }),
    )
    expect(mockNavigate).toHaveBeenCalledWith('/')
  })

  it('navigates back when "go back" is clicked', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(
      screen.getByRole('button', { name: 'notFound.actions.goBack' }),
    )
    expect(mockNavigate).toHaveBeenCalledWith(-1)
  })
})

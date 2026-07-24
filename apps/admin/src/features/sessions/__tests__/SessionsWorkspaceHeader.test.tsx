import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '../../../test/utils'
import { SessionsWorkspaceHeader } from '../ui/SessionsWorkspaceHeader'

describe('SessionsWorkspaceHeader', () => {
  it('exposes one visible title and three URL-addressable workspace destinations', () => {
    render(
      <MemoryRouter initialEntries={['/sessions/feed']}>
        <SessionsWorkspaceHeader title="Session review" description="Review session operations" />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { level: 1, name: 'Session review' })).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'conversations.workspace.ariaLabel' })
    const links = Array.from(nav.querySelectorAll('a'))
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/sessions',
      '/sessions/feed',
      '/sessions/users',
    ])
    expect(links[1]).toHaveClass('is-active')
  })
})

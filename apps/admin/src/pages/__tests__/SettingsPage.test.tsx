import { describe, expect, it, vi } from 'vitest'
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { render, screen } from '../../test/utils'
import { SettingsPage } from '../SettingsPage'

vi.mock('../../features/admin-settings/ui/AdminSettingsTab', () => ({
  AdminSettingsTab: () => <div data-testid="runtime-settings-panel" />,
}))

vi.mock('../../features/retention/ui/RetentionTab', () => ({
  RetentionTab: () => <div data-testid="retention-policy-panel" />,
}))

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderPage(initialEntry = '/settings') {
  const router = createMemoryRouter([
    { path: '/settings', element: <><SettingsPage /><LocationProbe /></> },
  ], { initialEntries: [initialEntry] })
  render(<RouterProvider router={router} />)
}

describe('SettingsPage', () => {
  it('renders one platform policy heading above URL-addressable tabs', () => {
    renderPage()

    const heading = screen.getByRole('heading', { level: 1, name: 'settingsPage.title' })
    const tablist = screen.getByRole('tablist', { name: 'settingsPage.tabsLabel' })
    expect(heading.compareDocumentPosition(tablist) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'settingsPage.tabRuntime' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('runtime-settings-panel')).toBeVisible()
    expect(screen.getByText('settingsPage.description')).toBeVisible()
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
  })

  it('opens data retention as a stable URL tab', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('tab', { name: 'settingsPage.tabRetention' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/settings?tab=retention')
    expect(screen.getByTestId('retention-policy-panel')).toBeVisible()
  })

  it('loads a direct retention deep link', () => {
    renderPage('/settings?tab=retention')

    expect(screen.getByRole('tab', { name: 'settingsPage.tabRetention' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('retention-policy-panel')).toBeVisible()
  })
})

import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '../../../test/utils'
import { AdminSettingsTab } from '../ui/AdminSettingsTab'
import * as api from '../api'

vi.mock('../api')

function renderAdminSettingsTab() {
  return render(
    <MemoryRouter>
      <AdminSettingsTab />
    </MemoryRouter>,
  )
}

describe('AdminSettingsTab', () => {
  beforeEach(() => {
    vi.mocked(api.listSettings).mockResolvedValue([])
    vi.mocked(api.refreshSettingsCache).mockResolvedValue(undefined)
    vi.mocked(api.reloadSlackPrompts).mockResolvedValue({ sectionCount: 0 })
  })

  it('keeps runtime operations local without a duplicate release workflow backlink', async () => {
    renderAdminSettingsTab()

    await screen.findByRole('button', { name: 'adminSettingsTab.reloadSlackPromptsTitle' })
    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
  })

  it('shows the backend description as the primary setting label and hides the raw key from the list', async () => {
    vi.mocked(api.listSettings).mockResolvedValue([{
      tenantId: 'tenant-1',
      key: 'runtime.guard.enabled',
      value: 'true',
      type: 'BOOLEAN',
      category: 'runtime',
      description: '실행 가드 활성화',
      updatedBy: 'admin-1',
      updatedAt: '2026-07-11T00:00:00Z',
      metadata: {},
    }])

    renderAdminSettingsTab()

    expect(await screen.findByText('실행 가드 활성화')).toBeVisible()
    expect(screen.queryByText('runtime.guard.enabled')).not.toBeInTheDocument()
    expect(screen.getByText('adminSettingsTab.booleanEnabled')).toBeVisible()
    expect(screen.queryByText('BOOLEAN')).not.toBeInTheDocument()
  })

  it('replaces known English backend descriptions with an operator label', async () => {
    vi.mocked(api.listSettings).mockResolvedValue([{
      tenantId: 'tenant-1',
      key: 'cache.enabled',
      value: 'true',
      type: 'BOOLEAN',
      category: 'cache',
      description: 'Enable response caching',
      updatedBy: 'admin-1',
      updatedAt: '2026-07-11T00:00:00Z',
      metadata: {},
    }])

    renderAdminSettingsTab()

    expect(await screen.findByText('adminSettingsTab.settingLabels.cacheEnabled')).toBeVisible()
    expect(screen.queryByText('Enable response caching')).not.toBeInTheDocument()
    expect(screen.queryByText('cache.enabled')).not.toBeInTheDocument()
    expect(screen.getByText('adminSettingsTab.settingLabels.cacheEnabled').closest('.admin-setting-identity'))
      .not.toHaveAttribute('title')
  })

  it('uses a Korean fallback when the server returns an unknown setting key', async () => {
    vi.mocked(api.listSettings).mockResolvedValue([{
      tenantId: 'tenant-1',
      key: 'runtime.experimental_mode',
      value: 'true',
      type: 'BOOLEAN',
      category: 'runtime',
      description: 'Enable an experimental mode',
      updatedBy: 'admin-1',
      updatedAt: '2026-07-11T00:00:00Z',
      metadata: {},
    }])

    renderAdminSettingsTab()

    expect(await screen.findByText('adminSettingsTab.unknownSetting')).toBeVisible()
    expect(screen.queryByText('runtime experimental mode')).not.toBeInTheDocument()
    expect(screen.queryByText('runtime.experimental_mode')).not.toBeInTheDocument()
    expect(screen.queryByText('Enable an experimental mode')).not.toBeInTheDocument()
  })

  it('keeps row actions in a selected setting detail instead of the settings list', async () => {
    vi.mocked(api.listSettings).mockResolvedValue([{
      tenantId: 'tenant-1',
      key: 'runtime.guard.enabled',
      value: 'true',
      type: 'BOOLEAN',
      category: 'runtime',
      description: '실행 가드 활성화',
      updatedBy: 'admin-1',
      updatedAt: '2026-07-11T00:00:00Z',
      metadata: {},
    }])
    const user = userEvent.setup()

    renderAdminSettingsTab()

    await screen.findByText('실행 가드 활성화')
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()

    await user.click(screen.getByText('실행 가드 활성화'))

    expect(await screen.findByRole('dialog', { name: '실행 가드 활성화' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Edit' })).toBeVisible()
  })

  it('distinguishes a settings load failure from an empty settings list', async () => {
    vi.mocked(api.listSettings).mockRejectedValue(new Error('settings unavailable'))

    renderAdminSettingsTab()

    expect(await screen.findByRole('alert')).toHaveTextContent('adminSettingsTab.unavailableTitle')
    expect(screen.queryByPlaceholderText('adminSettingsTab.searchPlaceholder')).not.toBeInTheDocument()
    expect(screen.queryByText('adminSettingsTab.empty')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'adminSettingsTab.openHealth' })).toHaveAttribute('href', '/health')
    expect(screen.queryByRole('button', { name: 'adminSettingsTab.reloadSlackPromptsTitle' })).not.toBeInTheDocument()
  })
})

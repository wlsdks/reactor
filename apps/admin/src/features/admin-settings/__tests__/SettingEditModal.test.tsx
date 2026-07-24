import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { fireEvent, render, screen } from '../../../test/utils'
import { SettingEditModal } from '../ui/SettingEditModal'
import type { AdminSetting } from '../types'

function buildSetting(overrides: Partial<AdminSetting> = {}): AdminSetting {
  return {
    tenantId: 'tenant-1',
    key: 'app.name',
    value: 'MyApp',
    type: 'string',
    category: 'application',
    description: '애플리케이션 이름',
    updatedBy: 'admin-1',
    updatedAt: '2026-01-01T00:00:00Z',
    metadata: {},
    ...overrides,
  }
}

describe('SettingEditModal — type inference on open', () => {
  it('keeps the raw setting key inside collapsed developer information', async () => {
    const user = userEvent.setup()
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'runtime.guard.enabled' })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )

    expect(screen.getByText('runtime.guard.enabled')).not.toBeVisible()
    await user.click(screen.getByText('adminSettingsTab.developerDetails'))
    expect(screen.getByText('runtime.guard.enabled')).toBeVisible()
  })

  it('uses the operator setting name instead of an English backend description', () => {
    render(
      <SettingEditModal
        setting={buildSetting({
          key: 'cache.enabled',
          description: 'Enable response caching',
          value: 'true',
          type: 'boolean',
        })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )

    expect(screen.getByRole('heading', { name: 'adminSettingsTab.settingLabels.cacheEnabled' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Enable response caching' })).not.toBeInTheDocument()
  })

  it('pre-selects Boolean when setting.type === "boolean"', () => {
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'cache.enabled', value: 'true', type: 'boolean' })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )
    const select = screen.getByLabelText('settingsPage.edit.typeLabel') as HTMLSelectElement
    expect(select.value).toBe('boolean')
  })

  it('normalizes an uppercase backend type before selecting the editor', () => {
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'cache.enabled', value: 'true', type: 'BOOLEAN' })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )
    const select = screen.getByLabelText('settingsPage.edit.typeLabel') as HTMLSelectElement
    expect(select.value).toBe('boolean')
  })

  it('pre-selects Number from key heuristic (*.order)', () => {
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'menu.order', value: '', type: 'string' })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )
    const select = screen.getByLabelText('settingsPage.edit.typeLabel') as HTMLSelectElement
    expect(select.value).toBe('number')
  })

  it('pre-selects Number from requestsPerMinute key pattern', () => {
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'rateLimit.requestsPerMinute', value: '60', type: 'string' })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )
    const select = screen.getByLabelText('settingsPage.edit.typeLabel') as HTMLSelectElement
    expect(select.value).toBe('number')
  })

  it('pre-selects Object when json type + value is a JSON object', () => {
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'app.config', value: '{"x":1}', type: 'json' })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )
    const select = screen.getByLabelText('settingsPage.edit.typeLabel') as HTMLSelectElement
    expect(select.value).toBe('object')
  })

  it('pre-selects Array when json type + value is a JSON array', () => {
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'app.tags', value: '[1,2,3]', type: 'json' })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )
    const select = screen.getByLabelText('settingsPage.edit.typeLabel') as HTMLSelectElement
    expect(select.value).toBe('array')
  })

  it('falls back to String when nothing else matches', () => {
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'welcome.message', value: 'Hello', type: 'string' })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )
    const select = screen.getByLabelText('settingsPage.edit.typeLabel') as HTMLSelectElement
    expect(select.value).toBe('string')
  })
})

describe('SettingEditModal — live JSON validation', () => {
  it('shows inline validity feedback without a status badge', () => {
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'app.config', value: '{"a":1}', type: 'json' })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )
    const status = screen.getByRole('status')
    expect(status.textContent).toContain('settingsPage.edit.jsonValid')
    expect(status.className).toContain('is-valid')
    expect(status.className).not.toContain('badge')

    const textarea = screen.getByLabelText('adminSettingsTab.value') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '{bad json' } })
    expect(status.className).toContain('is-invalid')
    expect(status.textContent).toContain('settingsPage.edit.jsonInvalid')
    // Tooltip (title) holds the parse error.
    expect(status.getAttribute('title')).toBeTruthy()
  })

  it('disables Save when JSON is invalid', () => {
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'app.config', value: '{"a":1}', type: 'json' })}
        isPending={false}
        onSave={() => {}}
        onClose={() => {}}
      />,
    )
    const textarea = screen.getByLabelText('adminSettingsTab.value') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '{not json' } })
    const save = screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement
    expect(save.disabled).toBe(true)
  })
})

describe('SettingEditModal — save serialization per type', () => {
  it('saves a string value as-is', async () => {
    const onSave = vi.fn()
    const user = userEvent.setup()
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'app.name', value: 'MyApp', type: 'string' })}
        isPending={false}
        onSave={onSave}
        onClose={() => {}}
      />,
    )
    const input = screen.getByLabelText('adminSettingsTab.value') as HTMLInputElement
    await user.clear(input)
    await user.type(input, 'NewApp')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith('NewApp')
  })

  it('saves a number value normalized to string form', () => {
    const onSave = vi.fn()
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'server.port', value: '8080', type: 'number' })}
        isPending={false}
        onSave={onSave}
        onClose={() => {}}
      />,
    )
    const input = screen.getByLabelText('adminSettingsTab.value') as HTMLInputElement
    fireEvent.change(input, { target: { value: '3000' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith('3000')
  })

  it('saves a boolean via the toggle switch', () => {
    const onSave = vi.fn()
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'cache.enabled', value: 'false', type: 'boolean' })}
        isPending={false}
        onSave={onSave}
        onClose={() => {}}
      />,
    )
    const toggle = screen.getByRole('switch')
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith('true')
  })

  it('saves an object as compact JSON (whitespace stripped)', () => {
    const onSave = vi.fn()
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'app.config', value: '{"a":1}', type: 'json' })}
        isPending={false}
        onSave={onSave}
        onClose={() => {}}
      />,
    )
    const textarea = screen.getByLabelText('adminSettingsTab.value') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '{"a": 1, "b":  2}' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith('{"a":1,"b":2}')
  })

  it('saves an array as compact JSON', () => {
    const onSave = vi.fn()
    render(
      <SettingEditModal
        setting={buildSetting({ key: 'app.tags', value: '[1,2,3]', type: 'json' })}
        isPending={false}
        onSave={onSave}
        onClose={() => {}}
      />,
    )
    const textarea = screen.getByLabelText('adminSettingsTab.value') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '[1,   2, 3, 4]' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).toHaveBeenCalledWith('[1,2,3,4]')
  })
})

import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { DashboardHealthBar } from '../ui/DashboardHealthBar'
import type { PlatformReadiness } from '../readiness'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({ t: (key: string) => key }),
  }
})

vi.mock('../../../shared/lib', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../shared/lib')>()
  return {
    ...actual,
    useRelativeTime: (input: unknown) => (input ? '방금 전' : ''),
  }
})

function makeReadiness(level: 'GREEN' | 'YELLOW' | 'RED'): PlatformReadiness {
  return {
    level,
    labelKey: 'dashboard.readiness.summary',
    actionKey: 'dashboard.readiness.action',
  }
}

describe('DashboardHealthBar', () => {
  it('presents readiness as one localized decision sentence', () => {
    const { container } = render(
      <DashboardHealthBar
        readiness={makeReadiness('RED')}
        issueSnapshot={undefined}
        mcpConnected={1}
        mcpTotal={3}
        groundedPercent={42}
      />,
    )

    expect(container.textContent).toContain('dashboard.readiness.summary')
    expect(container.textContent).toContain('dashboard.readiness.action')
    expect(container.querySelectorAll('.health-bar__chip')).toHaveLength(0)
    expect(container.querySelector('.health-bar__dot')).toHaveStyle({ background: 'var(--red)' })
  })

  it('hides the update timestamp when no source timestamp exists', () => {
    const { container } = render(
      <DashboardHealthBar
        readiness={makeReadiness('GREEN')}
        issueSnapshot={undefined}
        mcpConnected={0}
        mcpTotal={0}
        groundedPercent={0}
      />,
    )

    expect(container.textContent).not.toContain('dashboard.healthBar.lastUpdated')
  })

  it('renders the localized update timestamp when source evidence exists', () => {
    const { container } = render(
      <DashboardHealthBar
        readiness={makeReadiness('GREEN')}
        issueSnapshot={undefined}
        mcpConnected={0}
        mcpTotal={0}
        groundedPercent={0}
        updatedAt={Date.now()}
      />,
    )

    expect(container.textContent).toContain('dashboard.healthBar.lastUpdated')
    expect(container.textContent).toContain('방금 전')
  })
})

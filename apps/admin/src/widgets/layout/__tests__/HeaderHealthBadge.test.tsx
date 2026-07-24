import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { MemoryRouter } from 'react-router-dom'
import { HeaderHealthBadge } from '../HeaderHealthBadge'
import type { GlobalHealth } from '../../../features/health'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

const mockUseGlobalHealth = vi.fn<[], GlobalHealth>()
vi.mock('../../../features/health', () => ({
  useGlobalHealth: () => mockUseGlobalHealth(),
}))

function buildHealth(overrides: Partial<GlobalHealth> = {}): GlobalHealth {
  return {
    summary: {
      summary: 'All systems operational',
      status: 'OK',
      generatedAt: new Date(Date.now() - 30_000).toISOString(),
      allHealthy: true,
    },
    report: undefined,
    isLoading: false,
    isError: false,
    error: undefined,
    passed: 0,
    total: 0,
    criticalCount: 0,
    warnCount: 0,
    generatedAt: new Date(Date.now() - 30_000).toISOString(),
    effectiveStatus: 'OK',
    ...overrides,
  }
}

function renderBadge() {
  return render(
    <MemoryRouter>
      <HeaderHealthBadge />
    </MemoryRouter>,
  )
}

describe('HeaderHealthBadge', () => {
  beforeEach(() => {
    mockNavigate.mockReset()
    mockUseGlobalHealth.mockReset()
  })

  it('renders OK status with status dot and label', () => {
    mockUseGlobalHealth.mockReturnValue(buildHealth({ summary: { summary: 'ok', status: 'OK', generatedAt: new Date().toISOString(), allHealthy: true } }))
    renderBadge()
    const button = screen.getByRole('button', { name: /header\.health\.statusOk/ })
    expect(button).toBeInTheDocument()
    expect(button).toHaveAttribute('data-status', 'ok')
    expect(button.textContent).toContain('header.health.statusOk')
  })

  it('renders WARN intent with critical count when issues exist', () => {
    mockUseGlobalHealth.mockReturnValue(
      buildHealth({
        summary: { summary: 'warn', status: 'WARN', generatedAt: new Date().toISOString(), allHealthy: false },
        effectiveStatus: 'WARN',
        passed: 7,
        total: 8,
        criticalCount: 0,
        warnCount: 1,
      }),
    )
    renderBadge()
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('data-status', 'warn')
    expect(button.textContent).toContain('header.health.statusWarn')
  })

  it('uses the detailed effective status when the summary is optimistic', () => {
    mockUseGlobalHealth.mockReturnValue(buildHealth({
      summary: { summary: 'ok', status: 'OK', generatedAt: new Date().toISOString(), allHealthy: true },
      effectiveStatus: 'WARN',
      passed: 1,
      total: 3,
      warnCount: 2,
    }))

    renderBadge()

    expect(screen.getByRole('button')).toHaveAttribute('data-status', 'warn')
  })

  it('renders ERROR intent and shows critical count when criticalCount > 0', () => {
    mockUseGlobalHealth.mockReturnValue(
      buildHealth({
        summary: { summary: 'err', status: 'ERROR', generatedAt: new Date().toISOString(), allHealthy: false },
        effectiveStatus: 'ERROR',
        passed: 6,
        total: 8,
        criticalCount: 2,
        warnCount: 0,
      }),
    )
    renderBadge()
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('data-status', 'error')
    expect(button.textContent).toContain('header.health.statusError')
    expect(button.textContent).toContain('2')
  })

  it('renders loading placeholder when summary not yet loaded', () => {
    mockUseGlobalHealth.mockReturnValue(
      buildHealth({
        summary: undefined,
        isLoading: true,
        generatedAt: undefined,
      }),
    )
    renderBadge()
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('data-status', 'unknown')
    expect(button.textContent).toContain('header.health.statusUnknown')
  })

  it('renders unavailable state on error and surfaces error message in tooltip', () => {
    mockUseGlobalHealth.mockReturnValue(
      buildHealth({
        summary: undefined,
        isError: true,
        error: new Error('Network down'),
        generatedAt: undefined,
      }),
    )
    renderBadge()
    const button = screen.getByRole('button')
    expect(button).toHaveAttribute('data-status', 'unavailable')
    expect(button.textContent).toContain('header.health.statusUnavailable')
    expect(button.getAttribute('title')).toContain('Network down')
  })

  it('navigates to /health on click', () => {
    mockUseGlobalHealth.mockReturnValue(buildHealth())
    renderBadge()
    fireEvent.click(screen.getByRole('button'))
    expect(mockNavigate).toHaveBeenCalledWith('/health')
  })

  it('includes click hint in the tooltip', () => {
    mockUseGlobalHealth.mockReturnValue(buildHealth())
    renderBadge()
    const button = screen.getByRole('button')
    expect(button.getAttribute('title')).toContain('header.health.clickHint')
  })
})

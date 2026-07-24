import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { PlatformAdminRedirect } from '../PlatformAdminRedirect'
import {
  resolveRedirectDestination,
  buildPreservedDestination,
} from '../redirectMappings'

function LocationCapture() {
  const location = useLocation()
  return (
    <div>
      <span data-testid="captured-pathname">{location.pathname}</span>
      <span data-testid="captured-search">{location.search}</span>
    </div>
  )
}

describe('resolveRedirectDestination', () => {
  it('maps health tab to /health', () => {
    expect(resolveRedirectDestination('health').destination).toBe('/health')
  })

  it('maps tenants tab to /tenants', () => {
    expect(resolveRedirectDestination('tenants').destination).toBe('/tenants')
  })

  it('maps pricing tab to /models?tab=pricing', () => {
    expect(resolveRedirectDestination('pricing').destination).toBe('/models?tab=pricing')
  })

  it('maps roles tab to /access-control?tab=members', () => {
    expect(resolveRedirectDestination('roles').destination).toBe('/access-control?tab=members')
  })

  it('maps retention tab to the platform settings retention workspace', () => {
    expect(resolveRedirectDestination('retention').destination).toBe('/settings?tab=retention')
  })

  it('maps settings tab to /settings', () => {
    expect(resolveRedirectDestination('settings').destination).toBe('/settings')
  })

  it('maps tenant (singular) drill-down tab to /tenants?tab=tenant', () => {
    expect(resolveRedirectDestination('tenant').destination).toBe('/tenants?tab=tenant')
  })

  it('falls back to /tenants for unknown tab values', () => {
    const result = resolveRedirectDestination('unknown-thing')
    expect(result.destination).toBe('/tenants')
    expect(result.isFallback).toBe(true)
  })

  it('falls back to /tenants when tab is null', () => {
    const result = resolveRedirectDestination(null)
    expect(result.destination).toBe('/tenants')
    expect(result.isFallback).toBe(true)
  })

  it('returns a human label for each known tab', () => {
    expect(resolveRedirectDestination('health').destinationLabel).toBe('Health')
    expect(resolveRedirectDestination('pricing').destinationLabel).toBe('Models · Pricing')
    expect(resolveRedirectDestination('roles').destinationLabel).toBe('Access Control · Members')
  })
})

describe('buildPreservedDestination', () => {
  it('returns destination unchanged when no extra params', () => {
    expect(buildPreservedDestination('/health', new URLSearchParams('tab=health'))).toBe('/health')
  })

  it('preserves unrelated query params', () => {
    const result = buildPreservedDestination(
      '/health',
      new URLSearchParams('tab=health&filter=active&page=2'),
    )
    expect(result).toContain('filter=active')
    expect(result).toContain('page=2')
    expect(result).not.toContain('tab=health')
  })

  it('keeps existing destination query params intact', () => {
    const result = buildPreservedDestination(
      '/models?tab=pricing',
      new URLSearchParams('tab=pricing&model=gpt-4'),
    )
    expect(result).toContain('tab=pricing')
    expect(result).toContain('model=gpt-4')
  })

  it('does not overwrite a destination param with the same key from source', () => {
    const result = buildPreservedDestination(
      '/access-control?tab=members',
      new URLSearchParams('tab=roles&tab=ignored'),
    )
    // destination's tab=members must win
    expect(result).toContain('tab=members')
    expect(result).not.toContain('tab=roles')
  })

  it('drops the tab param entirely when destination has no query', () => {
    const result = buildPreservedDestination('/settings?tab=retention', new URLSearchParams('tab=retention'))
    expect(result).toBe('/settings?tab=retention')
  })
})

function renderRedirectAt(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/old" element={<PlatformAdminRedirect />} />
        <Route path="*" element={<LocationCapture />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('PlatformAdminRedirect (integration)', () => {
  it('navigates to /health for tab=health', () => {
    renderRedirectAt('/old?tab=health')
    expect(screen.getByTestId('captured-pathname')).toHaveTextContent('/health')
  })

  it('navigates to /tenants for tab=tenants', () => {
    renderRedirectAt('/old?tab=tenants')
    expect(screen.getByTestId('captured-pathname')).toHaveTextContent('/tenants')
  })

  it('navigates to /models?tab=pricing for tab=pricing', () => {
    renderRedirectAt('/old?tab=pricing')
    expect(screen.getByTestId('captured-pathname')).toHaveTextContent('/models')
    expect(screen.getByTestId('captured-search')).toHaveTextContent('tab=pricing')
  })

  it('navigates to /access-control?tab=members for tab=roles', () => {
    renderRedirectAt('/old?tab=roles')
    expect(screen.getByTestId('captured-pathname')).toHaveTextContent('/access-control')
    expect(screen.getByTestId('captured-search')).toHaveTextContent('tab=members')
  })

  it('navigates to the settings retention tab for tab=retention', () => {
    renderRedirectAt('/old?tab=retention')
    expect(screen.getByTestId('captured-pathname')).toHaveTextContent('/settings')
    expect(screen.getByTestId('captured-search')).toHaveTextContent('tab=retention')
  })

  it('navigates to /settings for tab=settings', () => {
    renderRedirectAt('/old?tab=settings')
    expect(screen.getByTestId('captured-pathname')).toHaveTextContent('/settings')
  })

  it('navigates to /tenants?tab=tenant for tab=tenant', () => {
    renderRedirectAt('/old?tab=tenant')
    expect(screen.getByTestId('captured-pathname')).toHaveTextContent('/tenants')
    expect(screen.getByTestId('captured-search')).toHaveTextContent('tab=tenant')
  })

  it('falls back to /tenants for unknown tab', () => {
    renderRedirectAt('/old?tab=garbage')
    expect(screen.getByTestId('captured-pathname')).toHaveTextContent('/tenants')
  })

  it('falls back to /tenants when no tab param', () => {
    renderRedirectAt('/old')
    expect(screen.getByTestId('captured-pathname')).toHaveTextContent('/tenants')
  })

  it('preserves unrelated query params across the redirect', () => {
    renderRedirectAt('/old?tab=health&filter=active&page=2')
    expect(screen.getByTestId('captured-pathname')).toHaveTextContent('/health')
    expect(screen.getByTestId('captured-search')).toHaveTextContent('filter=active')
    expect(screen.getByTestId('captured-search')).toHaveTextContent('page=2')
  })
})

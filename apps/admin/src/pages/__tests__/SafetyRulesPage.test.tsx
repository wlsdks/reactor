import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { fireEvent, render, screen } from '../../test/utils'
import { describe, expect, it, vi } from 'vitest'
import { SafetyRulesPage } from '../SafetyRulesPage'

vi.mock('../../features/input-guard', () => ({
  InputGuardManager: ({ embedded }: { embedded?: boolean }) => (
    <div data-testid="input-guard" data-embedded={String(embedded)} />
  ),
}))

vi.mock('../../features/output-guard', () => ({
  OutputGuardManager: ({ embedded }: { embedded?: boolean }) => (
    <div data-testid="output-guard" data-embedded={String(embedded)} />
  ),
}))

vi.mock('../../features/tool-policy', () => ({
  ToolPolicyManager: ({ embedded }: { embedded?: boolean }) => (
    <div data-testid="tool-policy" data-embedded={String(embedded)} />
  ),
}))

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>
}

function renderPage(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/safety-rules"
          element={(
            <>
              <SafetyRulesPage />
              <LocationProbe />
            </>
          )}
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SafetyRulesPage', () => {
  it('opens the input guard as the first safety boundary', () => {
    renderPage('/safety-rules')

    expect(screen.getByRole('tab', { name: 'safetyRules.tabInputGuard' }))
      .toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('input-guard')).toHaveAttribute('data-embedded', 'true')
    expect(screen.queryByTestId('output-guard')).not.toBeInTheDocument()
  })

  it('keeps legacy output guard query links addressable', () => {
    renderPage('/safety-rules?tab=output-guard')

    expect(screen.getByRole('tab', { name: 'safetyRules.tabOutputGuard' }))
      .toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('output-guard')).toHaveAttribute('data-embedded', 'true')
  })

  it('writes tool policy tab changes to the URL', () => {
    renderPage('/safety-rules?tab=input-guard')

    fireEvent.click(screen.getByRole('tab', { name: 'safetyRules.tabToolPolicy' }))

    expect(screen.getByTestId('location')).toHaveTextContent('/safety-rules?tab=tool-policy')
    expect(screen.getByTestId('tool-policy')).toHaveAttribute('data-embedded', 'true')
  })
})

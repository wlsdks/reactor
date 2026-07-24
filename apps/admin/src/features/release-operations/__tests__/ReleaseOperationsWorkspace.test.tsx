import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '../../../test/utils'
import { ReleaseOperationsWorkspace } from '../ui/ReleaseOperationsWorkspace'
import * as releaseOperationsData from '../useReleaseOperationsData'

vi.mock('../useReleaseOperationsData', () => ({
  useReleaseOperationsData: vi.fn(),
}))

vi.mock('../../dashboard/ui/ReleaseCockpit', () => ({
  ReleaseCockpit: ({ view }: { view?: string }) => (
    <div data-testid="release-cockpit" data-view={view ?? 'all'} />
  ),
}))

const useReleaseOperationsDataMock = vi.mocked(releaseOperationsData.useReleaseOperationsData)

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{`${location.pathname}${location.search}${location.hash}`}</output>
}

function renderWorkspace(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/release"
          element={(
            <>
              <ReleaseOperationsWorkspace />
              <LocationProbe />
            </>
          )}
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ReleaseOperationsWorkspace', () => {
  beforeEach(() => {
    useReleaseOperationsDataMock.mockReturnValue({
      readiness: { status: 'eligible_with_warnings' },
      isLoading: false,
      isFetching: false,
      error: null,
      refetch: vi.fn(),
    } as never)
  })

  it('maps the legacy cockpit anchor to the decision view', () => {
    renderWorkspace('/release#release-cockpit')

    expect(screen.getByRole('tab', { name: 'releaseOperations.views.decision' }))
      .toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('release-cockpit')).toHaveAttribute('data-view', 'decision')
    expect(screen.queryByTestId('release-workflow')).not.toBeInTheDocument()
  })

  it('maps the legacy workflow anchor to the product boundary view', () => {
    renderWorkspace('/release#release-workflow')

    expect(screen.getByRole('tab', { name: 'releaseOperations.views.boundary' }))
      .toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('release-cockpit')).toHaveAttribute('data-view', 'boundary')
    expect(screen.queryByTestId('release-workflow')).not.toBeInTheDocument()
  })

  it('uses the explicit evidence query view and keeps it in the URL', () => {
    renderWorkspace('/release?view=evidence#release-evidence')

    expect(screen.getByRole('tab', { name: 'releaseOperations.views.evidence' }))
      .toHaveAttribute('aria-selected', 'true')
    expect(screen.getByTestId('release-cockpit')).toHaveAttribute('data-view', 'evidence')
    expect(screen.getByTestId('location')).toHaveTextContent('/release?view=evidence#release-evidence')
  })

  it('writes tab changes to an addressable URL', () => {
    renderWorkspace('/release#release-cockpit')

    fireEvent.click(screen.getByRole('tab', { name: 'releaseOperations.views.boundary' }))

    expect(screen.getByTestId('location')).toHaveTextContent('/release?view=boundary#release-workflow')
    expect(screen.queryByTestId('release-workflow')).not.toBeInTheDocument()
  })

  it('fails closed when release data cannot be loaded and no prior result exists', () => {
    const refetch = vi.fn()
    useReleaseOperationsDataMock.mockReturnValue({
      readiness: null,
      isLoading: false,
      isFetching: false,
      error: 'HTTP 503',
      refetch,
    } as never)

    renderWorkspace('/release#release-cockpit')

    expect(screen.getByRole('alert')).toHaveTextContent('releaseOperations.unavailableTitle')
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByTestId('release-cockpit')).not.toBeInTheDocument()
    expect(screen.getByText('releaseOperations.technicalError').closest('details')).not.toHaveAttribute('open')
    fireEvent.click(screen.getByRole('button', { name: 'releaseOperations.retry' }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })
})

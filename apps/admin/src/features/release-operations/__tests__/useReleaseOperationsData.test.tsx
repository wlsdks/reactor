import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import * as dashboardApi from '../../dashboard/api'
import { useReleaseOperationsData } from '../useReleaseOperationsData'

vi.mock('../../dashboard/api', () => ({ getDashboard: vi.fn() }))

const getDashboardMock = vi.mocked(dashboardApi.getDashboard)

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  )
}

describe('useReleaseOperationsData', () => {
  it('selects release readiness from the canonical dashboard query', async () => {
    getDashboardMock.mockResolvedValue({
      releaseReadiness: {
        status: 'passed',
        summary: { passed: 4, total: 4 },
      },
    } as Awaited<ReturnType<typeof dashboardApi.getDashboard>>)

    const { result } = renderHook(() => useReleaseOperationsData(), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.readiness?.status).toBe('passed')
    expect(getDashboardMock).toHaveBeenCalledWith()
  })

  it('keeps load failures local to the release workspace', async () => {
    getDashboardMock.mockRejectedValue(new Error('backend unavailable'))

    const { result } = renderHook(() => useReleaseOperationsData(), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.readiness).toBeNull()
    expect(result.current.error).toBe('backend unavailable')
  })
})

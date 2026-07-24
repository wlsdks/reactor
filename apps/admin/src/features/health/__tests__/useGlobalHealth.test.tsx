import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useGlobalHealth } from '../useGlobalHealth'
import * as doctorApi from '../../doctor/api'

vi.mock('../../doctor/api')

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe('useGlobalHealth', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('returns isLoading=true while the summary query is in flight', () => {
    vi.mocked(doctorApi.getDoctorSummary).mockImplementation(() => new Promise(() => {}))
    vi.mocked(doctorApi.getDoctorReport).mockImplementation(() => new Promise(() => {}))
    const { result } = renderHook(() => useGlobalHealth(), { wrapper: makeWrapper() })
    expect(result.current.isLoading).toBe(true)
    expect(result.current.summary).toBeUndefined()
    expect(result.current.report).toBeUndefined()
  })

  it('exposes summary data after the summary query resolves', async () => {
    vi.useRealTimers()
    vi.mocked(doctorApi.getDoctorSummary).mockResolvedValue({
      summary: 'all good',
      status: 'OK',
      generatedAt: '2026-04-25T12:00:00Z',
      allHealthy: true,
    })
    vi.mocked(doctorApi.getDoctorReport).mockResolvedValue({
      generatedAt: '2026-04-25T12:00:00Z',
      sections: [],
    })
    const { result } = renderHook(() => useGlobalHealth(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.summary).toBeDefined())
    expect(result.current.summary?.status).toBe('OK')
    expect(result.current.generatedAt).toBe('2026-04-25T12:00:00Z')
  })

  it('aggregates operator-facing section status and treats skipped sections as attention', async () => {
    vi.useRealTimers()
    vi.mocked(doctorApi.getDoctorSummary).mockResolvedValue({
      summary: 'mixed',
      status: 'WARN',
      generatedAt: '2026-04-25T12:00:00Z',
      allHealthy: false,
    })
    vi.mocked(doctorApi.getDoctorReport).mockResolvedValue({
      generatedAt: '2026-04-25T12:00:00Z',
      sections: [
        {
          name: 'sec-a',
          status: 'OK',
          message: 'ok',
          checks: [
            { name: 'a1', status: 'OK', detail: '' },
            { name: 'a2', status: 'OK', detail: '' },
          ],
        },
        {
          name: 'sec-b',
          status: 'ERROR',
          message: 'broken',
          checks: [
            { name: 'b1', status: 'ERROR', detail: 'down' },
            { name: 'b2', status: 'WARN', detail: 'slow' },
            { name: 'b3', status: 'SKIPPED', detail: 'n/a' },
          ],
        },
        {
          name: 'sec-c',
          status: 'SKIPPED',
          message: 'not configured',
          checks: [],
        },
      ],
    })
    const { result } = renderHook(() => useGlobalHealth(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.report).toBeDefined())
    expect(result.current.total).toBe(3)
    expect(result.current.passed).toBe(1)
    expect(result.current.criticalCount).toBe(1)
    expect(result.current.warnCount).toBe(1)
    expect(result.current.effectiveStatus).toBe('ERROR')
  })

  it('does not call getDoctorReport until summary loads (lazy enabling)', async () => {
    let resolveSummary: ((v: unknown) => void) | null = null
    vi.mocked(doctorApi.getDoctorSummary).mockReturnValue(
      new Promise((resolve) => {
        resolveSummary = resolve as (v: unknown) => void
      }),
    )
    vi.mocked(doctorApi.getDoctorReport).mockResolvedValue({
      generatedAt: 't',
      sections: [],
    })
    vi.useRealTimers()
    const { result, rerender } = renderHook(() => useGlobalHealth(), { wrapper: makeWrapper() })
    // Before summary resolves: report query should not have fired
    expect(result.current.summary).toBeUndefined()
    expect(doctorApi.getDoctorReport).not.toHaveBeenCalled()
    // Resolve summary; report now becomes enabled
    resolveSummary!({
      summary: 's',
      status: 'OK',
      generatedAt: 't',
      allHealthy: true,
    })
    await waitFor(() => expect(result.current.summary).toBeDefined())
    rerender()
    await waitFor(() => expect(doctorApi.getDoctorReport).toHaveBeenCalled())
  })

  it('returns isError when the summary query fails', async () => {
    vi.useRealTimers()
    vi.mocked(doctorApi.getDoctorSummary).mockRejectedValue(new Error('500 Internal'))
    vi.mocked(doctorApi.getDoctorReport).mockResolvedValue({
      generatedAt: 't',
      sections: [],
    })
    const { result } = renderHook(() => useGlobalHealth(), { wrapper: makeWrapper() })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(Error)
  })
})

import { describe, expect, it } from 'vitest'
import { mockDoctorReport, mockDoctorSummary } from '../doctor'

describe('doctor mock handlers', () => {
  it('serves a backend-compatible partial local health summary', async () => {
    const response = await fetch('http://localhost/api/admin/doctor/summary')

    expect(response.ok).toBe(true)
    expect(response.headers.get('X-Doctor-Status')).toBe('OK')
    await expect(response.json()).resolves.toEqual(mockDoctorSummary)
    expect(mockDoctorSummary.allHealthy).toBe(true)
    expect(mockDoctorSummary.summary).toContain('SKIPPED 2')
  })

  it('serves the runtime, settings, and RAG diagnostic sections', async () => {
    const response = await fetch('http://localhost/api/admin/doctor')

    expect(response.ok).toBe(true)
    await expect(response.json()).resolves.toEqual(mockDoctorReport)
    expect(mockDoctorReport.sections.map((section) => section.status)).toEqual([
      'OK',
      'SKIPPED',
      'SKIPPED',
    ])
  })

  it('returns the same immutable health contract across polling requests', async () => {
    const responses = await Promise.all([
      fetch('http://localhost/api/admin/doctor/summary'),
      fetch('http://localhost/api/admin/doctor/summary'),
    ])
    const summaries = await Promise.all(responses.map((response) => response.json()))

    expect(summaries).toEqual([mockDoctorSummary, mockDoctorSummary])
    expect(summaries[0]).not.toBe(summaries[1])
  })
})

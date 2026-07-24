import { http, HttpResponse } from 'msw'
import type { DoctorReport, DoctorSummary } from '../../features/doctor/types'
import { NOW } from './shared'

const generatedAt = new Date(NOW).toISOString()

export const mockDoctorReport: DoctorReport = {
  generatedAt,
  status: 'OK',
  allHealthy: true,
  summary: '3 sections - OK 1, WARN 0, ERROR 0, SKIPPED 2',
  sections: [
    {
      name: 'FastAPI Runtime',
      status: 'OK',
      checks: [
        {
          name: 'application',
          status: 'OK',
          detail: 'FastAPI router is responding',
        },
      ],
      message: 'runtime available',
    },
    {
      name: 'Runtime Settings',
      status: 'SKIPPED',
      checks: [],
      message: 'runtime settings store is not configured',
    },
    {
      name: 'RAG Store',
      status: 'SKIPPED',
      checks: [],
      message: 'RAG store is not configured',
    },
  ],
}

export const mockDoctorSummary: DoctorSummary = {
  generatedAt,
  status: 'OK',
  allHealthy: true,
  summary: '3 sections - OK 1, WARN 0, ERROR 0, SKIPPED 2',
}

const doctorHeaders = { 'X-Doctor-Status': mockDoctorSummary.status }

export const doctorHandlers = [
  http.get('/api/admin/doctor/summary', () =>
    HttpResponse.json(mockDoctorSummary, { headers: doctorHeaders }),
  ),
  http.get('/api/admin/doctor', () =>
    HttpResponse.json(mockDoctorReport, { headers: doctorHeaders }),
  ),
]

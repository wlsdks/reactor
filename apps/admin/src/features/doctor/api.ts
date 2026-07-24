import type { DoctorCheck, DoctorReport, DoctorSection, DoctorStatus, DoctorSummary } from './types'
import { api } from '../../shared/api/client'

type RecordLike = Record<string, unknown>

function record(value: unknown): RecordLike {
  return typeof value === 'object' && value !== null ? value as RecordLike : {}
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function status(value: unknown): DoctorStatus {
  return value === 'OK' || value === 'WARN' || value === 'ERROR' || value === 'SKIPPED'
    ? value
    : 'ERROR'
}

function check(value: unknown): DoctorCheck {
  const raw = record(value)
  return { name: text(raw.name), status: status(raw.status), detail: text(raw.detail) }
}

function section(value: unknown): DoctorSection {
  const raw = record(value)
  return {
    name: text(raw.name),
    status: status(raw.status),
    checks: Array.isArray(raw.checks) ? raw.checks.map(check) : [],
    message: text(raw.message),
  }
}

function summary(value: unknown): DoctorSummary {
  const raw = record(value)
  const resolvedStatus = status(raw.status)
  return {
    summary: text(raw.summary),
    status: resolvedStatus === 'SKIPPED' ? 'WARN' : resolvedStatus,
    generatedAt: text(raw.generatedAt),
    allHealthy: raw.allHealthy === true,
  }
}

/** Diagnostic HTTP 500 responses still contain the report and must remain visible. */
export const getDoctorSummary = async (): Promise<DoctorSummary> => {
  const raw: unknown = await api.get('admin/doctor/summary', { throwHttpErrors: false }).json()
  return summary(raw)
}

/** Diagnostic HTTP 500 responses are a valid unhealthy report, not a transport failure. */
export const getDoctorReport = async (): Promise<DoctorReport> => {
  const raw: unknown = await api.get('admin/doctor', { throwHttpErrors: false }).json()
  const base = summary(raw)
  const body = record(raw)
  return {
    ...base,
    sections: Array.isArray(body.sections) ? body.sections.map(section) : [],
  }
}

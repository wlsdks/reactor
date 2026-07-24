import type { DoctorReport, DoctorStatus } from './types'

const STATUS_PRIORITY: Record<DoctorStatus, number> = {
  OK: 0,
  SKIPPED: 1,
  WARN: 2,
  ERROR: 3,
}
/**
 * Produces the operator-facing status from the detailed report instead of
 * trusting a possibly optimistic summary. Skipped diagnostics are treated as
 * attention, because an unconfigured dependency is not evidence of health.
 */
export function deriveDoctorDisplayStatus(report: DoctorReport | undefined): Exclude<DoctorStatus, 'SKIPPED'> | undefined {
  if (!report || report.sections.length === 0) return undefined

  const worst = report.sections.reduce<DoctorStatus>((current, section) => {
    const sectionWorst = section.checks.reduce<DoctorStatus>(
      (checkStatus, check) => STATUS_PRIORITY[check.status] > STATUS_PRIORITY[checkStatus] ? check.status : checkStatus,
      section.status,
    )
    return STATUS_PRIORITY[sectionWorst] > STATUS_PRIORITY[current] ? sectionWorst : current
  }, 'OK')

  return worst === 'SKIPPED' ? 'WARN' : worst
}

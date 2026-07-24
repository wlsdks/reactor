export type DoctorStatus = 'OK' | 'WARN' | 'ERROR' | 'SKIPPED'

export interface DoctorCheck {
  name: string
  status: DoctorStatus
  detail: string
}

export interface DoctorSection {
  name: string
  status: DoctorStatus
  checks: DoctorCheck[]
  message: string
}

// GET /api/admin/doctor
export interface DoctorReport {
  generatedAt: string
  status: 'OK' | 'WARN' | 'ERROR'
  allHealthy: boolean
  summary: string
  sections: DoctorSection[]
}

// GET /api/admin/doctor/summary
export interface DoctorSummary {
  summary: string
  status: 'OK' | 'WARN' | 'ERROR'
  generatedAt: string
  allHealthy: boolean
}

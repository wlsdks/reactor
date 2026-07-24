import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { SectionErrorBoundary, DetailModal } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getDoctorReport } from '../api'
import type { DoctorStatus } from '../types'

interface DoctorDetailModalProps {
  open: boolean
  onClose: () => void
}

function statusBadgeClass(status: DoctorStatus): string {
  switch (status) {
    case 'OK':
      return 'badge badge-green'
    case 'WARN':
      return 'badge badge-yellow'
    case 'ERROR':
      return 'badge badge-red'
    case 'SKIPPED':
    default:
      return 'badge badge-gray'
  }
}

function DoctorDetailContent() {
  const { t } = useTranslation()
  const [showRaw, setShowRaw] = useState(false)

  const { data: report, isLoading } = useQuery({
    queryKey: queryKeys.doctor.report(),
    queryFn: getDoctorReport,
  })

  const sections = report?.sections ?? []

  return (
    <>
      {isLoading && <p>{t('common.loading')}</p>}
      {!isLoading && !report && <p>{t('doctor.unavailable')}</p>}
      {report && sections.length === 0 && <p>{t('doctor.noSections')}</p>}
      {report && sections.length > 0 && (
        <>
          {sections.map((section) => (
            <section
              key={section.name}
              style={{ marginBottom: 'var(--space-4)' }}
            >
              <header
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-2)',
                  marginBottom: 'var(--space-2)',
                }}
              >
                <span className={statusBadgeClass(section.status)}>
                  {section.status}
                </span>
                <strong>{section.name}</strong>
                <span
                  style={{
                    color: 'var(--text-muted)',
                    fontSize: 'var(--text-sm)',
                  }}
                >
                  — {section.message}
                </span>
              </header>
              {section.checks.length > 0 && (
                <table className="data-table" style={{ width: '100%' }}>
                  <thead>
                    <tr>
                      <th scope="col">{t('doctor.check')}</th>
                      <th scope="col">{t('common.status')}</th>
                      <th scope="col">{t('doctor.detail')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {section.checks.map((check) => (
                      <tr key={`${section.name}:${check.name}`}>
                        <td>{check.name}</td>
                        <td>
                          <span className={statusBadgeClass(check.status)}>
                            {check.status}
                          </span>
                        </td>
                        <td>{check.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          ))}
          <div style={{ marginTop: 'var(--space-3)' }}>
            <button
              className="btn btn-sm btn-secondary"
              onClick={() => setShowRaw((v) => !v)}
            >
              {showRaw ? t('doctor.hideRaw') : t('doctor.showRaw')}
            </button>
            {showRaw && (
              <pre
                className="code-block"
                style={{
                  marginTop: 'var(--space-2)',
                  maxHeight: 300,
                  overflow: 'auto',
                }}
              >
                {JSON.stringify(report, null, 2)}
              </pre>
            )}
          </div>
        </>
      )}
    </>
  )
}

export function DoctorDetailModal({ open, onClose }: DoctorDetailModalProps) {
  const { t } = useTranslation()

  return (
    <DetailModal
      open={open}
      title={t('doctor.diagnosticReport')}
      onClose={onClose}
    >
      <SectionErrorBoundary name="doctor-detail">
        <DoctorDetailContent />
      </SectionErrorBoundary>
    </DetailModal>
  )
}

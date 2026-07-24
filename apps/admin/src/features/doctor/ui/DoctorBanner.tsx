import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { STALE_TIMES } from '../../../shared/lib/staleTimes'
import { useRoleVisibility } from '../../workspace/RoleVisibilityProvider'
import { getDoctorSummary } from '../api'
import { DoctorDetailModal } from './DoctorDetailModal'

export function DoctorBanner() {
  const { t } = useTranslation()
  const { effectiveRole } = useRoleVisibility()
  const [detailOpen, setDetailOpen] = useState(false)

  const { data: summary } = useQuery({
    queryKey: queryKeys.doctor.summary(),
    queryFn: getDoctorSummary,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    staleTime: STALE_TIMES.STANDARD,
  })

  if (effectiveRole === 'ADMIN_MANAGER') return null
  if (!summary) return null
  if (summary.allHealthy) return null

  const alertClass =
    summary.status === 'ERROR'
      ? 'alert alert-error alert-with-retry'
      : 'alert alert-warning alert-with-retry'

  return (
    <>
      <div className={alertClass} role="status" aria-live="polite">
        <span className="alert-message">{summary.summary}</span>
        <button
          className="btn btn-sm btn-secondary"
          onClick={() => setDetailOpen(true)}
        >
          {t('doctor.viewDetails')}
        </button>
      </div>
      <DoctorDetailModal
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      />
    </>
  )
}

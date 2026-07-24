import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { queryKeys } from '../../../shared/lib/queryKeys'
import { StatusBadge } from '../../../shared/ui/StatusBadge'
import { getFaqSchedulerHealth } from '../api'

const POLL_INTERVAL_MS = 60_000

/**
 * Thin status indicator at the top of the FAQ tab that surfaces FAQ scheduler
 * health. Renders nothing when the scheduler is OK to keep visual noise low —
 * we only draw attention when something is off.
 */
export function FaqSchedulerHealthBar() {
  const { t } = useTranslation()

  const { data } = useQuery({
    queryKey: queryKeys.slackFaq.schedulerHealth(),
    queryFn: getFaqSchedulerHealth,
    refetchInterval: POLL_INTERVAL_MS,
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
  })

  if (!data) return null

  if (data.enabled === false) {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="faq-scheduler-health-bar"
        data-testid="faq-scheduler-health-bar"
      >
        <StatusBadge status="DISABLED" label={t('slackFaq.scheduler.disabled')} />
      </div>
    )
  }

  if (data.status === 'OK') {
    return null
  }

  const isDown = data.status === 'DOWN'

  return (
    <div
      role="status"
      aria-live={isDown ? 'assertive' : 'polite'}
      aria-atomic="true"
      className="faq-scheduler-health-bar"
      data-testid="faq-scheduler-health-bar"
    >
      <StatusBadge
        status={isDown ? 'FAILED' : 'WARN'}
        label={
          isDown
            ? t('slackFaq.scheduler.down')
            : t('slackFaq.scheduler.degraded')
        }
      />
    </div>
  )
}

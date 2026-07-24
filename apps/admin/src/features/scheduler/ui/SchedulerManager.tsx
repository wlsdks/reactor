import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { usePageHelp } from '../../../shared/lib/usePageHelp'
import { PageHeader, Tabs } from '../../../shared/ui'
import { SchedulerJobsTab } from './SchedulerJobsTab'
import { SchedulerExecutionsTab } from './SchedulerExecutionsTab'
import './SchedulerManager.css'

// ── Tab type ───────────────────────────────────────────────────────────────

type SchedulerTab = 'jobs' | 'executions'

// ── Component ──────────────────────────────────────────────────────────────

export function SchedulerManager() {
  const { t } = useTranslation()
  usePageHelp({ helpKey: 'scheduler.help' })
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const activeTab: SchedulerTab = tabParam === 'executions' ? 'executions' : 'jobs'

  const tabs = [
    { value: 'jobs', label: t('scheduler.tabs.jobs'), panel: <SchedulerJobsTab /> },
    { value: 'executions', label: t('scheduler.tabs.executions'), panel: <SchedulerExecutionsTab /> },
  ]

  return (
    <div className="page scheduler-workspace">
      <PageHeader title={t('nav.scheduler')} description={t('nav.help.scheduler')} />
      <Tabs
        tabs={tabs}
        value={activeTab}
        onChange={(next) => {
          const params = new URLSearchParams(searchParams)
          if (next === 'jobs') params.delete('tab')
          else params.set('tab', next)
          setSearchParams(params, { replace: true })
        }}
        ariaLabel={t('scheduler.tabsLabel')}
      />
    </div>
  )
}

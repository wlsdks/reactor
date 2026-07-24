import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { PageHeader, SectionErrorBoundary, Tabs } from '../shared/ui'
import { AdminSettingsTab } from '../features/admin-settings/ui/AdminSettingsTab'
import { RetentionTab } from '../features/retention/ui/RetentionTab'

type SettingsTab = 'runtime' | 'retention'

function isSettingsTab(value: string | null): value is SettingsTab {
  return value === 'runtime' || value === 'retention'
}

export function SettingsPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const activeTab: SettingsTab = isSettingsTab(tabParam) ? tabParam : 'runtime'

  const tabs = [
    {
      value: 'runtime',
      label: t('settingsPage.tabRuntime'),
      panel: <AdminSettingsTab />,
    },
    {
      value: 'retention',
      label: t('settingsPage.tabRetention'),
      panel: <RetentionTab />,
    },
  ]

  return (
    <SectionErrorBoundary name="settings-page">
      <div className="page">
        <PageHeader title={t('settingsPage.title')} description={t('settingsPage.description')} />
        <Tabs
          tabs={tabs}
          value={activeTab}
          onChange={(next) => {
            const params = new URLSearchParams(searchParams)
            params.set('tab', next)
            setSearchParams(params, { replace: true })
          }}
          ariaLabel={t('settingsPage.tabsLabel')}
        />
      </div>
    </SectionErrorBoundary>
  )
}

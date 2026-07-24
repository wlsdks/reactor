import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ModelRegistryManager } from '../features/model-registry'
import { listModels } from '../features/model-registry/api'
import {
  PlatformPricingAlertsTab,
  usePlatformAdminData,
} from '../features/platform-admin'
import { queryKeys } from '../shared/lib/queryKeys'
import { PageHeader, SectionErrorBoundary, Tabs } from '../shared/ui'

type ModelsTab = 'registry' | 'pricing' | 'alerts'

function isValidTab(value: string | null): value is ModelsTab {
  return value === 'registry' || value === 'pricing' || value === 'alerts'
}

function PricingTabPanel() {
  const {
    pricing,
    alertRules,
    activeAlerts,
    saving,
    pricingForm,
    ruleForm,
    setPricingForm,
    setRuleForm,
    handleUpsertPricing,
    handleSaveAlertRule,
    deleteAlertMutation,
    resolveAlertMutation,
    pricingError,
    handleRefresh,
  } = usePlatformAdminData(undefined, { pricing: true })

  const { data: models = [] } = useQuery({
    queryKey: queryKeys.models.list(),
    queryFn: listModels,
  })
  const defaultModelName = models.find(m => m.isDefault)?.name ?? null

  return (
    <PlatformPricingAlertsTab
      section="pricing"
      pricing={pricing}
      alertRules={alertRules}
      activeAlerts={activeAlerts}
      saving={saving}
      pricingForm={pricingForm}
      ruleForm={ruleForm}
      onPricingFormChange={setPricingForm}
      onRuleFormChange={setRuleForm}
      onUpsertPricing={() => void handleUpsertPricing()}
      onSaveAlertRule={() => void handleSaveAlertRule()}
      onDeleteRule={(id) => deleteAlertMutation.mutate(id)}
      onResolveAlert={(id) => resolveAlertMutation.mutate(id)}
      defaultModelName={defaultModelName}
      pricingError={pricingError}
      onRetry={handleRefresh}
    />
  )
}

function AlertsTabPanel() {
  const {
    pricing,
    alertRules,
    activeAlerts,
    saving,
    pricingForm,
    ruleForm,
    setPricingForm,
    setRuleForm,
    handleUpsertPricing,
    handleSaveAlertRule,
    deleteAlertMutation,
    resolveAlertMutation,
    alertRulesError,
    activeAlertsError,
    handleRefresh,
  } = usePlatformAdminData(undefined, { alerts: true })

  return (
    <PlatformPricingAlertsTab
      section="alerts"
      pricing={pricing}
      alertRules={alertRules}
      activeAlerts={activeAlerts}
      saving={saving}
      pricingForm={pricingForm}
      ruleForm={ruleForm}
      onPricingFormChange={setPricingForm}
      onRuleFormChange={setRuleForm}
      onUpsertPricing={() => void handleUpsertPricing()}
      onSaveAlertRule={() => void handleSaveAlertRule()}
      onDeleteRule={(id) => deleteAlertMutation.mutate(id)}
      onResolveAlert={(id) => resolveAlertMutation.mutate(id)}
      alertRulesError={alertRulesError}
      activeAlertsError={activeAlertsError}
      onRetry={handleRefresh}
    />
  )
}

export function ModelRegistryPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const activeTab: ModelsTab = isValidTab(tabParam) ? tabParam : 'registry'

  const tabs = [
    {
      value: 'registry',
      label: t('modelsPage.tabRegistry'),
      panel: <ModelRegistryManager />,
    },
    {
      value: 'pricing',
      label: t('modelsPage.tabPricing'),
      panel: <PricingTabPanel />,
    },
    {
      value: 'alerts',
      label: t('modelsPage.tabAlerts'),
      panel: <AlertsTabPanel />,
    },
  ]

  return (
    <SectionErrorBoundary name="model-registry">
      <div className="page">
        <PageHeader
          title={t('modelsPage.title')}
          description={t('modelsPage.description')}
        />
        <Tabs
          tabs={tabs}
          value={activeTab}
          onChange={(next) => {
            const params = new URLSearchParams(searchParams)
            params.set('tab', next)
            setSearchParams(params, { replace: true })
          }}
          ariaLabel={t('modelsPage.tabsLabel')}
        />
      </div>
    </SectionErrorBoundary>
  )
}

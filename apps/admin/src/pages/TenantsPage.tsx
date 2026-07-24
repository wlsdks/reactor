import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { PageHeader, SectionErrorBoundary, Tabs } from '../shared/ui'
import { PlatformTenantsTab, usePlatformAdminData } from '../features/platform-admin'
import { TenantAdminManager } from '../features/tenant-admin/ui/TenantAdminManager'

type TenantsTab = 'admin' | 'tenant'

function isValidTab(value: string | null): value is TenantsTab {
  return value === 'admin' || value === 'tenant'
}

interface AdminTabContentProps {
  selectedTenantId?: string
  onSelectTenant: (id: string | null) => void
  onOpenTenantOperations: (id: string) => void
}

function AdminTabContent({
  selectedTenantId,
  onSelectTenant,
  onOpenTenantOperations,
}: AdminTabContentProps) {
  const {
    tenants,
    isLoading,
    selectedTenant,
    tenantForm,
    saving,
    notice,
    setSelectedTenantId,
    setTenantForm,
    handleCreateTenant,
    suspendMutation,
    activateMutation,
    handleRefresh,
    tenantsError,
    selectedTenantError,
  } = usePlatformAdminData(selectedTenantId, { tenants: true })

  return (
    <>
      {notice && <div className="alert alert-warning">{notice}</div>}

      <PlatformTenantsTab
        tenants={tenants}
        isLoading={isLoading}
        selectedTenant={selectedTenant}
        tenantForm={tenantForm}
        saving={saving}
        tenantsError={tenantsError}
        selectedTenantError={selectedTenantError}
        onRetry={handleRefresh}
        onSelectTenant={(id) => {
          setSelectedTenantId(id)
          onSelectTenant(id)
        }}
        onOpenTenantOperations={onOpenTenantOperations}
        onTenantFormChange={setTenantForm}
        onCreateTenant={() => void handleCreateTenant()}
        onSuspendTenant={(id) => suspendMutation.mutate(id)}
        onActivateTenant={(id) => activateMutation.mutate(id)}
      />
    </>
  )
}

function TenantTabContent({ tenantId }: { tenantId?: string }) {
  return <TenantAdminManager tenantId={tenantId} embedded />
}

export function TenantsPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const tenantIdParam = searchParams.get('tenantId') ?? undefined
  const activeTab: TenantsTab = isValidTab(tabParam) ? tabParam : 'admin'

  const updateWorkspace = (tab: TenantsTab, tenantId?: string | null) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', tab)
    if (tenantId) params.set('tenantId', tenantId)
    else params.delete('tenantId')
    setSearchParams(params, { replace: true })
  }

  const tabs = [
    {
      value: 'admin',
      label: t('tenantsPage.tabRoster'),
      panel: (
        <AdminTabContent
          selectedTenantId={tenantIdParam}
          onSelectTenant={(id) => updateWorkspace('admin', id)}
          onOpenTenantOperations={(id) => updateWorkspace('tenant', id)}
        />
      ),
    },
    {
      value: 'tenant',
      label: t('tenantsPage.tabOperations'),
      panel: <TenantTabContent tenantId={tenantIdParam} />,
    },
  ]

  return (
    <SectionErrorBoundary name="tenants-page">
      <div className="page">
        <PageHeader title={t('tenantsPage.title')} description={t('tenantsPage.description')} />
        <Tabs
          tabs={tabs}
          value={activeTab}
          onChange={(next) => {
            updateWorkspace(next as TenantsTab, tenantIdParam)
          }}
          ariaLabel={t('tenantsPage.tabsLabel')}
        />
      </div>
    </SectionErrorBoundary>
  )
}

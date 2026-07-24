import './PlatformTenantsTab.css'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DataTable, EmptyState, LoadingSpinner, TableSkeleton, WorkspaceUnavailable } from '../../../shared/ui'
import { formatISODate } from '../../../shared/lib/formatters'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import type { Tenant, TenantPlan, TenantStatus } from '../types'

export interface TenantFormState {
  name: string
  slug: string
  plan: TenantPlan
}

export interface PlatformTenantsTabProps {
  tenants: Tenant[]
  isLoading: boolean
  selectedTenant: Tenant | null
  tenantForm: TenantFormState
  saving: boolean
  tenantsError: unknown
  selectedTenantError: unknown
  onRetry: () => void
  onSelectTenant: (id: string | null) => void
  onOpenTenantOperations?: (id: string) => void
  onTenantFormChange: (next: TenantFormState | ((prev: TenantFormState) => TenantFormState)) => void
  onCreateTenant: () => void
  onSuspendTenant: (id: string) => void
  onActivateTenant: (id: string) => void
}

const PLAN_LABELS: Record<TenantPlan, string> = {
  FREE: '무료',
  STARTER: '스타터',
  BUSINESS: '비즈니스',
  ENTERPRISE: '엔터프라이즈',
}

const STATUS_LABELS: Record<TenantStatus, string> = {
  ACTIVE: '운영 중',
  SUSPENDED: '일시 중지',
  DEACTIVATED: '비활성',
}

export function PlatformTenantsTab({
  tenants,
  isLoading,
  selectedTenant,
  tenantForm,
  saving,
  tenantsError,
  selectedTenantError,
  onRetry,
  onSelectTenant,
  onOpenTenantOperations,
  onTenantFormChange,
  onCreateTenant,
  onSuspendTenant,
  onActivateTenant,
}: PlatformTenantsTabProps) {
  const { t } = useTranslation()
  const [creating, setCreating] = useState(false)

  const tenantColumns = [
    { key: 'name', header: t('common.name'), responsivePriority: 1, render: (row: Tenant) => <strong className="tenant-roster__name">{row.name}</strong> },
    { key: 'slug', header: t('platformAdminPage.slug'), responsivePriority: 3, render: (row: Tenant) => <span className="data-mono tenant-roster__secondary">{row.slug}</span> },
    { key: 'plan', header: t('platformAdminPage.plan'), responsivePriority: 3, render: (row: Tenant) => PLAN_LABELS[row.plan] },
    {
      key: 'status',
      header: t('common.status'),
      responsivePriority: 1,
      render: (row: Tenant) => <span className={`tenant-status is-${row.status.toLowerCase()}`}><span aria-hidden="true" />{STATUS_LABELS[row.status]}</span>,
    },
    { key: 'createdAt', header: t('common.createdAt'), responsivePriority: 3, render: (row: Tenant) => <span className="tenant-roster__secondary">{formatISODate(row.createdAt)}</span> },
  ]

  return (
    <div className="tenant-roster">
      <section className="tenant-roster__section" aria-labelledby="tenant-roster-list-title">
        <div className="tenant-roster__heading">
          <div><h2 id="tenant-roster-list-title">{t('platformAdminPage.tenants')}</h2><p>{t('tenantsPage.rosterDescription')}</p></div>
          {!tenantsError ? <div className="tenant-roster__actions">
            <button className="btn btn-ghost btn-sm" type="button" onClick={onRetry}>{t('common.refresh')}</button>
            <button className="btn btn-primary btn-sm" type="button" onClick={() => setCreating((value) => !value)}>{creating ? t('common.cancel') : t('platformAdminPage.createTenant')}</button>
          </div> : null}
        </div>

        {creating && (
          <form className="tenant-create" onSubmit={(event) => { event.preventDefault(); onCreateTenant() }}>
            <label><span>{t('common.name')}</span><input value={tenantForm.name} onChange={(event) => onTenantFormChange((previous) => ({ ...previous, name: event.target.value }))} autoComplete="off" /></label>
            <label><span>{t('platformAdminPage.slug')}</span><input value={tenantForm.slug} onChange={(event) => onTenantFormChange((previous) => ({ ...previous, slug: event.target.value }))} autoComplete="off" /></label>
            <label><span>{t('platformAdminPage.plan')}</span><select value={tenantForm.plan} onChange={(event) => onTenantFormChange((previous) => ({ ...previous, plan: event.target.value as TenantPlan }))}>{Object.entries(PLAN_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <button className="btn btn-primary" type="submit" disabled={saving}>{saving ? <LoadingSpinner size="sm" /> : t('platformAdminPage.createTenant')}</button>
          </form>
        )}

        {isLoading ? <TableSkeleton /> : tenantsError ? (
          <WorkspaceUnavailable
            title={t('tenantsPage.loadErrorTitle')}
            description={t('tenantsPage.loadErrorDescription')}
            retryLabel={t('common.retry')}
            retryingLabel={t('common.loading')}
            onRetry={onRetry}
            secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
            guide={{
              title: t('tenantsPage.recoveryTitle'),
              steps: [t('tenantsPage.recoveryAccount'), t('tenantsPage.recoveryConnection')],
              technicalLabel: t('common.technicalDetails'),
              technicalDetail: getErrorMessage(tenantsError),
            }}
          />
        ) : tenants.length === 0 ? (
          <EmptyState message={t('platformAdminPage.noTenants')} description={t('tenantsPage.emptyDescription')} actionLabel={t('platformAdminPage.createTenant')} onAction={() => setCreating(true)} />
        ) : (
          <DataTable columns={tenantColumns} data={tenants} keyFn={(row) => row.id} onRowClick={(row) => onSelectTenant(row.id)} selectedKey={selectedTenant?.id ?? null} tableId="tenant-roster" urlStateKey="tenant-roster" />
        )}
      </section>

      {Boolean(selectedTenant ?? selectedTenantError) && (
        <section className="tenant-roster__section" aria-labelledby="selected-tenant-title">
          <div className="tenant-roster__heading">
            <div><h2 id="selected-tenant-title">{t('platformAdminPage.selectedTenantDetail')}</h2><p>{t('tenantsPage.detailDescription')}</p></div>
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => onSelectTenant(null)}>{t('common.close')}</button>
          </div>
          {selectedTenantError ? <EmptyState message={t('tenantsPage.detailLoadError')} description={getErrorMessage(selectedTenantError)} /> : selectedTenant && (
            <div className="tenant-detail">
              <dl>
                <div><dt>{t('common.name')}</dt><dd>{selectedTenant.name}</dd></div>
                <div><dt>{t('platformAdminPage.slug')}</dt><dd className="data-mono">{selectedTenant.slug}</dd></div>
                <div><dt>{t('platformAdminPage.plan')}</dt><dd>{PLAN_LABELS[selectedTenant.plan]}</dd></div>
                <div><dt>{t('common.status')}</dt><dd>{STATUS_LABELS[selectedTenant.status]}</dd></div>
                <div><dt>{t('platformAdminPage.analytics.sloAvailability')}</dt><dd>{selectedTenant.sloAvailability}%</dd></div>
                <div><dt>{t('platformAdminPage.analytics.sloLatencyP99')}</dt><dd>{selectedTenant.sloLatencyP99Ms}ms</dd></div>
              </dl>
              <div className="tenant-detail__actions">
                {onOpenTenantOperations && <button type="button" className="btn btn-primary" onClick={() => onOpenTenantOperations(selectedTenant.id)}>{t('platformAdminPage.openTenantOperations')}</button>}
                {selectedTenant.status === 'ACTIVE' ? (
                  <button type="button" className="btn btn-secondary" onClick={() => onSuspendTenant(selectedTenant.id)}>{t('platformAdminPage.suspend')}</button>
                ) : (
                  <button type="button" className="btn btn-secondary" onClick={() => onActivateTenant(selectedTenant.id)}>{t('platformAdminPage.activate')}</button>
                )}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

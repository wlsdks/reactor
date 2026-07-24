import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { SkeletonTable, EmptyState, PageHeader, WorkspaceUnavailable } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { isForbiddenError } from '../../../shared/lib/isForbiddenError'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { listRoles } from '../api'
import { RolePillSelector } from './RolePillSelector'
import { RoleDetailCard } from './RoleDetailCard'
import { RoleDiffView } from './RoleDiffView'
import './rbac.css'

export function RbacManager({ embedded = false }: { embedded?: boolean } = {}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [selected, setSelected] = useState<string[]>([])

  const { data: rolesData, isLoading, isFetching, error } = useQuery({
    queryKey: queryKeys.rbac.list(),
    queryFn: listRoles,
  })
  const roles = rolesData ?? []
  const errorMessage = error ? getErrorMessage(error) : null

  function refreshRoles() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.rbac.list() })
  }

  // Default select ADMIN on first load
  const effectiveSelected = selected.length === 0 && roles.length > 0
    ? [roles.find(r => r.id === 'ADMIN')?.id ?? roles[0].id]
    : selected

  function handleToggle(roleId: string) {
    setSelected(prev => {
      if (prev.includes(roleId)) {
        return prev.filter(id => id !== roleId)
      }
      if (prev.length >= 2) {
        return [prev[1], roleId]
      }
      return [...prev, roleId]
    })
  }

  const selectedRoles = effectiveSelected
    .map(id => roles.find(r => r.id === id))
    .filter((r): r is NonNullable<typeof r> => r != null)

  if (isLoading) {
    return (
      <div className={embedded ? 'rbac-workspace' : 'page'}>
        {!embedded ? <PageHeader title={t('rbacPage.title')} description={t('rbacPage.subtitle')} /> : null}
        <SkeletonTable rows={6} columns={3} />
      </div>
    )
  }

  if (errorMessage && rolesData == null) {
    const forbidden = isForbiddenError(error)
    return (
      <div className={embedded ? 'rbac-workspace' : 'page'}>
        {!embedded ? <PageHeader title={t('rbacPage.title')} description={t('rbacPage.subtitle')} /> : null}
        <WorkspaceUnavailable
          title={t(forbidden ? 'rbacPage.accessDeniedTitle' : 'rbacPage.unavailableTitle')}
          description={t(forbidden ? 'rbacPage.accessDeniedDescription' : 'rbacPage.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refreshRoles}
          isRetrying={isFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('rbacPage.recoveryTitle'),
            steps: [t('rbacPage.recoveryAccount'), t('rbacPage.recoveryConnection')],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: errorMessage,
          }}
        />
      </div>
    )
  }

  return (
    <div className={embedded ? 'rbac-workspace' : 'page'}>
      {!embedded ? (
        <PageHeader
          title={t('rbacPage.title')}
          description={effectiveSelected.length === 2 ? t('rbacPage.comparingRoles') : t('rbacPage.subtitle')}
        />
      ) : null}

      {errorMessage && rolesData != null ? (
        <div className="rbac-workspace__sync-note" role="status">
          <span>{t('rbacPage.refreshFailed')}</span>
          <button className="btn btn-sm btn-secondary" onClick={refreshRoles}>{t('common.retry')}</button>
          <details>
            <summary>{t('common.technicalDetails')}</summary>
            <code>{errorMessage}</code>
          </details>
        </div>
      ) : null}

      {roles.length === 0 ? (
        <EmptyState message={t('rbacPage.noRoles')} description={t('rbacPage.noRolesDescription')} />
      ) : (
        <>
          <RolePillSelector
            roles={roles}
            selected={effectiveSelected}
            onToggle={handleToggle}
          />

          <div aria-live="polite">
            {selectedRoles.length === 0 && (
              <EmptyState message={t('rbacPage.selectRole')} />
            )}
            {selectedRoles.length === 1 && (
              <RoleDetailCard role={selectedRoles[0]} />
            )}
            {selectedRoles.length === 2 && (
              <RoleDiffView roleA={selectedRoles[0]} roleB={selectedRoles[1]} />
            )}
          </div>
        </>
      )}
    </div>
  )
}

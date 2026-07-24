import { useTranslation } from 'react-i18next'
import type { Role } from '../types'
import { localizeRoleName } from '../constants'

interface RolePillSelectorProps {
  roles: Role[]
  selected: string[]
  onToggle: (roleId: string) => void
}

export function RolePillSelector({ roles, selected, onToggle }: RolePillSelectorProps) {
  const { t } = useTranslation()

  return (
    <section className="rbac-role-selector" aria-labelledby="rbac-role-selector-title">
      <div className="rbac-role-selector__head">
        <div>
          <h2 id="rbac-role-selector-title">{t('rbacPage.roles')}</h2>
          <p>{t('rbacPage.roleSelectorDescription')}</p>
        </div>
        <span>{t('rbacPage.selectedRoleCount', { count: selected.length || 1 })}</span>
      </div>
      <div className="rbac-role-selector__list" role="group" aria-label={t('rbacPage.roles')}>
        {roles.map(role => {
          const isSelected = selected.includes(role.id)
          return (
            <button
              key={role.id}
              type="button"
              aria-pressed={isSelected}
              className="rbac-role-selector__row"
              onClick={() => onToggle(role.id)}
            >
              <span>{localizeRoleName(role.id, t)}</span>
              <span>{t('rbacPage.permissionCount', { count: role.permissions.length })}</span>
            </button>
          )
        })}
      </div>
      <p className="rbac-role-selector__hint">{t('rbacPage.roleSelectorHint')}</p>
    </section>
  )
}

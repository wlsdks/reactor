import { useTranslation } from 'react-i18next'
import type { Role } from '../types'
import { groupPermissions, localizeAction, localizeResource, localizeRoleDescription, localizeRoleName } from '../constants'

interface RoleDetailCardProps {
  role: Role
}

export function RoleDetailCard({ role }: RoleDetailCardProps) {
  const { t } = useTranslation()
  const groups = groupPermissions(role.permissions)

  return (
    <section className="rbac-role-detail" aria-labelledby={`rbac-role-detail-${role.id}`}>
      <div className="rbac-role-detail__head">
        <div>
          <h2 id={`rbac-role-detail-${role.id}`}>{localizeRoleName(role.id, t)}</h2>
          <p>{localizeRoleDescription(role.id, t)}</p>
        </div>
        <span className="rbac-role-detail__count">{t('rbacPage.permissionCount', { count: role.permissions.length })}</span>
      </div>

      <div className="rbac-role-detail__groups">
        {groups.map(({ groupKey, items }) => (
          <section key={groupKey} className="rbac-role-detail__group">
            <h3>{t(`rbacPage.groups.${groupKey}`)}</h3>
            <ul>
              {items.map(({ resource, actions }) => (
                <li key={resource}>
                  <span>{localizeResource(resource, t)}</span>
                  <span>{actions.map(action => localizeAction(action, t)).join(' · ')}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </section>
  )
}

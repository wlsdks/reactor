import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import type { Role, Permission } from '../types'
import { commonPermissionIds, localizeAction, localizeResource, localizeRoleName, uniquePermissions } from '../constants'

interface RoleDiffViewProps {
  roleA: Role
  roleB: Role
}

function formatPermission(p: Permission, t: TFunction): string {
  return `${localizeResource(p.resource, t)} · ${localizeAction(p.action, t)}`
}

function DiffColumn({ role, other, t }: { role: Role; other: Role; t: TFunction }) {
  const common = commonPermissionIds(role.permissions, other.permissions)
  const onlyInThis = uniquePermissions(role.permissions, other.permissions)
  const onlyInOther = uniquePermissions(other.permissions, role.permissions)
  const commonPerms = role.permissions.filter(p => common.has(p.id))

  return (
    <section className="rbac-role-comparison__column">
      <div className="rbac-role-comparison__head">
        <div>
          <h2>{localizeRoleName(role.id, t)}</h2>
          <p>{t('rbacPage.permissionCount', { count: role.permissions.length })}</p>
        </div>
      </div>

      <div className="rbac-role-comparison__groups">
        {commonPerms.length > 0 ? (
          <section>
            <h3>{t('rbacPage.commonPermissions')}</h3>
            <ul>
              {commonPerms.map(permission => <li key={permission.id}>{formatPermission(permission, t)}</li>)}
            </ul>
          </section>
        ) : null}
        {onlyInThis.length > 0 && (
          <section>
            <h3>{t('rbacPage.onlyThisRole')}</h3>
            <ul>{onlyInThis.map(permission => <li key={permission.id}>{formatPermission(permission, t)}</li>)}</ul>
          </section>
        )}
        {onlyInOther.length > 0 && (
          <section>
            <h3>{t('rbacPage.missingPermissions')}</h3>
            <ul>{onlyInOther.map(permission => <li key={permission.id}>{formatPermission(permission, t)}</li>)}</ul>
          </section>
        )}
      </div>
    </section>
  )
}

export function RoleDiffView({ roleA, roleB }: RoleDiffViewProps) {
  const { t } = useTranslation()

  return (
    <div className="rbac-role-comparison" aria-live="polite">
      <DiffColumn role={roleA} other={roleB} t={t} />
      <DiffColumn role={roleB} other={roleA} t={t} />
    </div>
  )
}

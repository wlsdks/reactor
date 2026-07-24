import type { TFunction } from 'i18next'
import type { Permission } from './types'

const KNOWN_ROLE_IDS = new Set(['ADMIN', 'ADMIN_DEVELOPER', 'ADMIN_MANAGER', 'USER'])

export interface ResourceGroupDef {
  group: string
}

export const RESOURCE_GROUPS: Record<string, ResourceGroupDef> = {
  persona: { group: 'ai' },
  prompt: { group: 'ai' },
  'agent-spec': { group: 'ai' },
  eval: { group: 'ai' },
  session: { group: 'security' },
  feedback: { group: 'security' },
  audit: { group: 'security' },
  guard: { group: 'security' },
  user: { group: 'system' },
  settings: { group: 'system' },
  mcp: { group: 'system' },
  scheduler: { group: 'system' },
  tenant: { group: 'system' },
  slack: { group: 'system' },
  chat: { group: 'chat' },
}

const KNOWN_ACTIONS = new Set(['read', 'write', 'export', 'use', 'select'])

function roleKey(roleId: string): string {
  return KNOWN_ROLE_IDS.has(roleId) ? roleId : 'unknown'
}

export function localizeRoleName(roleId: string, t: TFunction): string {
  return t(`rbacPage.roleNames.${roleKey(roleId)}`)
}

export function localizeRoleDescription(roleId: string, t: TFunction): string {
  return t(`rbacPage.roleDescriptions.${roleKey(roleId)}`)
}

export function localizeResource(resource: string, t: TFunction): string {
  const key = RESOURCE_GROUPS[resource] ? resource : 'unknown'
  return t(`rbacPage.resources.${key}`)
}

export function localizeAction(action: string, t: TFunction): string {
  return t(`rbacPage.actions.${KNOWN_ACTIONS.has(action) ? action : 'unknown'}`)
}

export function groupPermissions(permissions: Permission[]): { groupKey: string; items: { resource: string; actions: string[] }[] }[] {
  const groupOrder = ['ai', 'security', 'system', 'chat']
  const byResource = new Map<string, string[]>()

  for (const p of permissions) {
    const existing = byResource.get(p.resource) ?? []
    existing.push(p.action)
    byResource.set(p.resource, existing)
  }

  const grouped = new Map<string, { resource: string; actions: string[] }[]>()
  for (const [resource, actions] of byResource) {
    const groupKey = RESOURCE_GROUPS[resource]?.group ?? 'system'
    const list = grouped.get(groupKey) ?? []
    list.push({ resource, actions })
    grouped.set(groupKey, list)
  }

  return groupOrder
    .filter(key => grouped.has(key))
    .map(key => ({ groupKey: key, items: grouped.get(key)! }))
}

export function commonPermissionIds(a: Permission[], b: Permission[]): Set<string> {
  const bIds = new Set(b.map(p => p.id))
  return new Set(a.filter(p => bIds.has(p.id)).map(p => p.id))
}

export function uniquePermissions(a: Permission[], b: Permission[]): Permission[] {
  const bIds = new Set(b.map(p => p.id))
  return a.filter(p => !bIds.has(p.id))
}

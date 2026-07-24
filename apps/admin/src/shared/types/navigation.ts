import type { LucideIcon } from 'lucide-react'

export type AdminRole = 'ADMIN' | 'ADMIN_MANAGER' | 'ADMIN_DEVELOPER'

export type NavItemVisibility = 'all' | readonly AdminRole[]

export interface NavItem {
  path: string
  label: string
  description: string
  visibleTo?: NavItemVisibility
  icon: LucideIcon
  releaseStepNumber?: number
  /** Keep a partial-capability workspace discoverable while its panels fail independently. */
  discoverableWithoutCapability?: boolean
}

export interface NavGroup {
  titleKey: string
  descriptionKey?: string
  items: NavItem[]
}

export interface Permission {
  id: string
  resource: string
  action: string
}

/** Shape returned by GET /api/admin/rbac/roles */
export interface RawRole {
  role: string
  scope?: string | null
  permissions: string[]
}

export interface Role {
  id: string
  name: string
  description: string
  isSystem: boolean
  permissions: Permission[]
  memberCount: number
  createdAt: number
}

export interface UserRoleAssignment {
  userId: string
  email: string
  roles: Role[]
  grantedAt: number
  grantedBy: string
}

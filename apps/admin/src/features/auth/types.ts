export type UserRole = 'USER' | 'ADMIN' | 'ADMIN_MANAGER' | 'ADMIN_DEVELOPER'
export type AdminScope = 'FULL' | 'MANAGER' | 'DEVELOPER'

export interface User {
  id: string
  email: string
  name: string
  role: UserRole
  adminScope?: AdminScope | null
}

export interface LoginRequest {
  email: string
  password: string
  forceLogin?: boolean
}

export interface RegisterRequest {
  email: string
  password: string
  name: string
}

export interface ChangePasswordRequest {
  currentPassword: string
  newPassword: string
}

/** Raw response from POST /api/auth/register */
export interface RegisterResponse {
  email: string
  userId: string
}

/** Response from reactor POST /api/auth/login */
export interface AuthResponse {
  token: string
  user: User | null
  error?: string | null
}

/** Response from reactor-iam POST /api/auth/login */
export interface IamTokenResponse {
  requiresTwoFactor: boolean
  accessToken: string | null
  tokenType: string | null
  expiresIn: number | null
  user: IamUserInfo | null
}

export interface IamUserInfo {
  id: string
  roles: string[]
  permissions: string[]
}

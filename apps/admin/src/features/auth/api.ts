import type {
  LoginRequest,
  RegisterRequest,
  ChangePasswordRequest,
  RegisterResponse,
  AuthResponse,
  IamTokenResponse,
} from './types'
import ky from 'ky'
import { api } from '../../shared/api/client'
import { normalizeResponseError } from '../../shared/api/errors'

const AUTH_PREFIX = import.meta.env.VITE_API_URL ?? ''
const IAM_PREFIX = import.meta.env.VITE_IAM_URL ?? ''

/**
 * Whether IAM login flow is enabled.
 *
 * In dev mode, vite proxy routes /api/auth/login to reactor-iam automatically
 * (configured via VITE_IAM_PROXY_TARGET in vite.config.ts), so VITE_IAM_URL
 * does not need to be set — just VITE_IAM_ENABLED=true is enough.
 *
 * In production, VITE_IAM_URL must be set so the browser can call reactor-iam
 * directly (or via nginx proxy).
 */
export const IAM_ENABLED = import.meta.env.VITE_IAM_ENABLED === 'true' || !!IAM_PREFIX

// Unauthenticated ky instance for reactor (also used for IAM via vite proxy in dev)
const publicApi = ky.create({
  prefixUrl: `${AUTH_PREFIX}/api`,
  retry: 0,
  hooks: {
    beforeError: [
      async (error) => {
        throw await normalizeResponseError(error.response)
      },
    ],
  },
})

// Dedicated IAM ky instance for production (direct browser → IAM calls)
// In dev, this is null and publicApi is used instead (vite proxy handles routing)
const iamApi = IAM_PREFIX
  ? ky.create({ prefixUrl: `${IAM_PREFIX}/api`, retry: 0 })
  : null

/** Direct login to reactor (fallback when IAM is not configured) */
export const directLogin = (request: LoginRequest): Promise<AuthResponse> =>
  publicApi.post('auth/login', { json: request }).json()

/**
 * Login via reactor-iam (returns RS256 JWT).
 * In dev: uses publicApi (vite proxy routes /api/auth/login → reactor-iam)
 * In prod: uses iamApi (direct call to VITE_IAM_URL)
 */
export const iamLogin = (request: LoginRequest): Promise<IamTokenResponse> => {
  const client = iamApi ?? publicApi
  // Admin dashboard always forces login to avoid concurrent session blocks
  return client.post('auth/login', { json: { ...request, forceLogin: true } }).json()
}

/** Exchange reactor-iam RS256 token for reactor HS256 token */
export const exchangeToken = (iamToken: string): Promise<AuthResponse> =>
  publicApi.post('auth/exchange', { json: { token: iamToken } }).json()

/** R427: 원클릭 데모 로그인 — 고정 ADMIN 계정 토큰 발급 */
export const demoLogin = (): Promise<AuthResponse> =>
  publicApi.post('auth/demo-login').json()

/** Best-effort logout from reactor-iam (revoke IAM session) */
export const iamLogout = (iamToken: string): Promise<void> => {
  const client = iamApi ?? publicApi
  return client
    .post('auth/logout', {
      headers: { Authorization: `Bearer ${iamToken}` },
    })
    .then(() => undefined)
}

export const register = (request: RegisterRequest): Promise<RegisterResponse> =>
  publicApi.post('auth/register', { json: request }).json()

export const logout = (): Promise<void> =>
  api.post('auth/logout').then(() => undefined)

export const changePassword = (request: ChangePasswordRequest): Promise<void> =>
  api.post('auth/change-password', { json: request }).then(() => undefined)

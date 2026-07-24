export const API_BASE = import.meta.env.VITE_API_URL || ''

const selfRegistrationFlag = String(import.meta.env.VITE_AUTH_ALLOW_SELF_REGISTRATION || '')
  .trim()
  .toLowerCase()

export const AUTH_SELF_REGISTRATION_ENABLED = selfRegistrationFlag === 'true'

export const QUERY_STALE_TIME_MS = 30_000
export const TOAST_DURATION_MS = 5000
export const PASSWORD_MIN_LENGTH = 8
